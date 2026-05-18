from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import pipeline
from openai import OpenAI
import ollama
import os
import json

load_dotenv()

app = FastAPI()

# =========================
# 🔐 OpenAI
# =========================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# 💬 Historial compartido
# =========================
# Un solo historial para ambos modelos — así Angela recuerda
# la conversación sin importar qué motor respondió cada vez.
MAX_HISTORY = 20  # máximo de turnos (user+assistant) a recordar
HISTORY_FILE = "angela_historial.json"  # archivo donde se guarda el historial

def cargar_historial() -> list[dict]:
    """Carga el historial desde disco al arrancar. Si no existe, empieza vacío."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"📂 Historial cargado: {len(data)} turnos desde '{HISTORY_FILE}'")
                return data
        except Exception as e:
            print(f"⚠️  No se pudo cargar el historial: {e} — empezando vacío")
    return []

def guardar_historial(historial: list[dict]):
    """Guarda el historial en disco después de cada respuesta."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(historial, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️  No se pudo guardar el historial: {e}")

# Cargar historial al iniciar el servidor
conversation_history: list[dict] = cargar_historial()

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "Eres una VTuber femenina llamada Angela. "
        "Eres relajada, inteligente,curiosa y bastante agradable con el publico "
        "Respondes de forma breve y amigable en el chat de Twitch. "
        "Recuerda lo que se ha hablado antes y úsalo para dar respuestas coherentes."
    )
}

# =========================
# 🧠 Modelo de sentimiento (español)
# =========================
print("Cargando modelo de sentimiento...")
sentiment_model = pipeline(
    "sentiment-analysis",
    model="pysentimiento/robertuito-sentiment-analysis",
)
print("Modelo de sentimiento listo.")

# =========================
# 📦 Schema de entrada
# =========================
class ChatRequest(BaseModel):
    text: str
    user: str = "viewer"  # nombre del usuario de Twitch que pregunta

# =========================
# 🧠 Detector de complejidad
# =========================
def es_pregunta_pesada(texto: str) -> bool:
    palabras_clave = [
        "explica", "demuestra", "ecuacion", "código", "algoritmo",
        "programa", "función", "diferencia entre", "cómo funciona",
        "qué es", "por qué", "desarrolla", "resume"
    ]
    if len(texto) > 120:
        return True
    if "```" in texto:
        return True
    if any(p in texto.lower() for p in palabras_clave):
        return True
    return False

# =========================
# 🚀 Endpoint principal
# =========================
@app.post("/procesar")
async def procesar(req: ChatRequest):
    global conversation_history

    # 1️⃣ Analizar sentimiento
    sent = sentiment_model(req.text)[0]
    raw_label = sent["label"]
    score = sent["score"]
    label_map = {"POS": "POSITIVE", "NEG": "NEGATIVE", "NEU": "NEUTRAL"}
    label = label_map.get(raw_label.upper(), "NEUTRAL")

    # 2️⃣ Añadir el mensaje del usuario al historial
    # Incluimos el nombre del viewer para que Angela sepa quién habla
    user_msg = {
        "role": "user",
        "content": f"[{req.user}]: {req.text}"
    }
    conversation_history.append(user_msg)

    # 3️⃣ Recortar historial si supera el límite
    if len(conversation_history) > MAX_HISTORY:
        conversation_history = conversation_history[-MAX_HISTORY:]

    # 4️⃣ Armar mensajes completos: system + historial
    messages = [SYSTEM_PROMPT] + conversation_history

    respuesta = ""

    # 5️⃣ Elegir motor según complejidad
    if es_pregunta_pesada(req.text):
        print(f"🧠 OpenAI GPT-4o — '{req.text[:50]}...'")
        try:
            response = client.chat.completions.create(
                model="gpt-4o",  # ✅ más potente que gpt-3.5-turbo
                messages=messages,
                max_tokens=500,  # más espacio para respuestas complejas
            )
            respuesta = response.choices[0].message.content
        except Exception as e:
            print(f"❌ Error OpenAI: {e}")
            respuesta = "Error al conectar con OpenAI 😅"
    else:
        # Intentar con el modelo potente primero, luego fallback al básico
        for modelo in ["mixtral:8x7b", "llama3.1:8b", "llama3"]:
            print(f"🖥️  Ollama [{modelo}] — '{req.text[:50]}'")
            try:
                response = ollama.chat(
                    model=modelo,
                    messages=messages
                )
                respuesta = response["message"]["content"]
                break  # si funcionó, salir del loop
            except Exception as e:
                print(f"⚠️  {modelo} no disponible: {e} — probando siguiente...")
                continue

        if not respuesta:
            respuesta = "No pude conectar con ningún modelo local 😅"

    # 6️⃣ Añadir la respuesta de Angela al historial compartido
    conversation_history.append({
        "role": "assistant",
        "content": respuesta
    })

    # 7️⃣ Persistir en disco para sobrevivir reinicios
    guardar_historial(conversation_history)

    print(f"📜 Historial: {len(conversation_history)} turnos guardados")

    return {
        "respuesta": respuesta,
        "sentimiento": label,
        "score": round(score, 4),
        "modelo_usado": "openai" if es_pregunta_pesada(req.text) else "ollama",
        "historial_turnos": len(conversation_history)
    }

# =========================
# 🗑️ Resetear historial
# =========================
@app.post("/reset")
async def reset_historial():
    """Limpia el historial — útil al inicio de cada stream."""
    global conversation_history
    conversation_history = []
    guardar_historial(conversation_history)
    return {"status": "Historial limpiado ✅"}

# =========================
# ❤️ Health check
# =========================
@app.get("/")
async def health():
    return {
        "status": "Angela IA server corriendo ✅",
        "historial_turnos": len(conversation_history)
    }
