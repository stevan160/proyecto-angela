from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import pipeline
from openai import OpenAI
import ollama
import os

load_dotenv()

app = FastAPI()

# =========================
# 🔐 OpenAI (solo si lo necesitas)
# =========================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# 🧠 Modelo de sentimiento
# =========================
sentiment_model = pipeline(
    "sentiment-analysis",
    model="distilbert-base-uncased-finetuned-sst-2-spanish",
)

class ChatRequest(BaseModel):
    text: str

# =========================
# 🧠 Detector simple de complejidad
# =========================
def es_pregunta_pesada(texto: str):

    palabras_clave = ["explica", "demuestra", "ecuacion", "código", "algoritmo"]

    if len(texto) > 30:
        return True

    if any(p in texto.lower() for p in palabras_clave):
        return True

    if "```" in texto:
        return True

    return False


@app.post("/procesar")
async def procesar(req: ChatRequest):

    # 1️⃣ Sentimiento
    sent = sentiment_model(req.text)[0]
    label = sent["label"]
    score = sent["score"]

    respuesta = ""

    # 2️⃣ Decidir motor IA
    if es_pregunta_pesada(req.text):
        print("Usando OpenAI (pregunta pesada)")

        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres una VTuber femenina llamada angela,eres relajada,inteligente y curiosa independiente que vive en el stream."},
                    {"role": "user", "content": req.text}
                ],
                max_tokens=4096,
            )

            respuesta = response.choices[0].message.content

        except Exception as e:
            print("Error OpenAI:", e)
            respuesta = "Error en OpenAI"

    else:
        print("Usando Ollama (local)")

        try:
            response = ollama.chat(
                model="llama3",
                messages=[
                    {"role": "system", "content": "Eres una VTuber femenina llamada Angela. Eres relajada, inteligente y curiosa. Respondes de forma breve y amigable."},
                    {"role": "user", "content": req.text}
                ]
            )

            respuesta = response["message"]["content"]

        except Exception as e:
            print("Error Ollama:", e)
            respuesta = "Error en Ollama 😅"

    return {
        "respuesta": respuesta,
        "sentimiento": label,
        "score": score
    }


# ❤️ Health check
@app.get("/")
async def health():
    return {"status": "Angela IA server corriendo ✅"}