# 🚀 SETUP GUIDE — Project Angela

## 📋 Requisitos Previos

- **Python 3.9+** → [Download](https://www.python.org/)
- **Git** → [Download](https://git-scm.com/)
- **Ollama** (opcional, pero recomendado) → [Download](https://ollama.com/)
- **Tesseract OCR** (para Minecraft) → [Windows Setup](https://github.com/UB-Mannheim/tesseract/wiki)

---

## 🛠️ Instalación Step-by-Step

### 1️⃣ Clonar Repositorio

```bash
git clone https://github.com/stevan160/proyecto-angela.git
cd proyecto-angela
```

### 2️⃣ Crear Entorno Virtual (Recomendado)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3️⃣ Instalar Dependencias

**Solo para el Bot Twitch**:
```bash
pip install -r requeriments-pc.txt
```

**Solo para el Servidor IA**:
```bash
pip install -r requeriments-servidor.txt
# Luego, descargar modelos de Ollama:
ollama pull mixtral:8x7b
ollama pull llama3.1:8b
ollama pull llama3
```

**Para Desarrollo**:
```bash
pip install -r requirements-dev.txt
```

### 4️⃣ Configurar Variables de Entorno

```bash
# Copiar template
cp .env.example .env

# Editar con tus credenciales
# (usa tu editor favorito)
notepad .env   # Windows
nano .env      # Linux/Mac
```

**Variables esenciales a completar**:
```env
TWITCH_TOKEN=oauth_token_aqui
TWITCH_CHANNEL=tu_canal
OPENAI_API_KEY=sk-xxx
ELEVENLABS_API_KEY=xxx
IA_SERVER_URL=http://192.168.1.50:8000
```

Ver `.env.example` para descripción completa de cada variable.

---

## 🚀 Ejecutar Project Angela

### Opción A: Localhost (Todo en una PC)

**Terminal 1 - Servidor IA**:
```bash
pip install -r requeriments-servidor.txt
python server.py
# Debería ver: "Application startup complete"
```

**Terminal 2 - Bot Twitch**:
```bash
# Cambiar en .env: IA_SERVER_URL=http://localhost:8000
pip install -r requeriments-pc.txt
python main.py
# Debería ver: "Bot conectado como [tu_bot_name]"
```

### Opción B: Red Local (Recomendado - PC diferente para Server)

**En PC 1 (Servidor IA - puede ser más potente)**:
```bash
python server.py
# El server escucha en http://0.0.0.0:8000
# Otros PCs se conectan via: http://192.168.1.50:8000
```

**En PC 2 (Bot Twitch)**:
```bash
# En .env, set: IA_SERVER_URL=http://192.168.1.50:8000
# (cambia 192.168.1.50 a la IP de tu servidor)
python main.py
```

**Encontrar IP del servidor**:
```bash
# Windows
ipconfig
# Busca "IPv4 Address" en tu red local

# Linux/Mac
ifconfig
```

---

## ✅ Verificar que Funciona

### Server IA
```bash
# Si todo está bien:
# ✅ Modelo de sentimiento listo
# ✅ Application startup complete
# ✅ Listening on http://0.0.0.0:8000

# Test desde otra terminal:
curl http://localhost:8000
# Debería responder: {"status":"Angela IA server corriendo ✅",...}
```

### Bot Twitch
```bash
# Si todo está bien:
# ✅ Bot conectado como [tu_bot_name]
# ✅ Cola de audio iniciada
# ✅ Vision loop iniciado
# ✅ Conectado a VTube Studio

# Entra a tu chat de Twitch y escribe:
# !historial   → Te mostrará cuántos mensajes recuerda
# !ask hola    → Angela debería responder
```

---

## 🎮 Dependencias Especiales

### Tesseract OCR (para Minecraft)

**Windows**:
1. Descargar installer: https://github.com/UB-Mannheim/tesseract/wiki
2. Instalar en ruta por defecto: `C:\Program Files\Tesseract-OCR`
3. En `game_minecraft.py`, si no lo detecta automáticamente:
```python
pytesseract.pytesseract.pytesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

**Linux**:
```bash
sudo apt install tesseract-ocr
```

**Mac**:
```bash
brew install tesseract
```

### Ollama (Modelos Locales)

1. Instalar desde https://ollama.com/
2. Descargar modelos:
```bash
ollama pull mixtral:8x7b     # ~13GB, recomendado
ollama pull llama3.1:8b      # ~6GB
ollama pull llama3           # ~4GB
```
3. Verificar que funciona:
```bash
ollama serve  # Debería escuchar en http://localhost:11434
```

### CUDA (GPU Acceleration - Opcional)

Si quieres YOLO + Ollama rápido:

**NVIDIA**:
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**AMD**:
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm5.7
```

---

## 🔧 Troubleshooting Setup

| Problema | Solución |
|---------|----------|
| `ModuleNotFoundError: No module named 'X'` | Ejecutaste `pip install -r requeriments-pc.txt`? |
| `Connection refused` (server) | ¿Está corriendo `python server.py` en otra terminal? |
| `TWITCH_TOKEN not found` | Copió `.env` desde `.env.example` y lo completó? |
| `Ollama model not found` | Ejecutó `ollama pull mixtral:8x7b`? |
| `VTube Studio connection error` | ¿Está abierto VTube Studio? API debe estar habilitada |
| `pytesseract: Command not found` | Instalar Tesseract (ver sección OCR arriba) |

---

## 📊 Comandos Útiles

```bash
# Limpiar cache Python
find . -type d -name __pycache__ -exec rm -r {} +
find . -type f -name "*.pyc" -delete

# Listar variables de entorno cargadas
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('TWITCH_TOKEN')[:20]+'...')"

# Testear conexión a servidor IA
curl -X POST http://localhost:8000/procesar \
  -H "Content-Type: application/json" \
  -d '{"text":"Hola Angela", "user":"test_user"}'

# Ver logs en tiempo real (Linux)
tail -f angela_historial.json | jq .

# Activar virtual env con alias (opcional)
alias angela_env="source venv/bin/activate"  # Linux/Mac
```

---

## 🎯 Próximos Pasos

1. **Personalizar el avatar**: Cambiar expresiones en game.py, game_minecraft.py
2. **Ajustar prompts**: Editar `SYSTEM_PROMPT` en server.py
3. **Agregar comandos**: Crear nuevos en main.py `event_message()`
4. **Setup de CI/CD**: Crear `.github/workflows/` para testing automático

---

## 📚 Recursos

- [Twitchio Docs](https://twitchio.dev/)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Ollama Models](https://ollama.com/library)
- [OpenAI API](https://platform.openai.com/docs)
- [ElevenLabs Voices](https://elevenlabs.io/docs)
- [VTube Studio API](https://github.com/Inzanity/VTS-Python)

---

## ❓ Preguntas Frecuentes

**P: ¿Puedo usar otros modelos de Ollama?**
R: Sí. En `server.py`, línea 140, cambia la lista de modelos a intentar.

**P: ¿Cómo cambio la voz de Angela?**
R: En main.py, `await audio_queue.put((respuesta, "voz_nombre"))`. Ver voces en ElevenLabs.

**P: ¿Qué pasa si Ollama está caído?**
R: El bot automáticamente usa OpenAI como fallback (si tienes API key).

**P: ¿Cómo agrego más comandos de Twitch?**
R: En main.py `event_message()`, agregar más bloques `if message.content.startswith("!comando")`.

**P: ¿Puedo hosted en la nube?**
R: Sí, deploy el server en Railway, Render, etc. Solo actualiza `IA_SERVER_URL` en .env
