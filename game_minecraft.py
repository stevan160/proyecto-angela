"""
⛏️  game_minecraft.py — Módulo de Minecraft para Angela
Angela juega Minecraft analizando la pantalla con YOLO + OCR,
decidiendo qué hacer con la IA y ejecutando acciones con pyautogui.

Estados del juego:
    - EXPLORAR   → caminar, mirar alrededor
    - MINAR      → romper bloques
    - CONSTRUIR  → colocar bloques
    - COMBATIR   → atacar enemigos
    - SOBREVIVIR → buscar comida, refugio (vida/hambre baja)
    - CRAFTEAR   → abrir crafting table / inventario
"""

import asyncio
import random
import time
import re
import numpy as np
import cv2
import pyautogui
import mss
from ultralytics import YOLO

try:
    import pytesseract
    OCR_DISPONIBLE = True
except ImportError:
    OCR_DISPONIBLE = False
    print("⚠️  pytesseract no instalado — Angela no podrá leer texto en pantalla.")
    print("   Instalar: pip install pytesseract")

# =========================
# ⚙️ Configuración
# =========================
pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.05

JUEGO_REGION = {"left": 0, "top": 0, "width": 1920, "height": 1080}

# Controles de Minecraft (estándar)
TECLAS = {
    "adelante":   "w",
    "atras":      "s",
    "izquierda":  "a",
    "derecha":    "d",
    "saltar":     "space",
    "agacharse":  "shift",
    "correr":     "ctrl",       # sprint en Java Edition
    "inventario": "e",
    "craftear":   "e",          # misma tecla, abre inventario con crafting
    "tirar":      "q",
    "slot1":      "1",          # espada / hacha
    "slot2":      "2",          # pico
    "slot3":      "3",          # pala
    "slot4":      "4",          # comida
    "slot5":      "5",          # bloques
    "chat":       "t",
    "pausa":      "escape",
}

# =========================
# 🗺️ Estados del juego
# =========================
ESTADOS = ["EXPLORAR", "MINAR", "CONSTRUIR", "COMBATIR", "SOBREVIVIR", "CRAFTEAR"]

class EstadoJuego:
    def __init__(self):
        self.estado        = "EXPLORAR"
        self.vida          = 20       # 0-20 (10 corazones)
        self.hambre        = 20       # 0-20 (10 muslos de pollo)
        self.es_de_dia     = True
        self.enemigos_cerca = False
        self.ticks         = 0
        self.ultimo_cambio = time.time()

estado = EstadoJuego()
jugando = False

# =========================
# 📸 Captura y análisis
# =========================
def capturar_juego() -> np.ndarray:
    with mss.mss() as sct:
        shot = sct.grab(JUEGO_REGION)
        frame = np.array(shot)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

def leer_hud(frame: np.ndarray) -> dict:
    """
    Intenta leer vida y hambre del HUD de Minecraft con OCR.
    Minecraft Java muestra iconos, no números — usamos zonas del HUD.
    Devuelve un dict con lo que pudo detectar.
    """
    info = {"vida": estado.vida, "hambre": estado.hambre}

    if not OCR_DISPONIBLE:
        return info

    h, w = frame.shape[:2]

    # Zona del HUD (barra inferior central)
    hud = frame[int(h * 0.88):int(h * 0.98), int(w * 0.35):int(w * 0.65)]
    gris = cv2.cvtColor(hud, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gris, 180, 255, cv2.THRESH_BINARY)

    try:
        texto = pytesseract.image_to_string(thresh, config="--psm 7 digits")
        numeros = re.findall(r"\d+", texto)
        if len(numeros) >= 2:
            info["vida"]   = min(int(numeros[0]), 20)
            info["hambre"] = min(int(numeros[1]), 20)
    except Exception:
        pass

    return info

def detectar_enemigos_mc(frame: np.ndarray, yolo: YOLO) -> list[dict]:
    """
    Detecta mobs hostiles en pantalla.
    Con yolov8 genérico detecta personas (creepers, zombies tienen forma humanoide).
    Para mejor precisión: entrenar con screenshots de Minecraft.
    """
    resultados = yolo(frame, verbose=False)
    enemigos = []
    for r in resultados:
        for box in r.boxes:
            clase     = int(box.cls[0])
            confianza = float(box.conf[0])
            if clase == 0 and confianza > 0.50:  # clase 0 = person
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                enemigos.append({
                    "x": (x1 + x2) // 2,
                    "y": y1 + (y2 - y1) // 3,
                    "confianza": confianza
                })
    return sorted(enemigos, key=lambda e: e["confianza"], reverse=True)

def es_de_noche(frame: np.ndarray) -> bool:
    """Detecta si es de noche midiendo el brillo promedio del cielo."""
    h = frame.shape[0]
    cielo = frame[:int(h * 0.3), :]  # tercio superior = cielo
    brillo = cv2.cvtColor(cielo, cv2.COLOR_BGR2GRAY).mean()
    return brillo < 60  # oscuro = noche

# =========================
# 🎮 Acciones básicas
# =========================
async def moverse(tecla: str, duracion: float = 0.4):
    key = TECLAS.get(tecla)
    if key:
        pyautogui.keyDown(key)
        await asyncio.sleep(duracion)
        pyautogui.keyUp(key)

async def saltar():
    pyautogui.press(TECLAS["saltar"])
    await asyncio.sleep(0.1)

async def mirar(dx: int = 0, dy: int = 0):
    """Gira la cámara moviendo el mouse."""
    pyautogui.moveRel(dx, dy, duration=0.05)

async def minar_bloque():
    """Mantiene click izquierdo para romper el bloque delante."""
    pyautogui.mouseDown(button="left")
    await asyncio.sleep(random.uniform(0.8, 1.5))
    pyautogui.mouseUp(button="left")

async def colocar_bloque():
    """Click derecho para colocar bloque."""
    pyautogui.click(button="right")
    await asyncio.sleep(0.1)

async def atacar():
    """Click izquierdo para atacar."""
    pyautogui.click(button="left")
    await asyncio.sleep(0.15)

async def seleccionar_slot(slot: str):
    """Cambia al slot del inventario indicado."""
    pyautogui.press(TECLAS[slot])
    await asyncio.sleep(0.05)

async def abrir_inventario():
    pyautogui.press(TECLAS["inventario"])
    await asyncio.sleep(0.3)

async def cerrar_inventario():
    pyautogui.press(TECLAS["pausa"])
    await asyncio.sleep(0.2)

# =========================
# 🧠 Lógica por estado
# =========================
async def accion_explorar():
    """Camina hacia adelante, gira ocasionalmente, salta obstáculos."""
    accion = random.choices(
        ["adelante", "girar_izq", "girar_der", "saltar_adelante", "mirar_arriba"],
        weights=[55, 15, 15, 10, 5]
    )[0]

    if accion == "adelante":
        await moverse("adelante", random.uniform(0.5, 1.5))

    elif accion == "girar_izq":
        await mirar(dx=random.randint(-60, -20))
        await moverse("adelante", 0.5)

    elif accion == "girar_der":
        await mirar(dx=random.randint(20, 60))
        await moverse("adelante", 0.5)

    elif accion == "saltar_adelante":
        pyautogui.keyDown(TECLAS["adelante"])
        await saltar()
        await asyncio.sleep(0.3)
        pyautogui.keyUp(TECLAS["adelante"])

    elif accion == "mirar_arriba":
        await mirar(dy=random.randint(-30, -10))
        await asyncio.sleep(0.3)
        await mirar(dy=random.randint(10, 30))  # volver a mirar al frente

async def accion_minar():
    """Mira hacia abajo/frente y mina bloques."""
    await seleccionar_slot("slot2")  # pico
    await mirar(dy=random.randint(10, 25))   # mirar un poco hacia abajo
    await minar_bloque()
    await moverse("adelante", 0.2)

async def accion_construir():
    """Coloca bloques mirando al suelo."""
    await seleccionar_slot("slot5")  # bloques
    await mirar(dy=40)               # mirar al suelo
    await colocar_bloque()
    await moverse("adelante", 0.3)
    await mirar(dy=-40)              # volver a mirar al frente

async def accion_combatir(enemigos: list[dict]):
    """Apunta al enemigo más cercano y ataca."""
    await seleccionar_slot("slot1")  # espada
    if enemigos:
        objetivo = enemigos[0]
        cx = JUEGO_REGION["width"] // 2
        cy = JUEGO_REGION["height"] // 2
        dx = (objetivo["x"] - cx) // 4
        dy = (objetivo["y"] - cy) // 4
        await mirar(dx=dx, dy=dy)
    await atacar()
    # Retroceder y saltar para esquivar
    if random.random() > 0.5:
        await moverse("atras", 0.3)
    if random.random() > 0.7:
        await saltar()

async def accion_sobrevivir():
    """Cuando vida o hambre están bajas: busca comida o corre al refugio."""
    await seleccionar_slot("slot4")  # comida
    pyautogui.mouseDown(button="right")  # comer (mantener clic derecho)
    await asyncio.sleep(2.0)
    pyautogui.mouseUp(button="right")
    # Alejarse de posibles peligros
    await moverse("atras", 0.5)
    await saltar()

# =========================
# 🔄 Decidir estado según contexto
# =========================
def actualizar_estado(info_hud: dict, enemigos: list, es_noche: bool):
    """Actualiza el estado de Angela según lo que ve en pantalla."""
    global estado

    estado.vida    = info_hud.get("vida", estado.vida)
    estado.hambre  = info_hud.get("hambre", estado.hambre)
    estado.enemigos_cerca = len(enemigos) > 0
    estado.es_de_dia = not es_noche

    # Prioridad de estados
    if estado.vida < 6:                         # menos de 3 corazones → sobrevivir
        nuevo = "SOBREVIVIR"
    elif estado.hambre < 6:                     # hambre baja → sobrevivir
        nuevo = "SOBREVIVIR"
    elif estado.enemigos_cerca:                 # hay enemigos → combatir
        nuevo = "COMBATIR"
    elif es_noche:                              # de noche → minar (seguro bajo tierra)
        nuevo = "MINAR"
    else:
        # De día sin peligros: alternar entre explorar, minar y construir
        if estado.ticks % 60 < 35:
            nuevo = "EXPLORAR"
        elif estado.ticks % 60 < 50:
            nuevo = "MINAR"
        else:
            nuevo = "CONSTRUIR"

    if nuevo != estado.estado:
        print(f"🗺️  Estado: {estado.estado} → {nuevo}")
        estado.estado = nuevo
        estado.ultimo_cambio = time.time()

    estado.ticks += 1

# =========================
# 🤖 Bucle principal de Minecraft
# =========================
async def loop_minecraft(yolo: YOLO, consultar_modelo_fn, audio_queue, canal_twitch=None):
    """
    Bucle principal de Angela jugando Minecraft.
    Analiza pantalla, actualiza estado y ejecuta acciones.
    """
    global jugando
    jugando = True
    ultimo_comentario = 0

    print("⛏️  Angela empieza a jugar Minecraft...")

    while jugando:
        try:
            frame        = capturar_juego()
            info_hud     = leer_hud(frame)
            enemigos     = detectar_enemigos_mc(frame, yolo)
            noche        = es_de_noche(frame)

            actualizar_estado(info_hud, enemigos, noche)

            # Ejecutar acción según estado actual
            if estado.estado == "EXPLORAR":
                await accion_explorar()

            elif estado.estado == "MINAR":
                await accion_minar()

            elif estado.estado == "CONSTRUIR":
                await accion_construir()

            elif estado.estado == "COMBATIR":
                await accion_combatir(enemigos)

            elif estado.estado == "SOBREVIVIR":
                await accion_sobrevivir()

            # Comentar en el chat periódicamente
            ahora = time.time()
            if ahora - ultimo_comentario > 40:
                contexto = (
                    f"Estoy jugando Minecraft. "
                    f"Estado actual: {estado.estado}. "
                    f"Vida: {estado.vida}/20, Hambre: {estado.hambre}/20. "
                    f"{'Es de noche' if noche else 'Es de día'}. "
                    f"{'Hay enemigos cerca!' if estado.enemigos_cerca else 'Sin enemigos cerca.'} "
                    f"Di algo breve y natural como VTuber gamer."
                )
                respuesta, _ = await consultar_modelo_fn(contexto, usuario="Angela")
                if canal_twitch:
                    await canal_twitch.send(respuesta[:500])
                await audio_queue.put((respuesta, "Bella"))
                ultimo_comentario = ahora

            await asyncio.sleep(0.05)

        except Exception as e:
            print(f"⚠️  Error loop Minecraft: {e}")
            await asyncio.sleep(1)

    print("⛏️  Angela dejó de jugar Minecraft.")

def parar_minecraft():
    """Para el juego y libera todas las teclas."""
    global jugando
    jugando = False
    for tecla in TECLAS.values():
        if tecla:
            try:
                pyautogui.keyUp(tecla)
            except Exception:
                pass
    pyautogui.mouseUp(button="left")
    pyautogui.mouseUp(button="right")
    print("🛑 Minecraft detenido.")
