#!/usr/bin/env python3
"""Sensor dashboard for Thermalright LCD cooler screens.

Renders real-time CPU, GPU, memory, disk, and network stats on
trcc-linux compatible LCD displays (320x240 and 320x320).

Bypasses the broken trcc CLI `color`/`theme-load` commands by using
DeviceService.send_pil() directly with QImage conversion.

Requirements:
    - trcc-linux (pipx install trcc-linux)
    - nvidia-ml-py (pipx inject trcc-linux nvidia-ml-py)
    - Pillow (included with trcc-linux)

Usage:
    # Using trcc-linux's Python environment:
    ~/.local/share/pipx/venvs/trcc-linux/bin/python3 trcc_dashboard.py

    # Or if trcc's venv is on PATH:
    python3 trcc_dashboard.py

    # Options:
    python3 trcc_dashboard.py --interval 1      # update every 1 second
    python3 trcc_dashboard.py --no-gpu           # skip GPU stats (no NVIDIA)
"""
from __future__ import annotations

import argparse
import signal
import sys
import time

from PIL import Image, ImageDraw, ImageFont

from trcc.adapters.render.qt import QtRenderer
from trcc.cli._device import _get_service
from trcc.services.system import get_all_metrics

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
WHITE = (255, 255, 255)
GRAY = (120, 120, 130)
CYAN = (0, 200, 220)
GREEN = (0, 220, 100)
YELLOW = (255, 200, 0)
RED = (255, 60, 60)
ORANGE = (255, 140, 0)
BLUE = (80, 140, 255)
BG_COLOR = (10, 10, 15)
DARK_LINE = (40, 40, 50)
BAR_BG = (30, 30, 40)

_qt = QtRenderer()


def temp_color(temp: float) -> tuple:
    """Color-code temperature values."""
    if temp < 40:
        return GREEN
    if temp < 60:
        return CYAN
    if temp < 75:
        return YELLOW
    if temp < 85:
        return ORANGE
    return RED


def usage_color(pct: float) -> tuple:
    """Color-code usage percentages."""
    if pct < 30:
        return GREEN
    if pct < 60:
        return CYAN
    if pct < 80:
        return YELLOW
    return RED


def draw_bar(draw: ImageDraw.Draw, x: int, y: int, w: int, h: int,
             pct: float, color: tuple):
    """Draw a horizontal progress bar."""
    draw.rectangle([x, y, x + w, y + h], fill=BAR_BG, outline=DARK_LINE)
    fill_w = max(1, int(w * min(pct, 100) / 100))
    if fill_w > 0:
        draw.rectangle([x, y, x + fill_w, y + h], fill=color)


# ---------------------------------------------------------------------------
# GPU stats via pynvml (supports multiple GPUs)
# ---------------------------------------------------------------------------

def get_gpu_stats() -> list[dict]:
    """Read stats from all NVIDIA GPUs."""
    try:
        import pynvml
    except ImportError:
        return []

    gpus = []
    try:
        pynvml.nvmlInit()
        for i in range(pynvml.nvmlDeviceGetCount()):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            util = pynvml.nvmlDeviceGetUtilizationRates(h)
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            gpus.append({
                "name": pynvml.nvmlDeviceGetName(h),
                "temp": pynvml.nvmlDeviceGetTemperature(h, 0),
                "usage": util.gpu,
                "clock": pynvml.nvmlDeviceGetClockInfo(h, 0),
                "power": pynvml.nvmlDeviceGetPowerUsage(h) / 1000,
                "mem_used": mem.used / (1024**2),
                "mem_total": mem.total / (1024**2),
            })
        pynvml.nvmlShutdown()
    except Exception:
        pass
    return gpus


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

# Common font paths across Linux distros
_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans{style}.ttf",        # Debian/Ubuntu
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans{style}.ttf",       # Fedora
    "/usr/share/fonts/TTF/DejaVuSans{style}.ttf",                     # Arch
    "/usr/share/fonts/truetype/liberation/LiberationSans{style}.ttf",  # fallback
]


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Try to load a TrueType font, fall back to default."""
    style = "-Bold" if bold else ""
    for pattern in _FONT_PATHS:
        path = pattern.format(style=style)
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Frame renderer
# ---------------------------------------------------------------------------

def render_frame(metrics, gpus: list[dict], width: int, height: int,
                 hostname: str, hw_label: str) -> Image.Image:
    """Render a single dashboard frame."""
    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    font_lg = _load_font(16, bold=True)
    font_md = _load_font(13)
    font_sm = _load_font(11)

    right_edge = width - 8
    bar_width = width - 16

    # Header: hostname + time
    time_str = f"{metrics.time_hour:02d}:{metrics.time_minute:02d}:{metrics.time_second:02d}"
    draw.text((8, 5), hostname, fill=CYAN, font=font_lg)
    draw.text((right_edge - 80, 6), time_str, fill=WHITE, font=font_md)

    days = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    dow = days[metrics.day_of_week] if 0 <= metrics.day_of_week < 7 else "---"
    date_str = f"{metrics.date_year}/{metrics.date_month:02d}/{metrics.date_day:02d} {dow}"
    draw.text((right_edge - 80, 21), date_str, fill=GRAY, font=font_sm)

    y = 34
    draw.line([(8, y), (right_edge, y)], fill=DARK_LINE, width=1)

    # CPU
    y = 38
    cpu_temp = metrics.cpu_temp or 0
    cpu_pct = metrics.cpu_percent or 0
    cpu_freq = (metrics.cpu_freq or 0) / 1000
    cpu_power = metrics.cpu_power or 0

    draw.text((8, y), "CPU", fill=CYAN, font=font_md)
    draw.text((48, y), f"{cpu_temp:.0f}C", fill=temp_color(cpu_temp), font=font_md)
    draw.text((100, y), f"{cpu_pct:.0f}%", fill=usage_color(cpu_pct), font=font_md)
    draw.text((148, y + 1), f"{cpu_freq:.1f}GHz", fill=GRAY, font=font_sm)
    draw.text((225, y + 1), f"{cpu_power:.0f}W", fill=GRAY, font=font_sm)

    y += 16
    draw_bar(draw, 8, y, bar_width, 7, cpu_pct, usage_color(cpu_pct))

    # GPUs
    for i, gpu in enumerate(gpus):
        y += 16
        gpu_temp = gpu["temp"]
        gpu_usage = gpu["usage"]
        gpu_clock = gpu["clock"]
        gpu_power = gpu["power"]
        gpu_vram = gpu["mem_used"]
        gpu_vram_total = gpu["mem_total"]
        vram_pct = (gpu_vram / gpu_vram_total * 100) if gpu_vram_total else 0

        label = f"GPU{i}" if len(gpus) > 1 else "GPU"
        draw.text((8, y), label, fill=GREEN, font=font_md)
        draw.text((48, y), f"{gpu_temp:.0f}C", fill=temp_color(gpu_temp), font=font_md)
        draw.text((100, y), f"{gpu_usage:.0f}%", fill=usage_color(gpu_usage), font=font_md)
        draw.text((148, y + 1), f"{gpu_clock}MHz", fill=GRAY, font=font_sm)
        draw.text((225, y + 1), f"{gpu_power:.0f}W", fill=GRAY, font=font_sm)
        draw.text((268, y + 1), f"{gpu_vram:.0f}M", fill=GRAY, font=font_sm)

        y += 16
        half_bar = bar_width // 2 - 4
        draw_bar(draw, 8, y, half_bar, 7, gpu_usage, usage_color(gpu_usage))
        draw_bar(draw, 8 + half_bar + 8, y, half_bar, 7, vram_pct, BLUE)

    # Separator
    y += 14
    draw.line([(8, y), (right_edge, y)], fill=DARK_LINE, width=1)

    # Memory
    y += 4
    mem_pct = metrics.mem_percent or 0
    mem_avail = (metrics.mem_available or 0) / 1024

    draw.text((8, y), "MEM", fill=BLUE, font=font_md)
    draw.text((48, y), f"{mem_pct:.0f}%", fill=usage_color(mem_pct), font=font_md)
    draw.text((100, y + 1), f"{mem_avail:.1f}GB free", fill=GRAY, font=font_sm)

    y += 16
    draw_bar(draw, 8, y, bar_width, 7, mem_pct, usage_color(mem_pct))

    # Disk + Network
    y += 14
    disk_temp = metrics.disk_temp or 0
    net_up = metrics.net_up or 0
    net_down = metrics.net_down or 0

    draw.text((8, y), "SSD", fill=ORANGE, font=font_md)
    draw.text((48, y), f"{disk_temp:.0f}C", fill=temp_color(disk_temp), font=font_md)
    draw.text((110, y), "NET", fill=YELLOW, font=font_md)
    draw.text((150, y + 1), f"U:{net_up:.1f} D:{net_down:.1f} MB/s", fill=GRAY, font=font_sm)

    # Bottom
    y = height - 16
    draw.line([(8, y - 3), (right_edge, y - 3)], fill=DARK_LINE, width=1)
    draw.text((8, y), hw_label, fill=GRAY, font=font_sm)

    return img


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sensor dashboard for Thermalright LCD cooler screens")
    parser.add_argument("--interval", type=float, default=2,
                        help="Update interval in seconds (default: 2)")
    parser.add_argument("--hostname", type=str, default=None,
                        help="Hostname to display (default: auto-detect)")
    parser.add_argument("--label", type=str, default=None,
                        help="Hardware label for bottom line (default: auto-detect)")
    parser.add_argument("--no-gpu", action="store_true",
                        help="Skip GPU stats (for systems without NVIDIA GPUs)")
    args = parser.parse_args()

    # Auto-detect hostname
    if args.hostname is None:
        import socket
        args.hostname = socket.gethostname()

    # Auto-detect hardware label
    if args.label is None:
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        cpu_name = line.split(":")[1].strip()
                        # Shorten common prefixes
                        for prefix in ["AMD ", "Intel(R) Core(TM) ", "Intel "]:
                            cpu_name = cpu_name.replace(prefix, "")
                        cpu_name = cpu_name.split(" @")[0].strip()
                        break
                else:
                    cpu_name = "Unknown CPU"
        except Exception:
            cpu_name = "Unknown CPU"

        gpus_init = get_gpu_stats() if not args.no_gpu else []
        if gpus_init:
            gpu_name = gpus_init[0]["name"]
            # Shorten GPU names
            gpu_name = gpu_name.replace("NVIDIA GeForce ", "").replace("NVIDIA ", "")
            gpu_count = len(gpus_init)
            gpu_mem = int(gpus_init[0]["mem_total"] / 1024)
            if gpu_count > 1:
                gpu_label = f"{gpu_count}x {gpu_name} {gpu_mem}GB"
            else:
                gpu_label = f"{gpu_name} {gpu_mem}GB"
            args.label = f"{cpu_name} | {gpu_label}"
        else:
            args.label = cpu_name

    print(f"Connecting to LCD...")
    svc = _get_service()
    dev = svc.selected
    if not dev:
        print("No LCD device found. Make sure trcc detects your device:")
        print("  trcc detect")
        sys.exit(1)

    width, height = dev.resolution
    print(f"Device: {dev.path} ({width}x{height})")
    print(f"Hostname: {args.hostname}")
    print(f"Label: {args.label}")
    print(f"GPU monitoring: {'off' if args.no_gpu else 'on'}")
    print(f"Update interval: {args.interval}s")
    print(f"Dashboard running. Ctrl+C to stop.")

    running = True

    def stop(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    while running:
        try:
            metrics = get_all_metrics()
            gpus = get_gpu_stats() if not args.no_gpu else []
            pil_img = render_frame(metrics, gpus, width, height,
                                   args.hostname, args.label)
            qimg = _qt.from_pil(pil_img)
            svc.send_pil(qimg, width, height)
            time.sleep(args.interval)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

    print("\nDashboard stopped.")


if __name__ == "__main__":
    main()
