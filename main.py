import os
import pyttsx3
from dotenv import load_dotenv
from openai import OpenAI
from twitchio.ext import commands
import asyncio
import websockets
import json
from transformers import pipeline
import requests
import mss
import numpy as np
import cv2
from elevenlabs import set_api_key, generate, play
from elevenlabs import voices

# =========================
# 🔐 Cargar variables
# =========================
load_dotenv()

# =========================
# 🎵 Cola de audio global
# =========================
audio_queue = asyncio.Queue()

set_api_key(os.getenv("ELEVENLABS_API_KEY"))

# Listar voces disponibles (opcional, puede comentarse)
try:
    voces_disponibles = voices()
    print("Voces disponibles:", [v["name"] for v in voces_disponibles])
except Exception as e:
    print("No se pudieron cargar voces de ElevenLabs:", e)

# =========================
# 🧠 Modelo de sentimiento
# =========================
print("Cargando modelo de sentimiento...")
sentiment_model = pipeline(
    "sentiment-analysis",
    model="distilbert-base-uncased-finetuned-sst-2-english",
)
print("Modelo de sentimiento listo.")

def analizar_sentimiento(texto: str):
    result = sentiment_model(texto)[0]
    return result["label"], result["score"]

# =========================
# 🔊 TTS local (pyttsx3)
# =========================
tts_engine = pyttsx3.init()

async def hablar_async(texto):
    await asyncio.to_thread(tts_engine.say, texto)
    await asyncio.to_thread(tts_engine.runAndWait)

# =========================
# 🔊 ElevenLabs TTS
# =========================
async def hablar_elevenlabs(texto, voz="Bella"):
    try:
        audio = generate(
            text=texto,
            voice=voz,
            model="eleven_multilingual_v1"
        )
        await asyncio.to_thread(play, audio)
    except Exception as e:
        print("Error ElevenLabs TTS:", e)
        # Fallback a TTS local si ElevenLabs falla
        await hablar_async(texto)

# =========================
# 🎵 Worker de cola de audio
# =========================
async def audio_worker():
    """
    Procesa los audios en orden, uno por uno.
    Evita que se solapen si varios usuarios usan !ask al mismo tiempo.
    """
    while True:
        texto, voz = await audio_queue.get()
        try:
            audio = generate(
                text=texto,
                voice=voz,
                model="eleven_multilingual_v1"
            )
            await asyncio.to_thread(play, audio)
        except Exception as e:
            print(f"⚠️  Error ElevenLabs en cola: {e} — usando TTS local")
            await hablar_async(texto)
        finally:
            audio_queue.task_done()

# =========================
# 📸 Captura de pantalla
# =========================
def capturar_pantalla():
    """Captura un frame de la pantalla principal."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        frame = np.array(screenshot)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        return frame

# =========================
# 🔌 VTube Studio conexión
# =========================
async def conectar_vts():
    uri = "ws://localhost:8001"
    ws = await websockets.connect(uri)

    # Paso 1: pedir token si no existe
    vts_token = os.getenv("VTS_TOKEN", "")

    if not vts_token:
        token_request = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "token_request",
            "messageType": "AuthenticationTokenRequest",
            "data": {
                "pluginName": "Angela Chan",
                "pluginDeveloper": "stevan560",
                "pluginIcon": ""
            }
        }
        await ws.send(json.dumps(token_request))
        token_response = json.loads(await ws.recv())
        vts_token = token_response.get("data", {}).get("authenticationToken", "")
        print(f"⚠️  Guarda este token en tu .env como VTS_TOKEN={vts_token}")

    # Paso 2: autenticar con el token
    auth_request = {
        "apiName": "VTubeStudioPublicAPI",
        "apiVersion": "1.0",
        "requestID": "auth_test",
        "messageType": "AuthenticationRequest",
        "data": {
            "pluginName": "Angela Chan",
            "pluginDeveloper": "stevan560",
            "authenticationToken": vts_token
        }
    }

    await ws.send(json.dumps(auth_request))
    response = await ws.recv()
    print("VTS auth response:", response)

    return ws

async def activar_expresion(ws, archivo_exp):
    if ws is None:
        return
    try:
        request = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "exp_auto",
            "messageType": "ExpressionActivationRequest",
            "data": {
                "expressionFile": archivo_exp,
                "active": True
            }
        }
        await ws.send(json.dumps(request))
    except Exception as e:
        print("Error activando expresión VTS:", e)

# =========================
# ☁️ OpenAI client
# =========================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# 🤖 BOT de Twitch
# =========================
class Bot(commands.Bot):

    def __init__(self):
        super().__init__(
            token=os.getenv("TWITCH_TOKEN"),
            prefix="!",
            initial_channels=[os.getenv("TWITCH_CHANNEL")]
        )
        self.vts_ws = None

    async def event_ready(self):
        print(f"✅ Bot conectado como {self.nick}")
        asyncio.create_task(audio_worker()) 
        print("✅ Cola de audio iniciada")
        try:
            self.vts_ws = await conectar_vts()
            print("✅ Conectado a VTube Studio")
        except Exception as e:
            print("⚠️  No se pudo conectar a VTube Studio:", e)

    async def event_message(self, message):
        # Ignorar mensajes del propio bot
        if message.echo:
            return

        print(f"[{message.author.name}]: {message.content}")

        # Analizar sentimiento del mensaje
        label, score = analizar_sentimiento(message.content)
        print(f"Sentimiento: {label} ({score:.2f})")

        # Cambiar expresión según emoción detectada
        if label == "POSITIVE" and score > 0.8:
            await activar_expresion(self.vts_ws, "smile.exp3.json")
        elif label == "NEGATIVE" and score > 0.8:
            await activar_expresion(self.vts_ws, "sad.exp3.json")
        else:
            await activar_expresion(self.vts_ws, "neutral.exp3.json")

        # Ignorar mensajes muy negativos
        if label == "NEGATIVE" and score > 0.9:
            print("Mensaje ignorado por negatividad alta.")
            return

        # Comando !ask
        if message.content.startswith("!ask"):
            pregunta = message.content.replace("!ask", "").strip()

            if not pregunta:
                await message.channel.send("¡Escribe algo después de !ask! 😊")
                return

            respuesta, sentimiento = await self.consultar_modelo(pregunta)

            # Cambiar expresión según sentimiento de la respuesta
            if sentimiento == "POSITIVE":
                await activar_expresion(self.vts_ws, "smile.exp3.json")
            elif sentimiento == "NEGATIVE":
                await activar_expresion(self.vts_ws, "sad.exp3.json")
            else:
                await activar_expresion(self.vts_ws, "neutral.exp3.json")

            # Twitch tiene límite de 500 caracteres por mensaje
            await message.channel.send(respuesta[:500])

            # Encolar respuesta para voz (evita solapamiento)
            await audio_queue.put((respuesta, "Bella"))
            print(f"🎵 Audio encolado — {audio_queue.qsize()} en espera")

        await self.handle_commands(message)

    # =========================
    # 🧠 Modelo híbrido
    # =========================
    async def consultar_modelo(self, texto):
        """
        Intenta primero el servidor IA local.
        Si falla, usa OpenAI como fallback.
        """

        # 1️⃣ Intentar servidor IA local
        try:
            r = requests.post(
                "http://192.168.1.50:8000/procesar",  # <-- Cambia esta IP si es necesario
                json={"text": texto},
                timeout=30
            )
            r.raise_for_status()
            data = r.json()
            print("✅ Respuesta desde servidor IA local")
            return data["respuesta"], data["sentimiento"]

        except Exception as e:
            print(f"⚠️  Error servidor IA local: {e}")

        # 2️⃣ Fallback: OpenAI
        print("☁️  Usando fallback OpenAI...")
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Eres una VTuber femenina llamada Angela. "
                            "Eres relajada, inteligente y curiosa. "
                            "Respondes de forma breve y amigable en el chat de Twitch."
                        )
                    },
                    {"role": "user", "content": texto}
                ],
                max_tokens=4096,
            )
            return response.choices[0].message.content, "NEUTRAL"

        except Exception as e:
            print(f"❌ Error OpenAI: {e}")
            return "¡Algo falló, lo siento! 😅", "NEUTRAL"

# =========================
# 🚀 Ejecutar bot
# =========================
if __name__ == "__main__":
    bot = Bot()
    bot.run()
