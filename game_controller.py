"""
🎮 game_controller.py — Controlador unificado de juegos para Angela

Módulo que consolida la lógica de gameplay para ambos juegos:
  - Shooter: Detección de enemigos, apuntado, disparo
  - Minecraft: Estados (explorar, minar, combatir, etc.), OCR del HUD

Uso:
  from game_controller import GameController, GameType
  
  gc = GameController(GameType.SHOOTER)
  await gc.play(yolo_model, ai_fn, audio_queue, twitch_channel)
"""

import asyncio
import random
import time
import math
import re
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Optional, Any

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

# =========================
# 🔧 Configuración Global
# =========================
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.01

JUEGO_REGION = {"left": 0, "top": 0, "width": 1920, "height": 1080}
MOUSE_SENS = 1.0


class GameType(Enum):
    """Tipos de juegos soportados."""
    SHOOTER = "shooter"
    MINECRAFT = "minecraft"


# =========================
# ⚙️ Configuración por Juego
# =========================
TECLAS_SHOOTER = {
    "adelante": "w",
    "atras": "s",
    "izquierda": "a",
    "derecha": "d",
    "saltar": "space",
    "agacharse": "ctrl",
    "recargar": "r",
    "parar": None,
}

TECLAS_MINECRAFT = {
    "adelante": "w",
    "atras": "s",
    "izquierda": "a",
    "derecha": "d",
    "saltar": "space",
    "agacharse": "shift",
    "correr": "ctrl",
    "inventario": "e",
    "tirar": "q",
    "slot1": "1",  # espada
    "slot2": "2",  # pico
    "slot3": "3",  # pala
    "slot4": "4",  # comida
    "slot5": "5",  # bloques
    "pausa": "escape",
}

ESTADOS_MINECRAFT = ["EXPLORAR", "MINAR", "CONSTRUIR", "COMBATIR", "SOBREVIVIR"]


@dataclass
class GameState:
    """Estado del juego actual."""
    jugando: bool = False
    estado: str = "EXPLORAR"  # para Minecraft
    vida: int = 20
    hambre: int = 20
    es_de_dia: bool = True
    enemigos_cerca: bool = False
    ticks: int = 0


# =========================
# 📸 Funciones Compartidas
# =========================
def capturar_pantalla() -> np.ndarray:
    """Captura la región del juego."""
    with mss.mss() as sct:
        screenshot = sct.grab(JUEGO_REGION)
        frame = np.array(screenshot)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)


def detectar_enemigos(frame: np.ndarray, yolo: YOLO, confianza_min: float = 0.55) -> list[dict]:
    """
    Detección genérica de enemigos con YOLO.
    Retorna lista de dict: {x, y, w, h, confianza}
    """
    resultados = yolo(frame, verbose=False)
    enemigos = []

    for r in resultados:
        for box in r.boxes:
            clase = int(box.cls[0])
            confianza = float(box.conf[0])

            if clase == 0 and confianza > confianza_min:  # clase 0 = person
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                enemigos.append({
                    "x": (x1 + x2) // 2,
                    "y": y1 + (y2 - y1) // 4,
                    "w": x2 - x1,
                    "h": y2 - y1,
                    "confianza": confianza,
                })

    return sorted(enemigos, key=lambda e: e["confianza"], reverse=True)


def mover_mouse_suave(dx: int, dy: int, pasos: int = 5):
    """Movimiento suave del mouse con ruido para parecer humano."""
    for _ in range(pasos):
        ruido_x = random.randint(-1, 1)
        ruido_y = random.randint(-1, 1)
        paso_x = int((dx / pasos) * MOUSE_SENS) + ruido_x
        paso_y = int((dy / pasos) * MOUSE_SENS) + ruido_y
        pyautogui.moveRel(paso_x, paso_y, duration=0)
        time.sleep(0.005)


async def moverse_async(tecla: str, teclas_dict: dict, duracion: float = 0.3):
    """Presiona una tecla de movimiento durante un tiempo."""
    if tecla not in teclas_dict or teclas_dict[tecla] is None:
        return
    pyautogui.keyDown(teclas_dict[tecla])
    await asyncio.sleep(duracion)
    pyautogui.keyUp(teclas_dict[tecla])


def detener_teclas(teclas_dict: dict):
    """Suelta todas las teclas presionadas."""
    for tecla in teclas_dict.values():
        if tecla:
            try:
                pyautogui.keyUp(tecla)
            except Exception:
                pass


# =========================
# 🎯 Funciones Shooter
# =========================
async def shooter_apuntar_y_disparar(enemigos: list[dict]) -> bool:
    """
    Apunta y dispara hacia el enemigo más cercano.
    Retorna True si disparó, False si no hay enemigos.
    """
    if not enemigos:
        return False

    objetivo = enemigos[0]
    centro_x = JUEGO_REGION["width"] // 2
    centro_y = JUEGO_REGION["height"] // 2

    dx = objetivo["x"] - centro_x
    dy = objetivo["y"] - centro_y

    if abs(dx) > 5 or abs(dy) > 5:
        mover_mouse_suave(dx, dy)

    await asyncio.sleep(0.05)

    distancia = math.hypot(dx, dy)
    if distancia < 30:
        for _ in range(3):
            pyautogui.click(button="left")
            time.sleep(0.1)
    else:
        pyautogui.click(button="left")

    return True


async def shooter_movimiento_evasivo(teclas: dict):
    """Movimiento aleatorio para esquivar."""
    accion = random.choice(["izquierda", "derecha", "adelante", "atras"])
    await moverse_async(accion, teclas, duracion=random.uniform(0.2, 0.5))


# =========================
# ⛏️ Funciones Minecraft
# =========================
def leer_hud_minecraft(frame: np.ndarray, estado: GameState) -> dict:
    """Lee vida y hambre del HUD con OCR (si disponible)."""
    info = {"vida": estado.vida, "hambre": estado.hambre}

    if not OCR_DISPONIBLE:
        return info

    h, w = frame.shape[:2]
    hud = frame[int(h * 0.88) : int(h * 0.98), int(w * 0.35) : int(w * 0.65)]
    gris = cv2.cvtColor(hud, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gris, 180, 255, cv2.THRESH_BINARY)

    try:
        texto = pytesseract.image_to_string(thresh, config="--psm 7 digits")
        numeros = re.findall(r"\d+", texto)
        if len(numeros) >= 2:
            info["vida"] = min(int(numeros[0]), 20)
            info["hambre"] = min(int(numeros[1]), 20)
    except Exception:
        pass

    return info


def es_de_noche(frame: np.ndarray) -> bool:
    """Detecta si es de noche midiendo brillo del cielo."""
    h = frame.shape[0]
    cielo = frame[: int(h * 0.3), :]
    brillo = cv2.cvtColor(cielo, cv2.COLOR_BGR2GRAY).mean()
    return brillo < 60


async def minecraft_accion_explorar(teclas: dict):
    """Movimiento de exploración para Minecraft."""
    accion = random.choices(
        ["adelante", "girar_izq", "girar_der", "saltar_adelante"],
        weights=[55, 20, 20, 5],
    )[0]

    if accion == "adelante":
        await moverse_async("adelante", teclas, random.uniform(0.5, 1.5))
    elif accion == "girar_izq":
        pyautogui.moveRel(random.randint(-60, -20), 0, duration=0.1)
        await moverse_async("adelante", teclas, 0.5)
    elif accion == "girar_der":
        pyautogui.moveRel(random.randint(20, 60), 0, duration=0.1)
        await moverse_async("adelante", teclas, 0.5)
    elif accion == "saltar_adelante":
        pyautogui.keyDown(teclas["adelante"])
        pyautogui.press(teclas["saltar"])
        await asyncio.sleep(0.3)
        pyautogui.keyUp(teclas["adelante"])


async def minecraft_accion_minar(teclas: dict):
    """Acción de minería para Minecraft."""
    pyautogui.press(teclas["slot2"])  # pico
    await asyncio.sleep(0.05)
    pyautogui.moveRel(0, random.randint(10, 25), duration=0.1)
    
    pyautogui.mouseDown(button="left")
    await asyncio.sleep(random.uniform(0.8, 1.5))
    pyautogui.mouseUp(button="left")
    
    await moverse_async("adelante", teclas, 0.2)


async def minecraft_accion_combatir(teclas: dict, enemigos: list[dict]):
    """Combate para Minecraft."""
    pyautogui.press(teclas["slot1"])  # espada
    await asyncio.sleep(0.05)

    if enemigos:
        objetivo = enemigos[0]
        cx = JUEGO_REGION["width"] // 2
        cy = JUEGO_REGION["height"] // 2
        dx = (objetivo["x"] - cx) // 4
        dy = (objetivo["y"] - cy) // 4
        pyautogui.moveRel(dx, dy, duration=0.1)

    pyautogui.click(button="left")
    await asyncio.sleep(0.15)

    if random.random() > 0.5:
        await moverse_async("atras", teclas, 0.3)
    if random.random() > 0.7:
        pyautogui.press(teclas["saltar"])


async def minecraft_accion_construir(teclas: dict):
    """Construcción para Minecraft."""
    pyautogui.press(teclas["slot5"])  # bloques
    await asyncio.sleep(0.05)
    pyautogui.moveRel(0, 40, duration=0.1)
    pyautogui.click(button="right")
    await asyncio.sleep(0.1)
    await moverse_async("adelante", teclas, 0.3)
    pyautogui.moveRel(0, -40, duration=0.1)


async def minecraft_accion_sobrevivir(teclas: dict):
    """Supervivencia para Minecraft."""
    pyautogui.press(teclas["slot4"])  # comida
    await asyncio.sleep(0.05)
    pyautogui.mouseDown(button="right")
    await asyncio.sleep(2.0)
    pyautogui.mouseUp(button="right")
    await moverse_async("atras", teclas, 0.5)
    pyautogui.press(teclas["saltar"])


def actualizar_estado_minecraft(estado: GameState, info_hud: dict, enemigos: list, es_noche: bool):
    """Actualiza el estado de Minecraft según contexto."""
    estado.vida = info_hud.get("vida", estado.vida)
    estado.hambre = info_hud.get("hambre", estado.hambre)
    estado.enemigos_cerca = len(enemigos) > 0
    estado.es_de_dia = not es_noche

    if estado.vida < 6:
        nuevo = "SOBREVIVIR"
    elif estado.hambre < 6:
        nuevo = "SOBREVIVIR"
    elif estado.enemigos_cerca:
        nuevo = "COMBATIR"
    elif es_noche:
        nuevo = "MINAR"
    else:
        if estado.ticks % 60 < 35:
            nuevo = "EXPLORAR"
        elif estado.ticks % 60 < 50:
            nuevo = "MINAR"
        else:
            nuevo = "CONSTRUIR"

    if nuevo != estado.estado:
        print(f"🗺️  Estado: {estado.estado} → {nuevo}")
        estado.estado = nuevo

    estado.ticks += 1


# =========================
# 🎮 Controlador Unificado
# =========================
class GameController:
    """Controlador unificado para ambos juegos."""

    def __init__(self, game_type: GameType):
        self.game_type = game_type
        self.state = GameState()
        self.teclas = TECLAS_SHOOTER if game_type == GameType.SHOOTER else TECLAS_MINECRAFT

    async def play(
        self,
        yolo_model: YOLO,
        consultar_modelo_fn: Callable,
        audio_queue: asyncio.Queue,
        twitch_channel: Optional[Any] = None,
    ):
        """Bucle principal de juego."""
        self.state.jugando = True
        ultimo_comentario = time.time()

        tipo_texto = "jugando" if self.game_type == GameType.SHOOTER else "jugando Minecraft"
        print(f"🎮 Angela empieza a {tipo_texto}...")

        try:
            while self.state.jugando:
                frame = capturar_pantalla()

                if self.game_type == GameType.SHOOTER:
                    await self._loop_shooter(
                        frame, yolo_model, consultar_modelo_fn, audio_queue, twitch_channel, ultimo_comentario
                    )
                else:
                    await self._loop_minecraft(
                        frame, yolo_model, consultar_modelo_fn, audio_queue, twitch_channel, ultimo_comentario
                    )

                await asyncio.sleep(0.05)

        except Exception as e:
            print(f"⚠️  Error en bucle de juego: {e}")
            await asyncio.sleep(1)
        finally:
            self.stop()

    async def _loop_shooter(self, frame, yolo, consultar_fn, audio_queue, canal, ultimo_comentario):
        """Bucle específico para shooter."""
        enemigos = detectar_enemigos(frame, yolo)

        if enemigos:
            await shooter_apuntar_y_disparar(enemigos)
            if random.random() > 0.5:
                await shooter_movimiento_evasivo(self.teclas)

            ahora = time.time()
            if ahora - ultimo_comentario > 30:
                respuesta, _ = await consultar_fn(
                    f"Veo {len(enemigos)} enemigo(s), estoy en combate. Di algo breve y emocionante.",
                    usuario="Angela",
                )
                if canal:
                    await canal.send(respuesta[:500])
                await audio_queue.put((respuesta, "Bella"))
                ultimo_comentario = ahora
        else:
            accion = random.choice(["adelante", "izquierda", "derecha", "saltar"])
            await moverse_async(accion, self.teclas, random.uniform(0.2, 0.6))

    async def _loop_minecraft(self, frame, yolo, consultar_fn, audio_queue, canal, ultimo_comentario):
        """Bucle específico para Minecraft."""
        info_hud = leer_hud_minecraft(frame, self.state)
        enemigos = detectar_enemigos(frame, yolo, confianza_min=0.50)
        noche = es_de_noche(frame)

        actualizar_estado_minecraft(self.state, info_hud, enemigos, noche)

        if self.state.estado == "EXPLORAR":
            await minecraft_accion_explorar(self.teclas)
        elif self.state.estado == "MINAR":
            await minecraft_accion_minar(self.teclas)
        elif self.state.estado == "CONSTRUIR":
            await minecraft_accion_construir(self.teclas)
        elif self.state.estado == "COMBATIR":
            await minecraft_accion_combatir(self.teclas, enemigos)
        elif self.state.estado == "SOBREVIVIR":
            await minecraft_accion_sobrevivir(self.teclas)

        ahora = time.time()
        if ahora - ultimo_comentario > 40:
            contexto = (
                f"Estado: {self.state.estado}, "
                f"Vida: {self.state.vida}/20, Hambre: {self.state.hambre}/20. "
                f"{'Noche' if noche else 'Día'}. "
                f"{'¡Enemigos!' if self.state.enemigos_cerca else 'Sin peligro.'}. "
                f"Di algo breve y natural."
            )
            respuesta, _ = await consultar_fn(contexto, usuario="Angela")
            if canal:
                await canal.send(respuesta[:500])
            await audio_queue.put((respuesta, "Bella"))
            ultimo_comentario = ahora

    def stop(self):
        """Detiene el juego y libera todas las teclas."""
        self.state.jugando = False
        detener_teclas(self.teclas)
        pyautogui.mouseUp(button="left")
        pyautogui.mouseUp(button="right")
        print("🛑 Juego detenido.")


# =========================
# 🔄 Compatibilidad Backwards
# =========================
# Mantener las funciones antiguas para no romper main.py de inmediato

jugando = False
estado_minecraft = GameState()


async def loop_juego(yolo, consultar_modelo_fn, audio_queue, canal_twitch=None):
    """Wrapper compatible con main.py para shooter."""
    global jugando
    jugando = True

    controller = GameController(GameType.SHOOTER)
    try:
        await controller.play(yolo, consultar_modelo_fn, audio_queue, canal_twitch)
    finally:
        jugando = False


async def loop_minecraft(yolo, consultar_modelo_fn, audio_queue, canal_twitch=None):
    """Wrapper compatible con main.py para Minecraft."""
    global jugando
    jugando = True

    controller = GameController(GameType.MINECRAFT)
    try:
        await controller.play(yolo, consultar_modelo_fn, audio_queue, canal_twitch)
    finally:
        jugando = False


def parar_juego():
    """Para el juego shooter."""
    global jugando
    jugando = False
    detener_teclas(TECLAS_SHOOTER)
    print("🛑 Shooter detenido.")


def parar_minecraft():
    """Para el juego Minecraft."""
    global jugando
    jugando = False
    detener_teclas(TECLAS_MINECRAFT)
    pyautogui.mouseUp(button="left")
    pyautogui.mouseUp(button="right")
    print("🛑 Minecraft detenido.")
