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
import tensorflow as tf
from Ollama import OllamaClient



# =========================
# 🔐 Cargar variables
# =========================
load_dotenv()
load_dotenv(dotenv_path="config.env")

load_requeriments()()
read_requeriments()()

# =========================
# 🧠 Modelo de sentimiento
# =========================
print("Cargando modelo de sentimiento...")
sentiment_model = pipeline(
    "sentiment-analysis",
    model="distilbert-base-uncased-finetuned-sst-2-english",
    framework="tf"
)
print("Modelo de sentimiento listo.")

def analizar_sentimiento(texto: str):
    result = sentiment_model(texto)[0]
    return result["label"], result["score"]

# =========================
# 🔊 TTS
# =========================
tts_engine = pyttsx3.init()

async def hablar_async(texto):
    await asyncio.to_thread(tts_engine.say, texto)
    await asyncio.to_thread(tts_engine.runAndWait)

# =========================
# 🔌 VTube Studio conexión
# =========================
async def conectar_vts():
    uri = "ws://localhost:8001"
    ws = await websockets.connect(uri)

    auth_request = {
        "apiName": "VTubeStudioPublicAPI",
        "apiVersion": "1.0",
        "requestID": "auth_test",
        "messageType": "AuthenticationRequest",
        "data": {
            "pluginName": "angelia chan",
            "pluginDeveloper": "stevan 560",
            "authenticationToken": ""
        }
    }

    await ws.send(json.dumps(auth_request))
    response = await ws.recv()
    print("VTS:", response)

    return ws

async def activar_expresion(ws, archivo_exp):
    if ws is None:
        return

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

# =========================
# ☁️ OpenAI
# =========================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# 🤖 BOT
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
        print(f'Bot conectado como {self.nick}')
        try:
            self.vts_ws = await conectar_vts()
        except Exception as e:
            print("No se pudo conectar a VTube Studio:", e)

    async def event_message(self, message):

        # Ignorar mensajes del propio bot
        if message.echo:
            return

        print(f"{message.author.name}: {message.content}")

        # Analizar sentimiento del mensaje completo
        label, score = analizar_sentimiento(message.content)
        print("Sentimiento:", label, score)

        # Cambiar expresión según emoción
        if label == "POSITIVE" and score > 0.8:
            await activar_expresion(self.vts_ws, "smile.exp3.json")
        elif label == "NEGATIVE" and score > 0.8:
            await activar_expresion(self.vts_ws, "sad.exp3.json")
        else:
            await activar_expresion(self.vts_ws, "neutral.exp3.json")

        # Ignorar mensajes muy negativos fuertes
        if label == "NEGATIVE" and score > 0.9:
            return

        # Comando !ask
        if message.content.startswith("!ask"):
            pregunta = message.content.replace("!ask", "").strip()

            if not pregunta:
                await message.channel.send("Escribe algo después de !ask")
                return

            respuesta, sentimiento = await self.consultar_modelo(pregunta)

            # 🎭 Cambiar expresión según sentimiento del servidor IA
            if sentimiento == "POSITIVE":
                await activar_expresion(self.vts_ws, "smile.exp3.json")
            elif sentimiento == "NEGATIVE":
                await activar_expresion(self.vts_ws, "sad.exp3.json")
            else:
                await activar_expresion(self.vts_ws, "neutral.exp3.json")

            await message.channel.send(respuesta[:400])

            await hablar_async(respuesta)

        await self.handle_commands(message)

    # =========================
    # 🧠 MODELO HÍBRIDO
    # =========================
    async def consultar_modelo(self, texto):

        # =========================
        # 🖥️ Intentar PC IA local
        # =========================
        try:
            r = requests.post(
                "http://192.168.1.50:8000/procesar",  # <-- CAMBIA ESTA IP
                json={"text": texto},
                timeout=30
            )

            data = r.json()

            print("Respuesta desde PC IA")

            return data["respuesta"], data["sentimiento"]

        except Exception as e:
            print("Error PC IA:", e)

        # =========================
        # ☁️ Fallback OpenAI
        # =========================
        print("Usando fallback OpenAI")

        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "Eres un bot divertido de Twitch."},
                    {"role": "user", "content": texto}
                ],
                max_tokens=12000,
            )

            return response.choices[0].message.content, "NEUTRAL"

        except Exception as e:
            print("Error OpenAI:", e)
            return "Algo falló 😅", "NEUTRAL"

# =========================
# 🚀 Ejecutar bot
# =========================
bot = Bot()
bot.run()
