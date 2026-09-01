#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VIDGREEN - Lecteur vidéo ASCII dans le terminal avec thème vert.
Auteur : Projet éducatif
Version : 1.0.0
Usage éthique et personnel uniquement.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import ctypes
import math
import os
import platform
import queue
import shutil
import signal
import sys
import threading
import time
import wave
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
from colorama import Back, Fore, Style, init as colorama_init
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

# Rich imports pour UI avancée
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.text import Text

# Cross-platform terminal helpers
try:
    import pyaudio
    HAS_PYAUDIO = True
except Exception:
    HAS_PYAUDIO = False

try:
    from pydub import AudioSegment
    HAS_PYDUB = True
except Exception:
    HAS_PYDUB = False

try:
    from screeninfo import get_monitors
    HAS_SCREENINFO = True
except Exception:
    HAS_SCREENINFO = False

colorama_init(autoreset=True)

# Constantes globales
APP_NAME = "VIDGREEN"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Projet éducatif"
DEFAULT_CHARSET = " .:-=+*#%@"
GREEN_CHARSET = " ░▒▓█"
ADVANCED_CHARSET = "`^\\",:;Il!i~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"


class ColorMode(Enum):
    """Modes de coloration ASCII."""

    GREEN = "green"
    GREEN_INTENSE = "green_intense"
    MATRIX = "matrix"
    MONOCHROME = "monochrome"
    TRUECOLOR = "truecolor"


class RenderEngine(Enum):
    """Moteurs de rendu disponibles."""

    NAIVE = "naive"
    LUMINANCE = "luminance"
    EDGE = "edge"
    DITHER = "dither"
    BLOCK = "block"


@dataclass
class AppConfig:
    """Configuration de l'application."""

    input_path: str = ""
    width: int = 80
    height: int = 0
    fps: int = 30
    charset: str = DEFAULT_CHARSET
    color_mode: ColorMode = ColorMode.GREEN
    engine: RenderEngine = RenderEngine.LUMINANCE
    contrast: float = 1.0
    brightness: float = 0.0
    gamma: float = 1.0
    invert: bool = False
    blur: bool = False
    sharpen: bool = False
    edge: bool = False
    dither: bool = False
    audio: bool = True
    loop: bool = False
    start_time: float = 0.0
    duration: float = 0.0
    fullscreen: bool = False
    output_file: str = ""
    benchmark: bool = False
    use_rich: bool = True
    hide_hud: bool = False
    threads: int = 4
    preview_mode: bool = False

    def __post_init__(self):
        if not self.charset:
            self.charset = DEFAULT_CHARSET


@dataclass
class FrameStats:
    """Statistiques de rendu par frame."""

    frame_index: int = 0
    timestamp: float = 0.0
    ascii_lines: int = 0
    render_time_ms: float = 0.0
    total_time_ms: float = 0.0
    dropped: bool = False


class TerminalHelper:
    """Utilitaires pour manipuler le terminal."""

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
        if os.name == "nt":
            try:
                ctypes.windll.kernel32.SetConsoleCursorInfo(...)
            except Exception:
                pass
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


class ColorUtils:
    """Utilitaires de conversion de couleurs."""

    @staticmethod
    def rgb_to_ansi(r: int, g: int, b: int) -> str:
        if r == g == b:
            if r < 8:
                return "30"
            if r > 248:
                return "97"
            return str(232 + ((r - 8) // 10))
        r_index = 36 * (r // 51)
        g_index = 6 * (g // 51)
        b_index = b // 51
        code = 16 + r_index + g_index + b_index
        return f"38;5;{code}"

    @staticmethod
    def truecolor_fg(r: int, g: int, b: int) -> str:
        return f"\033[38;2;{r};{g};{b}m"

    @staticmethod
    def truecolor_bg(r: int, g: int, b: int) -> str:
        return f"\033[48;2;{r};{g};{b}m"

    @staticmethod
    def green_gradient(intensity: float) -> str:
        """Retourne une couleur verte en fonction de l'intensité (0-1)."""
        intensity = max(0.0, min(1.0, intensity))
        levels = [
            (0.0, Fore.BLACK),
            (0.1, Fore.BLACK),
            (0.2, Fore.GREEN),
            (0.4, Fore.LIGHTGREEN_EX),
            (0.6, Fore.LIGHTGREEN_EX),
            (0.8, Fore.WHITE),
            (1.0, Fore.WHITE),
        ]
        for i in range(len(levels) - 1):
            if levels[i][0] <= intensity <= levels[i + 1][0]:
                return levels[i + 1][1]
        return Fore.WHITE

    @staticmethod
    def matrix_gradient(intensity: float) -> str:
        intensity = max(0.0, min(1.0, intensity))
        if intensity < 0.15:
            return Fore.BLACK
        if intensity < 0.35:
            return Fore.GREEN
        if intensity < 0.65:
            return Fore.LIGHTGREEN_EX
        if intensity < 0.85:
            return Fore.WHITE
        return Fore.WHITE


class AudioPlayer:
    """Lecteur audio simple utilisant pyaudio et pydub."""

    def __init__(self, sample_rate: int = 44100, channels: int = 2):
        self.sample_rate = sample_rate
        self.channels = channels
        self._audio_queue: queue.Queue[Optional[np.ndarray]] = queue.Queue(maxsize=10)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._volume = 0.8

    def start(self) -> bool:
        if not HAS_PYAUDIO:
            return False
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._thread.start()
        return True

    def _playback_loop(self) -> None:
        try:
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=2048,
            )
            while not self._stop_event.is_set():
                try:
                    chunk = self._audio_queue.get(timeout=0.1)
                    if chunk is None:
                        break
                    chunk = (chunk * self._volume).astype(np.int16)
                    stream.write(chunk.tobytes())
                except queue.Empty:
                    continue
            stream.stop_stream()
            stream.close()
            pa.terminate()
        except Exception as e:
            print(f"[AudioPlayer error] {e}", file=sys.stderr)

    def feed(self, samples: np.ndarray) -> None:
        if self._thread is None:
            return
        try:
            self._audio_queue.put(samples, timeout=0.05)
        except queue.Full:
            pass

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self._audio_queue.put(None, timeout=0.1)
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=1.0)


class VideoSource:
    """Source vidéo basée sur OpenCV."""

    def __init__(self, path: str):
        self.path = path
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_count = 0
        self.fps = 30.0
        self.width = 0
        self.height = 0
        self.duration = 0.0

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
        return self.cap.read()

    def set_position(self, seconds: float) -> bool:
        if self.cap is None:
            return False
        msec = seconds * 1000.0
        return self.cap.set(cv2.CAP_PROP_POS_MSEC, msec)

    def release(self) -> None:
        if self.cap:
            self.cap.release()
            self.cap = None


class FrameProcessor:
    """Processeur d'image : redimensionnement, filtres, préparation ASCII."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.charset = config.charset
        self.char_len = len(self.charset)

    def adjust_gamma(self, image: np.ndarray) -> np.ndarray:
        inv_gamma = 1.0 / max(0.1, self.config.gamma)
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype(np.uint8)
        return cv2.LUT(image, table)

    def apply_filters(self, image: np.ndarray) -> np.ndarray:
        if self.config.blur:
            image = cv2.GaussianBlur(image, (3, 3), 0)
        if self.config.sharpen:
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
            image = cv2.filter2D(image, -1, kernel)
        if self.config.edge:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            image = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        return image

    def resize_for_terminal(self, image: np.ndarray, term_cols: int, term_rows: int) -> np.ndarray:
        h, w = image.shape[:2]
        aspect = h / w
        font_aspect = 2.0
        new_w = max(2, term_cols)
        new_h = max(1, int(aspect * new_w / font_aspect))
        if term_rows > 0 and new_h > term_rows:
            new_h = max(1, term_rows)
            new_w = max(2, int(new_h * font_aspect / aspect))
        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

    def frame_to_ascii_naive(self, image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if self.config.invert:
            gray = cv2.bitwise_not(gray)
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
                if val > 128:
                    ch = "#"
                else:
                    ch = " "
                row_chars.append(ch)
                row_colors.append(image[y, x])
            result.append(("".join(row_chars), np.array(row_colors)))
        return result

    def frame_to_ascii_dither(self, image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
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
                    gray[y, x + 1] = min(255, max(0, gray[y, x + 1] + error * 7 / 16))
                if y + 1 < h:
                    if x > 0:
                        gray[y + 1, x - 1] = min(255, max(0, gray[y + 1, x - 1] + error * 3 / 16))
                    gray[y + 1, x] = min(255, max(0, gray[y + 1, x] + error * 5 / 16))
                    if x + 1 < w:
                        gray[y + 1, x + 1] = min(255, max(0, gray[y + 1, x + 1] + error * 1 / 16))
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

    def process(self, image: np.ndarray, term_cols: int, term_rows: int) -> List[Tuple[str, np.ndarray]]:
        image = self.apply_filters(image)
        image = self.resize_for_terminal(image, term_cols, term_rows)
        if self.config.engine == RenderEngine.NAIVE:
            return self.frame_to_ascii_naive(image)
        elif self.config.engine == RenderEngine.BLOCK:
            return self.frame_to_ascii_block(image)
        elif self.config.engine == RenderEngine.EDGE:
            return self.frame_to_ascii_edge(image)
        elif self.config.engine == RenderEngine.DITHER:
            return self.frame_to_ascii_dither(image)
        else:
            return self.frame_to_ascii_luminance(image)


class FrameRenderer:
    """Rendu ASCII colorisé dans le terminal."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.color_utils = ColorUtils()

    def render_line_green(self, chars: str, colors: np.ndarray) -> str:
        output = ""
        for ch, color in zip(chars, colors):
            b, g, r = int(color[0]), int(color[1]), int(color[2])
            luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
            intensity = luminance / 255.0
            if self.config.color_mode == ColorMode.GREEN:
                col = self.color_utils.green_gradient(intensity)
            elif self.config.color_mode == ColorMode.MATRIX:
                col = self.color_utils.matrix_gradient(intensity)
            elif self.config.color_mode == ColorMode.TRUECOLOR:
                col = self.color_utils.truecolor_fg(r, g, b)
            else:
                col = Fore.GREEN
            output += f"{col}{ch}"
        output += Style.RESET_ALL
        return output

    def render_frame(self, ascii_data: List[Tuple[str, np.ndarray]]) -> str:
        lines: List[str] = []
        for chars, colors in ascii_data:
            lines.append(self.render_line_green(chars, colors))
        return "\n".join(lines)

    def render_to_file(self, ascii_data: List[Tuple[str, np.ndarray]], path: str) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(self.render_frame(ascii_data))
            f.write("\n")


class HUDRenderer:
    """Affichage des informations de lecture (HUD)."""

    def __init__(self, console: Console):
        self.console = console

    def render(self, source: VideoSource, current_time: float, fps: float, dropped: int, total_frames: int) -> Panel:
        progress = current_time / max(1e-6, source.duration)
        bar_width = 30
        filled = int(progress * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        text = Text()
        text.append(f"{APP_NAME} v{APP_VERSION}\n", style="bold green")
        text.append(f"Fichier : {source.path}\n")
        text.append(f"Temps   : {self._format_time(current_time)} / {self._format_time(source.duration)}\n")
        text.append(f"FPS     : {fps:.1f}\n")
        text.append(f"Frames  : {total_frames} (dropped {dropped})\n")
        text.append(f"{bar} {progress*100:.1f}%", style="green")
        return Panel(Align.left(text), title="[bold green]HUD[/bold green]", border_style="green")

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
        self.render_times: List[float] = []

    def record(self, render_time: float, frame_time: float) -> None:
        self.frames += 1
        self.total_time += frame_time
        self.render_times.append(render_time)

    def summary(self) -> str:
        if self.frames == 0:
            return "Aucune frame rendue."
        avg_frame = self.total_time / self.frames
        avg_render = sum(self.render_times) / len(self.render_times)
        return (
            f"Frames: {self.frames}\n"
            f"Temps total: {self.total_time:.2f}s\n"
            f"FPS moyen: {self.frames / max(self.total_time, 1e-6):.2f}\n"
            f"Temps moyen rendu: {avg_render*1000:.2f}ms\n"
        )


class VIDGREEN:
    """Orchestrateur principal de l'application."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.console = Console()
        self.source = VideoSource(config.input_path)
        self.processor = FrameProcessor(config)
        self.renderer = FrameRenderer(config)
        self.hud = HUDRenderer(self.console)
        self.benchmark = Benchmark()
        self.audio_player = AudioPlayer()
        self._running = False
        self._dropped_frames = 0
        self._total_frames = 0

    def run(self) -> int:
        if not self.source.open():
            self.console.print(f"[bold red]Erreur : impossible d'ouvrir {self.config.input_path}[/bold red]")
            return 1

        TerminalHelper.hide_cursor()
        TerminalHelper.set_terminal_title(f"{APP_NAME} - {self.config.input_path}")

        if self.config.start_time > 0:
            self.source.set_position(self.config.start_time)

        self._running = True
        signal.signal(signal.SIGINT, self._signal_handler)

        try:
            if self.config.use_rich and not self.config.hide_hud:
                self._run_with_hud()
            else:
                self._run_simple()
        finally:
            self._running = False
            self.source.release()
            self.audio_player.stop()
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
        if self.config.fullscreen:
            term_rows = max(1, term_rows - 2)
        else:
            term_rows = max(1, term_rows - 4)
        target_frame_time = 1.0 / max(1, self.config.fps)
        start_clock = time.perf_counter()
        frame_index = 0

        while self._running:
            t0 = time.perf_counter()
            ok, img = self.source.read()
            if not ok or img is None:
                if self.config.loop:
                    self.source.set_position(0.0)
                    continue
                break

            current_time = frame_index / max(1, self.source.fps)
            if self.config.duration > 0 and current_time > self.config.duration:
                break

            ascii_data = self.processor.process(img, term_cols, term_rows)
            rendered = self.renderer.render_frame(ascii_data)
            TerminalHelper.move_cursor_home()
            sys.stdout.write(rendered)
            sys.stdout.flush()
            if self.config.output_file:
                self.renderer.render_to_file(ascii_data, self.config.output_file)

            frame_index += 1
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
            self.benchmark.record(render_time, time.perf_counter() - t0)

    def _run_with_hud(self) -> None:
        layout = Layout()
        layout.split_column(Layout(name="video", ratio=6), Layout(name="hud", size=8))
        target_frame_time = 1.0 / max(1, self.config.fps)
        start_clock = time.perf_counter()
        frame_index = 0
        fps_display = 0.0
        last_fps_time = start_clock
        fps_frames = 0

        with Live(layout, refresh_per_second=self.config.fps, console=self.console, screen=True) as live:
            while self._running:
                t0 = time.perf_counter()
                ok, img = self.source.read()
                if not ok or img is None:
                    if self.config.loop:
                        self.source.set_position(0.0)
                        continue
                    break

                term_cols, term_rows = TerminalHelper.get_terminal_size()
                video_rows = max(1, term_rows - 8)
                current_time = self.source.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0 if self.source.cap else 0.0
                if self.config.duration > 0 and current_time > self.config.duration:
                    break

                ascii_data = self.processor.process(img, term_cols, video_rows)
                rendered = self.renderer.render_frame(ascii_data)
                layout["video"].update(Panel(rendered, border_style="green", padding=(0, 0)))

                now = time.perf_counter()
                fps_frames += 1
                if now - last_fps_time >= 1.0:
                    fps_display = fps_frames / (now - last_fps_time)
                    fps_frames = 0
                    last_fps_time = now

                hud_panel = self.hud.render(self.source, current_time, fps_display, self._dropped_frames, self._total_frames)
                layout["hud"].update(hud_panel)

                if self.config.output_file:
                    self.renderer.render_to_file(ascii_data, self.config.output_file)

                frame_index += 1
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
                self.benchmark.record(render_time, time.perf_counter() - t0)


def parse_args() -> AppConfig:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="Lecteur vidéo ASCII dans le terminal avec thème vert.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemple : python vidgreen.py video.mp4 --fullscreen --color matrix",
    )
    parser.add_argument("video", help="Chemin vers le fichier vidéo.")
    parser.add_argument("--width", "-w", type=int, default=0, help="Largeur en colonnes (0 = auto).")
    parser.add_argument("--height", "-h", type=int, default=0, help="Hauteur en lignes (0 = auto).")
    parser.add_argument("--fps", type=int, default=30, help="Limite de FPS.")
    parser.add_argument("--charset", "-c", type=str, default=DEFAULT_CHARSET, help="Jeu de caractères ASCII.")
    parser.add_argument("--color", choices=[m.value for m in ColorMode], default="green", help="Mode de couleur.")
    parser.add_argument("--engine", choices=[m.value for m in RenderEngine], default="luminance", help="Moteur de rendu.")
    parser.add_argument("--contrast", type=float, default=1.0, help="Contraste (1.0 = neutre).")
    parser.add_argument("--brightness", type=float, default=0.0, help="Luminosité (-1 à 1).")
    parser.add_argument("--gamma", type=float, default=1.0, help="Gamma (>0).")
    parser.add_argument("--invert", action="store_true", help="Inverser les couleurs.")
    parser.add_argument("--blur", action="store_true", help="Appliquer un flou.")
    parser.add_argument("--sharpen", action="store_true", help="Appliquer un sharpen.")
    parser.add_argument("--edge", action="store_true", help="Détection de contours.")
    parser.add_argument("--dither", action="store_true", help="Appliquer un dithering Floyd-Steinberg.")
    parser.add_argument("--no-audio", action="store_true", help="Désactiver l'audio.")
    parser.add_argument("--loop", action="store_true", help="Lecture en boucle.")
    parser.add_argument("--start", type=float, default=0.0, help="Temps de départ en secondes.")
    parser.add_argument("--duration", type=float, default=0.0, help="Durée maximale en secondes (0 = illimité).")
    parser.add_argument("--fullscreen", "-f", action="store_true", help="Mode plein terminal.")
    parser.add_argument("--output", "-o", type=str, default="", help="Fichier de sortie ASCII.")
    parser.add_argument("--benchmark", "-b", action="store_true", help="Afficher un benchmark.")
    parser.add_argument("--no-rich", action="store_true", help="Désactiver l'interface Rich.")
    parser.add_argument("--hide-hud", action="store_true", help="Cacher le HUD.")
    parser.add_argument("--threads", type=int, default=4, help="Nombre de threads.")
    parser.add_argument("--preview", action="store_true", help="Afficher un aperçu statique.")

    args = parser.parse_args()
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
        invert=args.invert,
        blur=args.blur,
        sharpen=args.sharpen,
        edge=args.edge,
        dither=args.dither,
        audio=not args.no_audio,
        loop=args.loop,
        start_time=args.start,
        duration=args.duration,
        fullscreen=args.fullscreen,
        output_file=args.output,
        benchmark=args.benchmark,
        use_rich=not args.no_rich,
        hide_hud=args.hide_hud,
        threads=args.threads,
        preview_mode=args.preview,
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
{Fore.LIGHTGREEN_EX}    Terminal Video Player - ASCII Green Edition v{APP_VERSION}{Style.RESET_ALL}
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
