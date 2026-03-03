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
from collections import deque
from datetime import datetime
import game          # 🎮 módulo shooter
import game_minecraft  # ⛏️  módulo minecraft
import yolo_model     # modelo de visión (YOLO)

# =========================
# 🔐 Cargar variables
# =========================
load_dotenv()

# =========================
# 🎵 Cola de audio global
# =========================
audio_queue = asyncio.Queue()

# =========================
# 📜 Historial compartido del chat
# =========================
# Guarda los últimos 300 mensajes del chat (usuario + Angela)
# Se pasa como contexto al modelo en el fallback si el servidor cae
HISTORIAL_MAX = 300
chat_history = deque(maxlen=HISTORIAL_MAX)

def agregar_al_historial(rol: str, nombre: str, contenido: str):
    """
    rol: 'user' o 'assistant'
    nombre: nombre del usuario de Twitch o 'Angela'
    contenido: texto del mensaje
    """
    chat_history.append({
        "rol": rol,
        "nombre": nombre,
        "contenido": contenido,
        "hora": datetime.now().strftime("%H:%M")
    })

def historial_como_messages():
    """
    Convierte el historial al formato de mensajes que espera OpenAI/Ollama.
    """
    messages = []
    for entry in chat_history:
        # Prefijamos el nombre para que Angela sepa quién dijo qué
        texto = f"[{entry['nombre']}]: {entry['contenido']}" if entry["rol"] == "user" else entry["contenido"]
        messages.append({"role": entry["rol"], "content": texto})
    return messages

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
        self.game_task      = None  # 🎮 tarea shooter
        self.minecraft_task = None  # ⛏️  tarea minecraft

    async def event_ready(self):
        print(f"✅ Bot conectado como {self.nick}")
        asyncio.create_task(audio_worker())
        print("✅ Cola de audio iniciada")
        asyncio.create_task(self.loop_vision())
        print("✅ Vision loop iniciado")
        try:
            self.vts_ws = await conectar_vts()
            print("✅ Conectado a VTube Studio")
        except Exception as e:
            print("⚠️  No se pudo conectar a VTube Studio:", e)

    async def loop_vision(self):
        """Captura pantalla cada 5 segundos (preparado para análisis futuro)."""
        while True:
            try:
                frame = capturar_pantalla()
                # TODO: aquí puedes analizar el frame con YOLO u OpenCV
                _ = frame  # sin uso por ahora
            except Exception as e:
                print(f"⚠️  Error captura pantalla: {e}")
            await asyncio.sleep(5)

    async def event_message(self, message):
        # Ignorar mensajes del propio bot
        if message.echo:
            return

        print(f"[{message.author.name}]: {message.content}")

        # Guardar mensaje en historial compartido
        agregar_al_historial("user", message.author.name, message.content)

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

        # Comando !historial — muestra cuántos mensajes recuerda Angela
        if message.content.startswith("!historial"):
            total = len(chat_history)
            await message.channel.send(
                f"📜 Recuerdo los últimos {total} mensajes del chat (máx {HISTORIAL_MAX}). "
                f"Primer mensaje desde las {chat_history[0]['hora'] if total > 0 else '—'}."
            )
            return

        # Comando !olvida — limpia el historial (solo el streamer)
        if message.content.startswith("!olvida"):
            if message.author.name.lower() == os.getenv("TWITCH_NICK", "").lower():
                chat_history.clear()
                # ✅ También limpiar el historial del servidor
                try:
                    requests.post("http://192.168.1.50:8000/reset", timeout=5)
                except Exception:
                    pass
                await message.channel.send("🧹 Historial limpiado. ¡Empezamos de cero!")
            return

        # Comando !jugar — Angela juega shooter (solo el streamer)
        if message.content.startswith("!jugar"):
            if message.author.name.lower() != os.getenv("TWITCH_NICK", "").lower():
                await message.channel.send("Solo el streamer puede usar !jugar 😅")
                return
            if game.jugando or game_minecraft.jugando:
                await message.channel.send("¡Ya estoy jugando algo! Usa !parar primero 🎮")
                return
            await message.channel.send("🎮 ¡Vamos al shooter! Asegúrate de que el juego esté en pantalla.")
            await audio_queue.put(("¡Vamos a jugar!", "Bella"))
            self.game_task = asyncio.create_task(
                game.loop_juego(yolo, self.consultar_modelo, audio_queue, message.channel)
            )
            return

        # Comando !minecraft — Angela juega Minecraft (solo el streamer)
        if message.content.startswith("!minecraft"):
            if message.author.name.lower() != os.getenv("TWITCH_NICK", "").lower():
                await message.channel.send("Solo el streamer puede usar !minecraft 😅")
                return
            if game.jugando or game_minecraft.jugando:
                await message.channel.send("¡Ya estoy jugando algo! Usa !parar primero ⛏️")
                return
            await message.channel.send("⛏️ ¡A minar se ha dicho! Asegúrate de que Minecraft esté abierto.")
            await audio_queue.put(("¡Vamos a jugar Minecraft!", "Bella"))
            self.minecraft_task = asyncio.create_task(
                game_minecraft.loop_minecraft(yolo, self.consultar_modelo, audio_queue, message.channel)
            )
            return

        # Comando !parar — para cualquier juego activo (solo el streamer)
        if message.content.startswith("!parar"):
            if message.author.name.lower() != os.getenv("TWITCH_NICK", "").lower():
                return
            if not game.jugando and not game_minecraft.jugando:
                await message.channel.send("No estaba jugando nada 🤷")
                return
            game.parar_juego()
            game_minecraft.parar_minecraft()
            for t in [self.game_task, self.minecraft_task]:
                if t:
                    t.cancel()
            self.game_task = None
            self.minecraft_task = None
            await message.channel.send("🛑 Dejé de jugar.")
            await audio_queue.put(("Listo, paré de jugar.", "Bella"))
            return

        # Comando !ask
        if message.content.startswith("!ask"):
            pregunta = message.content.replace("!ask", "").strip()

            if not pregunta:
                await message.channel.send("¡Escribe algo después de !ask! 😊")
                return

            # ✅ Pasamos el nombre del usuario en lugar del historial
            respuesta, sentimiento = await self.consultar_modelo(
                pregunta,
                usuario=message.author.name
            )

            # Guardar respuesta de Angela en el historial local
            agregar_al_historial("assistant", "Angela", respuesta)

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
    async def consultar_modelo(self, texto, usuario="viewer"):
        """
        El servidor IA maneja el historial internamente.
        Solo enviamos el texto y el nombre del usuario.
        Si el servidor falla, el fallback OpenAI usa el historial local.
        """

        # 1️⃣ Intentar servidor IA local (maneja historial él solo)
        try:
            r = requests.post(
                "http://192.168.1.50:8000/procesar",  # <-- Cambia esta IP si es necesario
                json={"text": texto, "user": usuario},  # ✅ ya no enviamos historial
                timeout=30
            )
            r.raise_for_status()
            data = r.json()
            modelo = data.get("modelo_usado", "?")
            turnos = data.get("historial_turnos", "?")
            print(f"✅ Servidor IA [{modelo}] — {turnos} turnos en historial")
            return data["respuesta"], data["sentimiento"]

        except Exception as e:
            print(f"⚠️  Error servidor IA local: {e}")

        # 2️⃣ Fallback: OpenAI con historial local (si el servidor está caído)
        print("☁️  Usando fallback OpenAI con historial local...")
        try:
            system_prompt = {
                "role": "system",
                "content": (
                    "Eres una VTuber femenina llamada Angela. "
                    "Eres relajada, inteligente y curiosa. "
                    "Respondes de forma breve y amigable en el chat de Twitch. "
                    "Tienes memoria del chat: usa el contexto anterior para dar respuestas coherentes."
                )
            }
            messages = [system_prompt] + historial_como_messages()[-20:] + [
                {"role": "user", "content": f"[{usuario}]: {texto}"}
            ]

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=300,
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
