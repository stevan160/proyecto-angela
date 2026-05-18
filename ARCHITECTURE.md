# 📋 ARQUITECTURA — Project Angela

## 🎯 Visión General

**Project Angela** es un sistema de IA conversacional para un VTuber que:
- Responde a comandos de chat en Twitch con inteligencia
- Reproduce voz sintetizada en tiempo real
- Detecta emociones del usuario y cambia expresiones faciales
- Puede jugar videojuegos bajo comando

```
┌─────────────────────────────────────────────────────────────────┐
│                     TWITCH CHAT                                 │
│                    (Input: !ask)                                │
└────────────────────────┬────────────────────────────────────────┘
                         │
                    [Usuario envia msg]
                         │
        ┌────────────────▼────────────────┐
        │      MAIN.PY (Twitch Bot)       │
        │  • Escucha chat                 │
        │  • Analiza sentimiento          │
        │  • Gestiona juegos              │
        └────────┬──────────┬─────────────┘
                 │          │
          [Pregunta]   [Expresión]
                 │          │
        ┌────────▼──────┐  ┌─────────────────┐
        │  SERVER.PY    │  │ VTUBESTUDIO API │
        │  (IA Backend) │  │  (Avatar)       │
        │               │  └─────────────────┘
        │  • Ollama ──┐ │
        │  • OpenAI ─┤ │
        │  • Historial│ │
        └────────┬──────┘
                 │
          [Respuesta IA]
                 │
        ┌────────▼──────────────┐
        │    ELEVENLABS TTS     │
        │    (Audio synthesis)  │
        └────────┬──────────────┘
                 │
        ┌────────▼──────────────┐
        │ AUDIO QUEUE WORKER    │
        │ (Evita solapamiento)  │
        └───────────────────────┘
```

---

## 📦 Componentes Principales

### 1️⃣ **main.py** — Bot de Twitch
**Responsabilidad**: Interfaz principal, interacción con usuarios

- `class Bot(commands.Bot)`: Bot de Twitch asincrónico
- `event_message()`: Procesa mensajes del chat
- `consultar_modelo()`: Orquesta la IA (servidor local → fallback OpenAI)
- `audio_worker()`: Queue para evitar solapamiento de audio
- `loop_vision()`: Captura pantalla (preparado para análisis futuro)

**Comandos disponibles**:
```
!ask <pregunta>    → Consulta a Angela
!jugar             → Inicia juego shooter (solo streamer)
!minecraft         → Inicia juego Minecraft (solo streamer)
!parar             → Para cualquier juego (solo streamer)
!historial         → Muestra cuántos turnos recuerda Angela
!olvida            → Limpia historial (solo streamer)
```

**Flujo de evento de mensaje**:
1. Recibe mensaje de Twitch
2. Analiza sentimiento con DistilBERT
3. Activa expresión facial en VTube Studio
4. Si es comando, ejecuta lógica específica
5. Si es !ask, consulta IA (servidor → OpenAI fallback)
6. Encola audio en worker asincrónico

---

### 2️⃣ **server.py** — Backend de IA (FastAPI)
**Responsabilidad**: Gestionar IA, historial y elegir modelo

**Endpoints**:
```
POST /procesar
  Input:  {"text": "pregunta", "user": "nombre_usuario"}
  Output: {
    "respuesta": "texto",
    "sentimiento": "POSITIVE|NEGATIVE|NEUTRAL",
    "modelo_usado": "openai|ollama",
    "historial_turnos": 42
  }

POST /reset
  Output: {"status": "Historial limpiado ✅"}

GET /
  Output: {"status": "Angela IA server corriendo ✅", "historial_turnos": 42}
```

**Lógica de decisión de modelo**:
```python
if es_pregunta_pesada(texto):  # Detecta palabras clave, longitud > 120
    → Usar OpenAI GPT-4o (más potente, respuestas largas)
else:
    → Intentar Ollama (Mixtral > Llama3.1 > Llama3)
    → Si falla, fallback OpenAI
```

**Historial persistente**:
- Se guarda en `angela_historial.json` después de cada respuesta
- Máximo 20 turnos en memor ia
- Se carga al iniciar el servidor
- Se limpia con endpoint `/reset`

---

### 3️⃣ **game.py & game_minecraft.py** — Control de Juegos
**Responsabilidad**: Automatización de gameplay

- `loop_juego()`: Control automático de shooter
- `loop_minecraft()`: Control automático de minería
- Uso de PyAutoGUI para input (teclado/ratón)
- Uso de YOLO para detección de objetos
- Uso de pytesseract para OCR (HUD de Minecraft)

---

### 4️⃣ **game.py** (importación no usada)
⚠️ **TODO**: El modelo YOLO se importa en main.py pero no se usa en la práctica.
- Futuro: Analizar frames de pantalla para mejorar gameplay
- Alternativa: Remover si no es necesario

---

## 🔄 Flujos de Datos

### Flujo 1: Pregunta de Usuario → Respuesta
```
Chat Twitch
    ↓
main.py: event_message()
    ↓
Analizar sentimiento → Cambiar expresión VTS
    ↓
consultar_modelo()
    ├─→ POST http://192.168.1.50:8000/procesar
    │       ├─→ Detecta complejidad
    │       ├─→ Ollama (rápido) o OpenAI (preciso)
    │       └─→ Guarda respuesta en historial
    │
    └─→ Si falla: Fallback OpenAI con historial local
    ↓
audio_queue.put((respuesta, voz))
    ↓
audio_worker() → ElevenLabs TTS → Play audio
    ↓
Enviar a Twitch (primeros 500 chars)
```

### Flujo 2: Juego (Shooter/Minecraft)
```
!jugar / !minecraft (usuario)
    ↓
Iniciar asyncio.create_task(game.loop_juego/loop_minecraft)
    ↓
Capturar pantalla cada 5ms
    ↓
Analizar con YOLO/Tesseract
    ↓
Ejecutar input (PyAutoGUI)
    ↓
Si detecta muerte/victoria/comando !parar → Detener
```

---

## 🔐 Variables de Entorno Críticas

Ver `.env.example` para lista completa.

**Esenciales**:
```env
TWITCH_TOKEN=oauth_token
TWITCH_CHANNEL=canal
OPENAI_API_KEY=sk-xxx
ELEVENLABS_API_KEY=xxx
IA_SERVER_URL=http://192.168.1.50:8000
```

---

## 📊 Stack Tecnológico

| Componente | Tecnología | Propósito |
|-----------|-----------|----------|
| Bot Twitch | Twitchio | Conexión a chat |
| LLM Principal | Ollama + Transformer | IA rápida local |
| LLM Premium | OpenAI GPT-4o | Preguntas complejas |
| TTS | ElevenLabs + pyttsx3 | Voz sintetizada |
| Avatar | VTube Studio API | Control de expresiones |
| Sentimiento | DistilBERT-SST2 | Análisis emocional |
| Detección | YOLOv8 | Objetos en pantalla |
| OCR | pytesseract/Tesseract | Lectura HUD |
| Automatización | PyAutoGUI | Control mouse/teclado |
| Backend | FastAPI | API del servidor IA |
| Base de datos | JSON | Historial persistente |

---

## 🚀 Deployment

### Desarrollo Local
```bash
# Terminal 1: Servidor IA
cd proyecto-angela
pip install -r requeriments-servidor.txt
python server.py  # http://localhost:8000

# Terminal 2: Bot Twitch
pip install -r requeriments-pc.txt
python main.py
```

### Red Local (Recomendado)
```bash
# Server en PC potente (con Ollama)
python server.py

# Bot en otra PC (menos requisitos)
python main.py  # Conecta a http://192.168.1.50:8000
```

---

## 🐛 Troubleshooting

| Error | Causa | Solución |
|-------|-------|----------|
| `Connection refused 192.168.1.50:8000` | Server IA no está corriendo | Inicia `python server.py` en otra terminal |
| `Ollama model not found` | Modelo no descargado | `ollama pull mixtral:8x7b` |
| `ElevenLabs timeout` | API lenta/caída | Fallback a pyttsx3 automático |
| `VTube Studio connection error` | VTS no abierto | Abre VTube Studio en otra ventana |
| `Tesseract not found` | OCR no instalado | Ver requeriments-pc.txt para instrucciones |
| `CUDA not available` | GPU no detectada | YOLO usa CPU (lento) |

---

## 📝 Mejoras Futuras

- [ ] Logging centralizado (actual: solo print)
- [ ] Métricas de latencia y uso de modelos
- [ ] Caching de respuestas frecuentes
- [ ] Tests unitarios para server.py
- [ ] Dashboard de estadísticas en tiempo real
- [ ] Soporte para múltiples streams
