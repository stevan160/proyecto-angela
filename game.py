"""
🎮 game.py — Módulo de juego para Angela
Permite a Angela jugar shooters con teclado + ratón.

⚠️  IMPORTANTE: Usar solo en modos offline / sin anti-cheat.
    VAC (CS2) y Vanguard (Valorant) detectan pyautogui y banean.
    Funciona bien en: CS2 con bots, juegos indie, servidores privados.
"""

import asyncio
import random
import time
import math
import numpy as np
import cv2
import pyautogui
import mss
from ultralytics import YOLO

# =========================
# ⚙️ Configuración
# =========================
pyautogui.FAILSAFE = True       # mover mouse a esquina superior izquierda = parar
pyautogui.PAUSE = 0.01          # pausa mínima entre acciones (segundos)

# Zona segura — Angela no mueve el mouse fuera del área del juego
# Ajusta según tu resolución y posición de la ventana del juego
JUEGO_REGION = {
    "left": 0,
    "top": 0,
    "width": 1920,
    "height": 1080
}

# Sensibilidad del mouse (ajustar según la sensibilidad in-game)
MOUSE_SENS = 1.0

# Controles del juego (cambiar si el juego usa otras teclas)
TECLAS = {
    "adelante":  "w",
    "atras":     "s",
    "izquierda": "a",
    "derecha":   "d",
    "saltar":    "space",
    "agacharse": "ctrl",
    "recargar":  "r",
    "arma1":     "1",
    "arma2":     "2",
    "granada":   "g",
    "usar":      "f",
    "parar":     None   # ninguna tecla — estado de reposo
}

# =========================
# 🎮 Estado del juego
# =========================
jugando = False         # True = Angela está jugando activamente
apuntar_activo = False  # True = hay un enemigo en la mira

# =========================
# 📸 Captura de pantalla del juego
# =========================
def capturar_juego() -> np.ndarray:
    """Captura solo la región del juego."""
    with mss.mss() as sct:
        screenshot = sct.grab(JUEGO_REGION)
        frame = np.array(screenshot)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

# =========================
# 🎯 Detección de enemigos con YOLO
# =========================
def detectar_enemigos(frame: np.ndarray, modelo_yolo: YOLO) -> list[dict]:
    """
    Detecta enemigos en el frame.
    Devuelve lista de dicts con: {x, y, w, h, confianza}

    Para mejores resultados, entrena un modelo YOLO con assets del juego.
    Por defecto usa yolov8n.pt que detecta personas genéricas.
    """
    resultados = modelo_yolo(frame, verbose=False)
    enemigos = []

    for r in resultados:
        for box in r.boxes:
            clase = int(box.cls[0])
            confianza = float(box.conf[0])

            # Clase 0 = "person" en COCO (YOLOv8 genérico)
            # Con un modelo entrenado en el juego, aquí va la clase "enemy"
            if clase == 0 and confianza > 0.55:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                enemigos.append({
                    "x": (x1 + x2) // 2,           # centro X
                    "y": y1 + (y2 - y1) // 4,       # apuntar a la cabeza (1/4 desde arriba)
                    "w": x2 - x1,
                    "h": y2 - y1,
                    "confianza": confianza
                })

    # Ordenar por confianza descendente
    return sorted(enemigos, key=lambda e: e["confianza"], reverse=True)

# =========================
# 🖱️ Movimiento humanizado del mouse
# =========================
def mover_mouse_suave(dx: int, dy: int, pasos: int = 5):
    """
    Mueve el mouse de forma suave con pequeñas variaciones
    para parecer más humano.
    """
    for i in range(pasos):
        # Añadir pequeño ruido aleatorio para naturalidad
        ruido_x = random.randint(-1, 1)
        ruido_y = random.randint(-1, 1)
        paso_x = int((dx / pasos) * MOUSE_SENS) + ruido_x
        paso_y = int((dy / pasos) * MOUSE_SENS) + ruido_y
        pyautogui.moveRel(paso_x, paso_y, duration=0)
        time.sleep(0.005)

def apuntar_a(enemigo: dict):
    """
    Mueve el mouse hacia un enemigo detectado.
    Calcula el delta desde el centro de la pantalla.
    """
    centro_x = JUEGO_REGION["width"] // 2
    centro_y = JUEGO_REGION["height"] // 2

    dx = enemigo["x"] - centro_x
    dy = enemigo["y"] - centro_y

    # Solo mover si el enemigo no está ya centrado
    if abs(dx) > 5 or abs(dy) > 5:
        mover_mouse_suave(dx, dy)

def disparar():
    """Dispara un tiro."""
    pyautogui.click(button="left")

def disparo_rafaga(disparos: int = 3, intervalo: float = 0.1):
    """Dispara en ráfaga controlada."""
    for _ in range(disparos):
        pyautogui.click(button="left")
        time.sleep(intervalo)

# =========================
# 🚶 Movimiento del personaje
# =========================
async def moverse(tecla: str, duracion: float = 0.3):
    """Presiona una tecla de movimiento durante un tiempo."""
    if tecla not in TECLAS or TECLAS[tecla] is None:
        return
    pyautogui.keyDown(TECLAS[tecla])
    await asyncio.sleep(duracion)
    pyautogui.keyUp(TECLAS[tecla])

async def movimiento_evasivo():
    """Movimiento aleatorio para esquivar balas."""
    opciones = ["izquierda", "derecha", "adelante", "atras"]
    tecla = random.choice(opciones)
    await moverse(tecla, duracion=random.uniform(0.2, 0.5))

async def saltar_y_moverse():
    """Salta mientras se mueve — útil para esquivar."""
    pyautogui.keyDown(TECLAS["saltar"])
    await moverse("adelante", duracion=0.3)
    pyautogui.keyUp(TECLAS["saltar"])

# =========================
# 🤖 Bucle principal de juego
# =========================
async def loop_juego(modelo_yolo: YOLO, consultar_modelo_fn, audio_queue, canal_twitch=None):
    """
    Bucle principal de Angela jugando.
    - Detecta enemigos con YOLO
    - Apunta y dispara si hay enemigos
    - Se mueve aleatoriamente si no hay enemigos
    - Comenta lo que ve en el chat de Twitch

    Args:
        modelo_yolo: instancia de YOLO ya cargada
        consultar_modelo_fn: función async para preguntar a la IA
        audio_queue: cola de audio para que Angela hable
        canal_twitch: canal donde mandar mensajes (puede ser None)
    """
    global jugando, apuntar_activo

    print("🎮 Angela empieza a jugar...")
    jugando = True

    ticks_sin_enemigo = 0
    ultimo_comentario = 0

    while jugando:
        try:
            frame = capturar_juego()
            enemigos = detectar_enemigos(frame, modelo_yolo)

            # ========================
            # 🎯 HAY ENEMIGOS — apuntar y disparar
            # ========================
            if enemigos:
                ticks_sin_enemigo = 0
                apuntar_activo = True
                objetivo = enemigos[0]  # el más cercano / mayor confianza

                apuntar_a(objetivo)
                await asyncio.sleep(0.05)  # pequeña pausa para estabilizar

                # Disparar según la distancia al centro
                centro_x = JUEGO_REGION["width"] // 2
                centro_y = JUEGO_REGION["height"] // 2
                distancia = math.hypot(objetivo["x"] - centro_x, objetivo["y"] - centro_y)

                if distancia < 30:
                    # Bien centrado — disparo en ráfaga
                    disparo_rafaga(disparos=3)
                else:
                    # Aún apuntando — un solo disparo
                    disparar()

                # Movimiento evasivo mientras dispara (50% de las veces)
                if random.random() > 0.5:
                    await movimiento_evasivo()

                # Comentar si hace tiempo que no comenta
                ahora = time.time()
                if ahora - ultimo_comentario > 30:
                    respuesta, _ = await consultar_modelo_fn(
                        f"Estoy viendo {len(enemigos)} enemigo(s) en pantalla y estoy apuntando. "
                        "Di algo breve y emocionante como VTuber gamer.",
                        usuario="Angela"
                    )
                    if canal_twitch:
                        await canal_twitch.send(respuesta[:500])
                    await audio_queue.put((respuesta, "Bella"))
                    ultimo_comentario = ahora

            # ========================
            # 🚶 SIN ENEMIGOS — explorar
            # ========================
            else:
                apuntar_activo = False
                ticks_sin_enemigo += 1

                # Movimiento de exploración aleatorio
                accion = random.choices(
                    ["adelante", "izquierda", "derecha", "saltar", "parar"],
                    weights=[50, 20, 20, 5, 5]
                )[0]

                if accion == "saltar":
                    await saltar_y_moverse()
                elif accion != "parar":
                    await moverse(accion, duracion=random.uniform(0.2, 0.6))

                # Si lleva mucho tiempo sin ver enemigos, Angela lo comenta
                ahora = time.time()
                if ticks_sin_enemigo > 20 and ahora - ultimo_comentario > 45:
                    respuesta, _ = await consultar_modelo_fn(
                        "Llevo un rato sin ver enemigos, estoy explorando el mapa. "
                        "Di algo breve y natural como VTuber.",
                        usuario="Angela"
                    )
                    if canal_twitch:
                        await canal_twitch.send(respuesta[:500])
                    await audio_queue.put((respuesta, "Bella"))
                    ultimo_comentario = ahora
                    ticks_sin_enemigo = 0

            await asyncio.sleep(0.05)  # ~20 FPS de decisiones

        except Exception as e:
            print(f"⚠️  Error en loop_juego: {e}")
            await asyncio.sleep(1)

    print("🎮 Angela dejó de jugar.")

def parar_juego():
    """Para el bucle de juego y suelta todas las teclas."""
    global jugando
    jugando = False
    for tecla in TECLAS.values():
        if tecla:
            try:
                pyautogui.keyUp(tecla)
            except Exception:
                pass
    print("🛑 Juego detenido, teclas liberadas.")

