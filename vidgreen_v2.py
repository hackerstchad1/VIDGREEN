#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VIDGREEN v2.0 - Lecteur vidéo ASCII avancé dans le terminal.
Thème vert Matrix, architecture modulaire, audio synchronisé, HUD riche.
Auteur : Projet éducatif
Version : 2.0.0
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import ctypes
import io
import json
import math
import os
import platform
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import wave
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
from colorama import Back, Fore, Style, init as colorama_init
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw, ImageFont

from rich.align import Align
from rich.bar import Bar
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
from rich.text import Text

colorama_init(autoreset=True)

APP_NAME = "VIDGREEN"
APP_VERSION = "2.0.0"
APP_AUTHOR = "Projet éducatif"
APP_LICENSE = "MIT"

DEFAULT_CHARSET = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
BLOCK_CHARSET = " ░▒▓█"
MINIMAL_CHARSET = " .:-=+*#%@"
DETAILED_CHARSET = " .'`^\",:;Il!i~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
MATRIX_CHARSET = "ｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ1234567890"

HAS_PYAUDIO = False
HAS_PYDUB = False
HAS_FFMPEG = False

# Imports optionnels
try:
    import pyaudio
    HAS_PYAUDIO = True
except Exception:
    pyaudio = None  # type: ignore

try:
    from pydub import AudioSegment
    HAS_PYDUB = True
except Exception:
    AudioSegment = None  # type: ignore

try:
    import imageio_ffmpeg
    HAS_FFMPEG = True
except Exception:
    imageio_ffmpeg = None  # type: ignore


class ColorMode(Enum):
    """Modes de coloration ASCII."""
    GREEN = "green"
    GREEN_INTENSE = "green_intense"
    MATRIX = "matrix"
    MONOCHROME = "monochrome"
    TRUECOLOR = "truecolor"
    RAINBOW = "rainbow"
    FIRE = "fire"
    ICE = "ice"
    AMBER = "amber"
    CUSTOM = "custom"


class RenderEngine(Enum):
    """Moteurs de rendu disponibles."""
    NAIVE = "naive"
    LUMINANCE = "luminance"
    EDGE = "edge"
    DITHER = "dither"
    BLOCK = "block"
    DETAILED = "detailed"
    HALFTONE = "halftone"
    SYMBOL = "symbol"


class AudioBackend(Enum):
    """Backends audio supportés."""
    PYAUDIO = "pyaudio"
    FFMPEG = "ffmpeg"
    NONE = "none"


@dataclass
class AppConfig:
    """Configuration complète de l'application."""
    input_path: str = ""
    width: int = 0
    height: int = 0
    fps: int = 0
    target_fps: int = 30
    charset: str = DEFAULT_CHARSET
    color_mode: ColorMode = ColorMode.GREEN
    engine: RenderEngine = RenderEngine.LUMINANCE
    contrast: float = 1.0
    brightness: float = 0.0
    gamma: float = 1.0
    saturation: float = 1.0
    invert: bool = False
    blur: bool = False
    sharpen: bool = False
    edge: bool = False
    dither: bool = False
    halftone: bool = False
    audio: bool = True
    audio_backend: AudioBackend = AudioBackend.PYAUDIO
    loop: bool = False
    start_time: float = 0.0
    duration: float = 0.0
    fullscreen: bool = False
    output_file: str = ""
    export_frames_dir: str = ""
    benchmark: bool = False
    use_rich: bool = True
    hide_hud: bool = False
    threads: int = 4
    preview_mode: bool = False
    custom_color: Tuple[int, int, int] = (0, 255, 0)
    volume: float = 0.8
    audio_offset: float = 0.0
    disable_async: bool = False
    keep_aspect: bool = True
    font_ratio: float = 2.15
    show_waveform: bool = False
    save_screenshot: bool = False
    screenshot_path: str = "vidgreen_screenshot.txt"
    subtitle_path: str = ""
    frame_skip: int = 0
    noise_reduction: bool = False
    auto_contrast: bool = False

    def __post_init__(self):
        if not self.charset:
            self.charset = DEFAULT_CHARSET
        if self.fps > 0:
            self.target_fps = self.fps


@dataclass
class FrameStats:
    """Statistiques de rendu par frame."""
    frame_index: int = 0
    timestamp: float = 0.0
    ascii_lines: int = 0
    render_time_ms: float = 0.0
    total_time_ms: float = 0.0
    dropped: bool = False
    audio_buffer_ms: float = 0.0


@dataclass
class AudioChunk:
    """Morceau audio avec synchronisation temporelle."""
    samples: np.ndarray
    timestamp: float
    duration: float


@dataclass
class ProcessedFrame:
    """Frame traitée prête à l'affichage."""
    frame_index: int
    timestamp: float
    ascii_data: List[Tuple[str, np.ndarray]]
    audio_chunk: Optional[AudioChunk] = None


class TerminalHelper:
    """Utilitaires avancés pour manipuler le terminal."""

    @staticmethod
    def clear() -> None:
        os.system("cls" if os.name == "nt" else "clear")

    @staticmethod
    def get_terminal_size() -> Tuple[int, int]:
        try:
            cols, rows = shutil.get_terminal_size()
            return cols, rows
        except Exception:
            return 80, 24

    @staticmethod
    def hide_cursor() -> None:
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

    @staticmethod
    def show_cursor() -> None:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    @staticmethod
    def set_terminal_title(title: str) -> None:
        if os.name == "nt":
            try:
                ctypes.windll.kernel32.SetConsoleTitleW(title)
            except Exception:
                pass
        else:
            sys.stdout.write(f"\033]2;{title}\007")
            sys.stdout.flush()

    @staticmethod
    def move_cursor_home() -> None:
        sys.stdout.write("\033[H")
        sys.stdout.flush()

    @staticmethod
    def reset_color() -> None:
        sys.stdout.write(Style.RESET_ALL)
        sys.stdout.flush()

    @staticmethod
    def enter_alt_screen() -> None:
        sys.stdout.write("\033[?1049h")
        sys.stdout.flush()

    @staticmethod
    def exit_alt_screen() -> None:
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()

    @staticmethod
    def set_terminal_size(cols: int, rows: int) -> None:
        if os.name != "nt":
            sys.stdout.write(f"\033[8;{rows};{cols}t")
            sys.stdout.flush()

    @staticmethod
    def supports_truecolor() -> bool:
        colorterm = os.environ.get("COLORTERM", "").lower()
        term = os.environ.get("TERM", "").lower()
        return "truecolor" in colorterm or "24bit" in colorterm or "256color" in term


class ColorUtils:
    """Utilitaires de conversion et de gradient de couleurs."""

    @staticmethod
    def rgb_to_ansi256(r: int, g: int, b: int) -> int:
        if r == g == b:
            if r < 8:
                return 16
            if r > 248:
                return 231
            return 232 + ((r - 8) // 10)
        r_index = 36 * (r // 51)
        g_index = 6 * (g // 51)
        b_index = b // 51
        return 16 + r_index + g_index + b_index

    @staticmethod
    def truecolor_fg(r: int, g: int, b: int) -> str:
        return f"\033[38;2;{r};{g};{b}m"

    @staticmethod
    def truecolor_bg(r: int, g: int, b: int) -> str:
        return f"\033[48;2;{r};{g};{b}m"

    @staticmethod
    def ansi256_fg(code: int) -> str:
        return f"\033[38;5;{code}m"

    @staticmethod
    def ansi256_bg(code: int) -> str:
        return f"\033[48;5;{code}m"

    @staticmethod
    def green_gradient(intensity: float) -> str:
        intensity = max(0.0, min(1.0, intensity))
        if intensity < 0.08:
            return Fore.BLACK
        if intensity < 0.22:
            return Fore.GREEN
        if intensity < 0.45:
            return Fore.LIGHTGREEN_EX
        if intensity < 0.70:
            return Fore.GREEN
        if intensity < 0.88:
            return Fore.WHITE
        return Fore.LIGHTGREEN_EX

    @staticmethod
    def matrix_gradient(intensity: float) -> str:
        intensity = max(0.0, min(1.0, intensity))
        if intensity < 0.12:
            return "\033[38;2;0;20;0m"
        if intensity < 0.30:
            return "\033[38;2;0;100;0m"
        if intensity < 0.55:
            return "\033[38;2;0;180;0m"
        if intensity < 0.80:
            return "\033[38;2;50;255;50m"
        return "\033[38;2;150;255;150m"

    @staticmethod
    def fire_gradient(intensity: float) -> str:
        intensity = max(0.0, min(1.0, intensity))
        r = int(255 * min(1.0, intensity * 2.0))
        g = int(255 * max(0.0, intensity - 0.5) * 2.0)
        b = 0
        return ColorUtils.truecolor_fg(r, g, b)

    @staticmethod
    def ice_gradient(intensity: float) -> str:
        intensity = max(0.0, min(1.0, intensity))
        r = int(50 * intensity)
        g = int(150 + 105 * intensity)
        b = int(200 + 55 * intensity)
        return ColorUtils.truecolor_fg(r, g, b)

    @staticmethod
    def amber_gradient(intensity: float) -> str:
        intensity = max(0.0, min(1.0, intensity))
        r = int(200 + 55 * intensity)
        g = int(120 + 100 * intensity)
        b = int(20 * intensity)
        return ColorUtils.truecolor_fg(r, g, b)

    @staticmethod
    def rainbow_gradient(intensity: float) -> str:
        intensity = max(0.0, min(1.0, intensity))
        hue = intensity * 360.0
        return ColorUtils.hsl_to_truecolor(hue, 1.0, 0.5)

    @staticmethod
    def hsl_to_truecolor(h: float, s: float, l: float) -> str:
        c = (1 - abs(2 * l - 1)) * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = l - c / 2
        if h < 60:
            r, g, b = c, x, 0
        elif h < 120:
            r, g, b = x, c, 0
        elif h < 180:
            r, g, b = 0, c, x
        elif h < 240:
            r, g, b = 0, x, c
        elif h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
        r = int((r + m) * 255)
        g = int((g + m) * 255)
        b = int((b + m) * 255)
        return ColorUtils.truecolor_fg(r, g, b)

    @staticmethod
    def color_for_mode(mode: ColorMode, intensity: float, bgr: Tuple[int, int, int], custom: Tuple[int, int, int] = (0, 255, 0)) -> str:
        b, g, r = bgr
        if mode == ColorMode.TRUECOLOR:
            return ColorUtils.truecolor_fg(r, g, b)
        if mode == ColorMode.RAINBOW:
            return ColorUtils.rainbow_gradient(intensity)
        if mode == ColorMode.FIRE:
            return ColorUtils.fire_gradient(intensity)
        if mode == ColorMode.ICE:
            return ColorUtils.ice_gradient(intensity)
        if mode == ColorMode.AMBER:
            return ColorUtils.amber_gradient(intensity)
        if mode == ColorMode.MATRIX:
            return ColorUtils.matrix_gradient(intensity)
        if mode == ColorMode.MONOCHROME:
            code = ColorUtils.rgb_to_ansi256(int(intensity * 255), int(intensity * 255), int(intensity * 255))
            return ColorUtils.ansi256_fg(code)
        if mode == ColorMode.CUSTOM:
            cr, cg, cb = custom
            return ColorUtils.truecolor_fg(int(cr * intensity), int(cg * intensity), int(cb * intensity))
        if mode == ColorMode.GREEN_INTENSE:
            return ColorUtils.truecolor_fg(0, int(255 * intensity), 0)
        return ColorUtils.green_gradient(intensity)


class AudioExtractor:
    """Extraction et décodage audio avec ffmpeg ou pydub."""

    def __init__(self, video_path: str, backend: AudioBackend = AudioBackend.PYAUDIO):
        self.video_path = video_path
        self.backend = backend
        self.sample_rate = 44100
        self.channels = 2
        self.temp_wav: Optional[str] = None

    def extract(self) -> Optional[str]:
        if not HAS_FFMPEG and not HAS_PYDUB:
            return None
        if HAS_FFMPEG:
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        else:
            ffmpeg_path = "ffmpeg"
        fd, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            cmd = [
                ffmpeg_path, "-y", "-i", self.video_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", str(self.sample_rate),
                "-ac", str(self.channels), temp_path
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            self.temp_wav = temp_path
            return temp_path
        except Exception:
            try:
                os.remove(temp_path)
            except Exception:
                pass
            return None

    def cleanup(self) -> None:
        if self.temp_wav and os.path.exists(self.temp_wav):
            try:
                os.remove(self.temp_wav)
            except Exception:
                pass


class AudioPlayer:
    """Lecteur audio avancé avec file d'attente et synchronisation."""

    def __init__(self, sample_rate: int = 44100, channels: int = 2, volume: float = 0.8, backend: AudioBackend = AudioBackend.PYAUDIO):
        self.sample_rate = sample_rate
        self.channels = channels
        self.volume = volume
        self.backend = backend
        self._audio_queue: queue.Queue[Optional[np.ndarray]] = queue.Queue(maxsize=20)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._playing = False
        self._buffer_ms = 0.0

    def start(self) -> bool:
        if self.backend == AudioBackend.NONE:
            return False
        if self.backend == AudioBackend.PYAUDIO and not HAS_PYAUDIO:
            return False
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._thread.start()
        self._playing = True
        return True

    def _playback_loop(self) -> None:
        try:
            if self.backend == AudioBackend.PYAUDIO and pyaudio:
                pa = pyaudio.PyAudio()
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=self.channels,
                    rate=self.sample_rate,
                    output=True,
                    frames_per_buffer=1024,
                )
                while not self._stop_event.is_set():
                    try:
                        chunk = self._audio_queue.get(timeout=0.05)
                        if chunk is None:
                            break
                        chunk = (chunk * self.volume).astype(np.int16)
                        stream.write(chunk.tobytes())
                    except queue.Empty:
                        continue
                stream.stop_stream()
                stream.close()
                pa.terminate()
            elif self.backend == AudioBackend.FFMPEG:
                self._play_via_ffmpeg()
        except Exception as e:
            print(f"[AudioPlayer error] {e}", file=sys.stderr)
        finally:
            self._playing = False

    def _play_via_ffmpeg(self) -> None:
        pass

    def feed(self, samples: np.ndarray) -> None:
        if not self._playing:
            return
        try:
            self._audio_queue.put(samples, timeout=0.05)
            self._buffer_ms += (len(samples) / self.channels / self.sample_rate) * 1000.0
        except queue.Full:
            pass

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self._audio_queue.put(None, timeout=0.1)
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=2.0)

    @property
    def is_playing(self) -> bool:
        return self._playing


class VideoSource:
    """Source vidéo basée sur OpenCV avec accès aléatoire."""

    def __init__(self, path: str):
        self.path = path
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_count = 0
        self.fps = 30.0
        self.width = 0
        self.height = 0
        self.duration = 0.0
        self.current_frame = 0

    def open(self) -> bool:
        self.cap = cv2.VideoCapture(self.path)
        if not self.cap.isOpened():
            return False
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if self.fps > 0 and self.frame_count > 0:
            self.duration = self.frame_count / self.fps
        return True

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self.cap is None:
            return False, None
        ok, frame = self.cap.read()
        if ok:
            self.current_frame += 1
        return ok, frame

    def set_position(self, seconds: float) -> bool:
        if self.cap is None:
            return False
        msec = seconds * 1000.0
        ok = self.cap.set(cv2.CAP_PROP_POS_MSEC, msec)
        if ok:
            self.current_frame = int(seconds * self.fps)
        return ok

    def release(self) -> None:
        if self.cap:
            self.cap.release()
            self.cap = None


class FrameProcessor:
    """Processeur d'image avancé : filtres, redimensionnement, conversion ASCII."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.charset = config.charset
        self.char_len = len(self.charset)
        self.executor = ThreadPoolExecutor(max_workers=config.threads) if config.threads > 1 else None

    def adjust_gamma(self, image: np.ndarray) -> np.ndarray:
        inv_gamma = 1.0 / max(0.1, self.config.gamma)
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
        return cv2.LUT(image, table)

    def auto_contrast(self, image: np.ndarray) -> np.ndarray:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        merged = cv2.merge([l, a, b])
        return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)

    def apply_filters(self, image: np.ndarray) -> np.ndarray:
        if self.config.auto_contrast:
            image = self.auto_contrast(image)
        if self.config.noise_reduction:
            image = cv2.fastNlMeansDenoisingColored(image, None, 5, 5, 7, 21)
        if self.config.blur:
            image = cv2.GaussianBlur(image, (3, 3), 0)
        if self.config.sharpen:
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
            image = cv2.filter2D(image, -1, kernel)
        if self.config.edge:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            image = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        if self.config.saturation != 1.0:
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype("float32")
            hsv[:, :, 1] *= self.config.saturation
            hsv[:, :, 1] = np.clip(hsv[:, :, 1], 0, 255)
            image = cv2.cvtColor(hsv.astype("uint8"), cv2.COLOR_HSV2BGR)
        return image

    def resize_for_terminal(self, image: np.ndarray, term_cols: int, term_rows: int) -> np.ndarray:
        h, w = image.shape[:2]
        if not self.config.keep_aspect:
            return cv2.resize(image, (max(2, term_cols), max(1, term_rows)), interpolation=cv2.INTER_AREA)
        aspect = h / w
        font_aspect = self.config.font_ratio
        new_w = max(2, term_cols)
        new_h = max(1, int(aspect * new_w / font_aspect))
        if term_rows > 0 and new_h > term_rows:
            new_h = max(1, term_rows)
            new_w = max(2, int(new_h * font_aspect / aspect))
        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

    def frame_to_ascii_luminance(self, image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if self.config.invert:
            gray = 255 - gray
        if self.config.brightness != 0.0:
            gray = cv2.convertScaleAbs(gray, alpha=1.0, beta=self.config.brightness * 255)
        if self.config.contrast != 1.0:
            gray = cv2.convertScaleAbs(gray, alpha=self.config.contrast, beta=0)
        gray = self.adjust_gamma(gray)
        h, w = gray.shape
        result: List[Tuple[str, np.ndarray]] = []
        for y in range(h):
            row_chars = []
            row_colors = []
            for x in range(w):
                intensity = gray[y, x] / 255.0
                idx = min(self.char_len - 1, int(intensity * self.char_len))
                row_chars.append(self.charset[idx])
                row_colors.append(image[y, x])
            result.append(("".join(row_chars), np.array(row_colors)))
        return result

    def frame_to_ascii_block(self, image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if self.config.invert:
            gray = 255 - gray
        h, w = gray.shape
        result: List[Tuple[str, np.ndarray]] = []
        for y in range(h):
            row_chars = []
            row_colors = []
            for x in range(w):
                intensity = gray[y, x] / 255.0
                if intensity < 0.2:
                    ch = " "
                elif intensity < 0.4:
                    ch = "░"
                elif intensity < 0.6:
                    ch = "▒"
                elif intensity < 0.8:
                    ch = "▓"
                else:
                    ch = "█"
                row_chars.append(ch)
                row_colors.append(image[y, x])
            result.append(("".join(row_chars), np.array(row_colors)))
        return result

    def frame_to_ascii_edge(self, image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        h, w = edges.shape
        result: List[Tuple[str, np.ndarray]] = []
        for y in range(h):
            row_chars = []
            row_colors = []
            for x in range(w):
                val = edges[y, x]
                ch = "█" if val > 128 else " "
                row_chars.append(ch)
                row_colors.append(image[y, x])
            result.append(("".join(row_chars), np.array(row_colors)))
        return result

    def frame_to_ascii_dither(self, image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype("float32")
        if self.config.invert:
            gray = 255 - gray
        h, w = gray.shape
        for y in range(h):
            for x in range(w):
                old_pixel = gray[y, x]
                new_pixel = 255 if old_pixel > 128 else 0
                gray[y, x] = new_pixel
                error = old_pixel - new_pixel
                if x + 1 < w:
                    gray[y, x + 1] += error * 7 / 16
                if y + 1 < h:
                    if x > 0:
                        gray[y + 1, x - 1] += error * 3 / 16
                    gray[y + 1, x] += error * 5 / 16
                    if x + 1 < w:
                        gray[y + 1, x + 1] += error * 1 / 16
        gray = np.clip(gray, 0, 255).astype("uint8")
        result: List[Tuple[str, np.ndarray]] = []
        for y in range(h):
            row_chars = []
            row_colors = []
            for x in range(w):
                intensity = gray[y, x] / 255.0
                idx = min(self.char_len - 1, int(intensity * self.char_len))
                row_chars.append(self.charset[idx])
                row_colors.append(image[y, x])
            result.append(("".join(row_chars), np.array(row_colors)))
        return result

    def frame_to_ascii_halftone(self, image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if self.config.invert:
            gray = 255 - gray
        h, w = gray.shape
        result: List[Tuple[str, np.ndarray]] = []
        dots = [" ", "·", "∘", "○", "●", "█"]
        for y in range(h):
            row_chars = []
            row_colors = []
            for x in range(w):
                intensity = gray[y, x] / 255.0
                idx = min(len(dots) - 1, int(intensity * len(dots)))
                row_chars.append(dots[idx])
                row_colors.append(image[y, x])
            result.append(("".join(row_chars), np.array(row_colors)))
        return result

    def frame_to_ascii_symbol(self, image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if self.config.invert:
            gray = 255 - gray
        h, w = gray.shape
        result: List[Tuple[str, np.ndarray]] = []
        charset = MATRIX_CHARSET
        char_len = len(charset)
        for y in range(h):
            row_chars = []
            row_colors = []
            for x in range(w):
                intensity = gray[y, x] / 255.0
                idx = min(char_len - 1, int(intensity * char_len))
                row_chars.append(charset[idx])
                row_colors.append(image[y, x])
            result.append(("".join(row_chars), np.array(row_colors)))
        return result

    def process(self, image: np.ndarray, term_cols: int, term_rows: int) -> List[Tuple[str, np.ndarray]]:
        image = self.apply_filters(image)
        image = self.resize_for_terminal(image, term_cols, term_rows)
        if self.config.engine == RenderEngine.BLOCK:
            return self.frame_to_ascii_block(image)
        elif self.config.engine == RenderEngine.EDGE:
            return self.frame_to_ascii_edge(image)
        elif self.config.engine == RenderEngine.DITHER:
            return self.frame_to_ascii_dither(image)
        elif self.config.engine == RenderEngine.HALFTONE:
            return self.frame_to_ascii_halftone(image)
        elif self.config.engine == RenderEngine.SYMBOL:
            return self.frame_to_ascii_symbol(image)
        elif self.config.engine == RenderEngine.DETAILED:
            old_charset = self.charset
            self.charset = DETAILED_CHARSET
            self.char_len = len(self.charset)
            result = self.frame_to_ascii_luminance(image)
            self.charset = old_charset
            self.char_len = len(self.charset)
            return result
        else:
            return self.frame_to_ascii_luminance(image)

    def shutdown(self) -> None:
        if self.executor:
            self.executor.shutdown(wait=False)


class FrameRenderer:
    """Rendu ASCII colorisé dans le terminal avec plusieurs modes."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.color_utils = ColorUtils()
        self.truecolor_support = TerminalHelper.supports_truecolor()

    def render_line(self, chars: str, colors: np.ndarray) -> str:
        output = ""
        mode = self.config.color_mode
        for ch, color in zip(chars, colors):
            b, g, r = int(color[0]), int(color[1]), int(color[2])
            luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
            intensity = luminance / 255.0
            col = self.color_utils.color_for_mode(mode, intensity, (b, g, r), self.config.custom_color)
            output += f"{col}{ch}"
        output += Style.RESET_ALL
        return output

    def render_frame(self, ascii_data: List[Tuple[str, np.ndarray]]) -> str:
        lines: List[str] = []
        for chars, colors in ascii_data:
            lines.append(self.render_line(chars, colors))
        return "\n".join(lines)

    def render_to_file(self, ascii_data: List[Tuple[str, np.ndarray]], path: str) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(self.render_frame(ascii_data))
            f.write("\n\n")

    def screenshot(self, ascii_data: List[Tuple[str, np.ndarray]], path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.render_frame(ascii_data))


class HUDRenderer:
    """HUD avancé avec informations de lecture et visualiseur."""

    def __init__(self, console: Console):
        self.console = console
        self.waveform_history: deque[float] = deque(maxlen=40)

    def update_waveform(self, value: float) -> None:
        self.waveform_history.append(value)

    def render(self, source: VideoSource, current_time: float, fps: float, dropped: int, total_frames: int, volume: float = 0.8) -> Panel:
        progress = current_time / max(1e-6, source.duration)
        bar_width = 40
        filled = int(progress * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        text = Text()
        text.append(f"{APP_NAME} v{APP_VERSION}  |  ", style="bold green")
        text.append(f"{source.path}\n")
        text.append(f"⏱ {self._format_time(current_time)} / {self._format_time(source.duration)}  ")
        text.append(f"FPS {fps:.1f}  ")
        text.append(f"Frames {total_frames}  ")
        text.append(f"Dropped {dropped}\n")
        text.append(f"Vol {volume*100:.0f}%  ")
        text.append(f"Res {source.width}x{source.height}  ")
        text.append(f"Src {source.fps:.1f}fps\n")
        text.append(f"{bar} {progress*100:.1f}%", style="green")
        if self.waveform_history:
            text.append("\n")
            wave_line = ""
            for v in self.waveform_history:
                idx = min(7, int(v * 8))
                blocks = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
                wave_line += blocks[idx]
            text.append(wave_line, style="green")
        return Panel(Align.left(text), title="[bold green]VIDGREEN CONTROL PANEL[/bold green]", border_style="green")

    @staticmethod
    def _format_time(seconds: float) -> str:
        seconds = max(0, seconds)
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"


class Benchmark:
    """Outil de benchmark des performances."""

    def __init__(self):
        self.frames = 0
        self.total_time = 0.0
        self.render_times: deque[float] = deque(maxlen=100)
        self.fps_history: deque[float] = deque(maxlen=60)

    def record(self, render_time: float, frame_time: float, fps: float) -> None:
        self.frames += 1
        self.total_time += frame_time
        self.render_times.append(render_time)
        self.fps_history.append(fps)

    def summary(self) -> str:
        if self.frames == 0:
            return "Aucune frame rendue."
        avg_frame = self.total_time / self.frames
        avg_render = sum(self.render_times) / len(self.render_times)
        avg_fps = sum(self.fps_history) / len(self.fps_history) if self.fps_history else 0.0
        return (
            f"Frames rendues : {self.frames}\n"
            f"Temps total    : {self.total_time:.2f}s\n"
            f"FPS moyen      : {avg_fps:.2f}\n"
            f"Temps rendu    : {avg_render*1000:.2f}ms\n"
            f"Temps frame    : {avg_frame*1000:.2f}ms"
        )


class InputController:
    """Contrôleur d'entrée clavier asynchrone."""

    def __init__(self, app: "VIDGREEN"):
        self.app = app
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.commands: Dict[str, Callable[[], None]] = {
            "q": app.stop,
            "Q": app.stop,
            " ": app.toggle_pause,
            "p": app.toggle_pause,
            "l": app.toggle_loop,
            "+": app.volume_up,
            "=": app.volume_up,
            "-": app.volume_down,
            "r": app.reset,
            "f": app.toggle_fullscreen,
            "h": app.toggle_hud,
            "s": app.take_screenshot,
            "n": app.next_color_mode,
            "m": app.next_engine,
        }

    def start(self) -> None:
        try:
            import pynput
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._listen_pynput, daemon=True)
            self._thread.start()
        except Exception:
            pass

    def _listen_pynput(self) -> None:
        try:
            from pynput import keyboard
            def on_press(key):
                try:
                    ch = key.char
                except AttributeError:
                    return
                if ch in self.commands:
                    self.commands[ch]()
                elif ch == "\x03":
                    self.app.stop()
            with keyboard.Listener(on_press=on_press) as listener:
                while not self._stop_event.is_set():
                    time.sleep(0.05)
                listener.stop()
        except Exception:
            pass

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)


class VIDGREEN:
    """Orchestrateur principal de VIDGREEN v2."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.console = Console()
        self.source = VideoSource(config.input_path)
        self.processor = FrameProcessor(config)
        self.renderer = FrameRenderer(config)
        self.hud = HUDRenderer(self.console)
        self.benchmark = Benchmark()
        self.audio_extractor = AudioExtractor(config.input_path, config.audio_backend)
        self.audio_player = AudioPlayer(volume=config.volume, backend=config.audio_backend)
        self.audio_samples: Optional[np.ndarray] = None
        self.audio_path: Optional[str] = None
        self._running = False
        self._paused = False
        self._dropped_frames = 0
        self._total_frames = 0
        self._fps_display = 0.0
        self._input_controller = InputController(self)
        self._frame_index = 0
        self._loop_count = 0

    def stop(self) -> None:
        self._running = False

    def toggle_pause(self) -> None:
        self._paused = not self._paused

    def toggle_loop(self) -> None:
        self.config.loop = not self.config.loop

    def volume_up(self) -> None:
        self.config.volume = min(1.0, self.config.volume + 0.1)
        self.audio_player.volume = self.config.volume

    def volume_down(self) -> None:
        self.config.volume = max(0.0, self.config.volume - 0.1)
        self.audio_player.volume = self.config.volume

    def reset(self) -> None:
        self.source.set_position(self.config.start_time)
        self._frame_index = 0

    def toggle_fullscreen(self) -> None:
        self.config.fullscreen = not self.config.fullscreen

    def toggle_hud(self) -> None:
        self.config.hide_hud = not self.config.hide_hud

    def take_screenshot(self) -> None:
        self.config.save_screenshot = True

    def next_color_mode(self) -> None:
        modes = list(ColorMode)
        idx = modes.index(self.config.color_mode)
        self.config.color_mode = modes[(idx + 1) % len(modes)]

    def next_engine(self) -> None:
        engines = list(RenderEngine)
        idx = engines.index(self.config.engine)
        self.config.engine = engines[(idx + 1) % len(engines)]

    def _load_audio(self) -> bool:
        if not self.config.audio:
            return False
        self.audio_path = self.audio_extractor.extract()
        if self.audio_path is None:
            return False
        try:
            with wave.open(self.audio_path, "rb") as wf:
                nchannels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                nframes = wf.getnframes()
                raw = wf.readframes(nframes)
                if sampwidth == 2:
                    self.audio_samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                else:
                    self.audio_samples = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) / 255.0
                if nchannels == 2:
                    self.audio_samples = self.audio_samples.reshape(-1, 2)
                self.audio_player.sample_rate = framerate
                self.audio_player.channels = nchannels
        except Exception as e:
            print(f"[Audio load error] {e}", file=sys.stderr)
            return False
        return True

    def _get_audio_chunk(self, frame_index: int, fps: float) -> Optional[np.ndarray]:
        if self.audio_samples is None:
            return None
        if self.audio_samples.ndim == 1:
            channels = 1
        else:
            channels = self.audio_samples.shape[1]
        sample_rate = self.audio_player.sample_rate
        start_sample = int((frame_index / fps) * sample_rate)
        end_sample = int(((frame_index + 1) / fps) * sample_rate)
        start_sample += int(self.config.audio_offset * sample_rate)
        end_sample += int(self.config.audio_offset * sample_rate)
        if start_sample >= len(self.audio_samples):
            return None
        end_sample = min(end_sample, len(self.audio_samples))
        chunk = self.audio_samples[start_sample:end_sample]
        if channels == 1:
            chunk = chunk.reshape(-1, 1)
        return chunk

    def run(self) -> int:
        if not self.source.open():
            self.console.print(f"[bold red]Erreur : impossible d'ouvrir {self.config.input_path}[/bold red]")
            return 1

        TerminalHelper.hide_cursor()
        TerminalHelper.set_terminal_title(f"{APP_NAME} v{APP_VERSION} - {self.config.input_path}")
        signal.signal(signal.SIGINT, self._signal_handler)

        if self.config.start_time > 0:
            self.source.set_position(self.config.start_time)

        self._running = True
        if self.config.audio:
            self._load_audio()
            self.audio_player.start()

        self._input_controller.start()

        try:
            if self.config.use_rich and not self.config.hide_hud:
                self._run_with_hud()
            else:
                self._run_simple()
        finally:
            self._running = False
            self._input_controller.stop()
            self.source.release()
            self.audio_player.stop()
            self.audio_extractor.cleanup()
            self.processor.shutdown()
            TerminalHelper.show_cursor()
            TerminalHelper.reset_color()
            if self.config.benchmark:
                self.console.print("\n[bold green]Benchmark :[/bold green]")
                self.console.print(self.benchmark.summary())
        return 0

    def _signal_handler(self, signum: int, frame: Any) -> None:
        self._running = False

    def _run_simple(self) -> None:
        term_cols, term_rows = TerminalHelper.get_terminal_size()
        video_rows = max(1, term_rows - 2) if self.config.fullscreen else max(1, term_rows - 4)
        target_frame_time = 1.0 / max(1, self.config.target_fps)
        start_clock = time.perf_counter()
        frame_index = 0
        last_fps_time = start_clock
        fps_frames = 0

        while self._running:
            if self._paused:
                time.sleep(0.05)
                continue
            t0 = time.perf_counter()
            ok, img = self.source.read()
            if not ok or img is None:
                if self.config.loop:
                    self.source.set_position(self.config.start_time)
                    frame_index = 0
                    self._loop_count += 1
                    continue
                break

            current_time = frame_index / max(1, self.source.fps)
            if self.config.duration > 0 and current_time > self.config.duration:
                break

            ascii_data = self.processor.process(img, term_cols, video_rows)
            rendered = self.renderer.render_frame(ascii_data)
            TerminalHelper.move_cursor_home()
            sys.stdout.write(rendered)
            sys.stdout.flush()

            if self.config.output_file:
                self.renderer.render_to_file(ascii_data, self.config.output_file)
            if self.config.save_screenshot:
                self.renderer.screenshot(ascii_data, self.config.screenshot_path)
                self.config.save_screenshot = False

            if self.audio_samples is not None:
                chunk = self._get_audio_chunk(frame_index, self.source.fps)
                if chunk is not None:
                    self.audio_player.feed(chunk)

            frame_index += 1
            self._frame_index = frame_index
            self._total_frames += 1
            t1 = time.perf_counter()
            render_time = t1 - t0
            fps_frames += 1
            if t1 - last_fps_time >= 1.0:
                self._fps_display = fps_frames / (t1 - last_fps_time)
                fps_frames = 0
                last_fps_time = t1
            elapsed = t1 - start_clock
            expected = frame_index * target_frame_time
            sleep_time = expected - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                self._dropped_frames += 1
            self.benchmark.record(render_time, time.perf_counter() - t0, self._fps_display)

    def _run_with_hud(self) -> None:
        layout = Layout()
        layout.split_column(Layout(name="video", ratio=6), Layout(name="hud", size=10))
        target_frame_time = 1.0 / max(1, self.config.target_fps)
        start_clock = time.perf_counter()
        frame_index = 0
        last_fps_time = start_clock
        fps_frames = 0

        with Live(layout, refresh_per_second=self.config.target_fps, console=self.console, screen=True) as live:
            while self._running:
                if self._paused:
                    time.sleep(0.05)
                    continue
                t0 = time.perf_counter()
                ok, img = self.source.read()
                if not ok or img is None:
                    if self.config.loop:
                        self.source.set_position(self.config.start_time)
                        frame_index = 0
                        self._loop_count += 1
                        continue
                    break

                term_cols, term_rows = TerminalHelper.get_terminal_size()
                video_rows = max(1, term_rows - 10)
                current_time = self.source.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0 if self.source.cap else 0.0
                if self.config.duration > 0 and current_time > self.config.duration:
                    break

                ascii_data = self.processor.process(img, term_cols, video_rows)
                rendered = self.renderer.render_frame(ascii_data)
                layout["video"].update(Panel(rendered, border_style="green", padding=(0, 0), title="[green]VIDEO[/green]"))

                now = time.perf_counter()
                fps_frames += 1
                if now - last_fps_time >= 1.0:
                    self._fps_display = fps_frames / (now - last_fps_time)
                    fps_frames = 0
                    last_fps_time = now

                if self.audio_samples is not None:
                    chunk = self._get_audio_chunk(frame_index, self.source.fps)
                    if chunk is not None:
                        self.audio_player.feed(chunk)
                        self.hud.update_waveform(np.abs(chunk).mean())

                if not self.config.hide_hud:
                    hud_panel = self.hud.render(self.source, current_time, self._fps_display, self._dropped_frames, self._total_frames, self.config.volume)
                    layout["hud"].update(hud_panel)

                if self.config.output_file:
                    self.renderer.render_to_file(ascii_data, self.config.output_file)
                if self.config.save_screenshot:
                    self.renderer.screenshot(ascii_data, self.config.screenshot_path)
                    self.config.save_screenshot = False

                frame_index += 1
                self._frame_index = frame_index
                self._total_frames += 1
                t1 = time.perf_counter()
                render_time = t1 - t0
                elapsed = t1 - start_clock
                expected = frame_index * target_frame_time
                sleep_time = expected - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    self._dropped_frames += 1
                self.benchmark.record(render_time, time.perf_counter() - t0, self._fps_display)


def parse_args() -> AppConfig:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="VIDGREEN v2.0 - Lecteur vidéo ASCII avancé dans le terminal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemple : python vidgreen_v2.py video.mp4 --fullscreen --color matrix --engine block",
    )
    parser.add_argument("video", help="Chemin vers le fichier vidéo.")
    parser.add_argument("--width", "-w", type=int, default=0, help="Largeur en colonnes (0 = auto).")
    parser.add_argument("--height", "-H", type=int, default=0, help="Hauteur en lignes (0 = auto).")
    parser.add_argument("--fps", type=int, default=0, help="Limite de FPS (0 = source).")
    parser.add_argument("--charset", "-c", type=str, default=DEFAULT_CHARSET, help="Jeu de caractères ASCII.")
    parser.add_argument("--color", choices=[m.value for m in ColorMode], default="green", help="Mode de couleur.")
    parser.add_argument("--engine", choices=[m.value for m in RenderEngine], default="luminance", help="Moteur de rendu.")
    parser.add_argument("--contrast", type=float, default=1.0, help="Contraste.")
    parser.add_argument("--brightness", type=float, default=0.0, help="Luminosité.")
    parser.add_argument("--gamma", type=float, default=1.0, help="Gamma.")
    parser.add_argument("--saturation", type=float, default=1.0, help="Saturation.")
    parser.add_argument("--invert", action="store_true", help="Inverser.")
    parser.add_argument("--blur", action="store_true", help="Flou.")
    parser.add_argument("--sharpen", action="store_true", help="Sharpen.")
    parser.add_argument("--edge", action="store_true", help="Contours.")
    parser.add_argument("--dither", action="store_true", help="Dithering.")
    parser.add_argument("--halftone", action="store_true", help="Halftone.")
    parser.add_argument("--no-audio", action="store_true", help="Désactiver audio.")
    parser.add_argument("--audio-backend", choices=[b.value for b in AudioBackend], default="pyaudio", help="Backend audio.")
    parser.add_argument("--loop", action="store_true", help="Boucle.")
    parser.add_argument("--start", type=float, default=0.0, help="Départ (s).")
    parser.add_argument("--duration", type=float, default=0.0, help="Durée max (s).")
    parser.add_argument("--fullscreen", "-f", action="store_true", help="Plein terminal.")
    parser.add_argument("--output", "-o", type=str, default="", help="Fichier sortie ASCII.")
    parser.add_argument("--export-frames", type=str, default="", help="Dossier export frames.")
    parser.add_argument("--benchmark", "-b", action="store_true", help="Benchmark.")
    parser.add_argument("--no-rich", action="store_true", help="Désactiver Rich.")
    parser.add_argument("--hide-hud", action="store_true", help="Cacher HUD.")
    parser.add_argument("--threads", "-t", type=int, default=4, help="Threads.")
    parser.add_argument("--preview", action="store_true", help="Aperçu statique.")
    parser.add_argument("--volume", "-v", type=float, default=0.8, help="Volume.")
    parser.add_argument("--audio-offset", type=float, default=0.0, help="Décalage audio (s).")
    parser.add_argument("--custom-color", type=str, default="0,255,0", help="Couleur RGB personnalisée.")
    parser.add_argument("--waveform", action="store_true", help="Afficher waveform HUD.")
    parser.add_argument("--screenshot", type=str, default="", help="Chemin screenshot.")
    parser.add_argument("--noise-reduction", action="store_true", help="Réduction bruit.")
    parser.add_argument("--auto-contrast", action="store_true", help="Contraste automatique.")

    args = parser.parse_args()
    try:
        custom_rgb = tuple(int(x) for x in args.custom_color.split(","))
        if len(custom_rgb) != 3:
            custom_rgb = (0, 255, 0)
    except Exception:
        custom_rgb = (0, 255, 0)

    config = AppConfig(
        input_path=args.video,
        width=args.width,
        height=args.height,
        fps=args.fps,
        charset=args.charset,
        color_mode=ColorMode(args.color),
        engine=RenderEngine(args.engine),
        contrast=args.contrast,
        brightness=args.brightness,
        gamma=args.gamma,
        saturation=args.saturation,
        invert=args.invert,
        blur=args.blur,
        sharpen=args.sharpen,
        edge=args.edge,
        dither=args.dither,
        halftone=args.halftone,
        audio=not args.no_audio,
        audio_backend=AudioBackend(args.audio_backend),
        loop=args.loop,
        start_time=args.start,
        duration=args.duration,
        fullscreen=args.fullscreen,
        output_file=args.output,
        export_frames_dir=args.export_frames,
        benchmark=args.benchmark,
        use_rich=not args.no_rich,
        hide_hud=args.hide_hud,
        threads=args.threads,
        preview_mode=args.preview,
        volume=args.volume,
        audio_offset=args.audio_offset,
        custom_color=custom_rgb,
        show_waveform=args.waveform,
        screenshot_path=args.screenshot or "vidgreen_screenshot.txt",
        save_screenshot=bool(args.screenshot),
        noise_reduction=args.noise_reduction,
        auto_contrast=args.auto_contrast,
    )
    return config


def print_banner() -> None:
    banner = f"""
{Fore.GREEN}
 ██╗   ██╗██╗██████╗  ██████╗ ██████╗ ███████╗███████╗███╗   ██╗
 ██║   ██║██║██╔══██╗██╔════╝ ██╔══██╗██╔════╝██╔════╝████╗  ██║
 ██║   ██║██║██║  ██║██║  ███╗██████╔╝█████╗  █████╗  ██╔██╗ ██║
 ╚██╗ ██╔╝██║██║  ██║██║   ██║██╔══██╗██╔══╝  ██╔══╝  ██║╚██╗██║
  ╚████╔╝ ██║██████╔╝╚██████╔╝██║  ██║███████╗███████╗██║ ╚████║
   ╚═══╝  ╚═╝╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═══╝
{Style.RESET_ALL}
{Fore.LIGHTGREEN_EX}    VIDGREEN v2.0 - Lecteur vidéo ASCII dans le terminal{Style.RESET_ALL}
{Fore.GREEN}    Thème vert Matrix | Audio sync | HUD avancé | Benchmark{Style.RESET_ALL}
"""
    print(banner)


def main() -> int:
    print_banner()
    config = parse_args()
    if not os.path.exists(config.input_path):
        print(f"{Fore.RED}Fichier introuvable : {config.input_path}{Style.RESET_ALL}")
        return 1

    if config.preview_mode:
        source = VideoSource(config.input_path)
        if not source.open():
            print(f"{Fore.RED}Impossible d'ouvrir la vidéo.{Style.RESET_ALL}")
            return 1
        ok, img = source.read()
        if ok and img is not None:
            term_cols, term_rows = TerminalHelper.get_terminal_size()
            processor = FrameProcessor(config)
            renderer = FrameRenderer(config)
            ascii_data = processor.process(img, term_cols, term_rows - 2)
            print(renderer.render_frame(ascii_data))
        source.release()
        return 0

    app = VIDGREEN(config)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
