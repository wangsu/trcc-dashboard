# trcc-dashboard

A real-time sensor dashboard for Thermalright LCD cooler screens on Linux.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Renders live CPU, GPU, memory, disk, and network stats on the small LCD displays found on Thermalright AIO coolers (like the FW 360). Built on top of [trcc-linux](https://github.com/Lexonight1/thermalright-trcc-linux).

## Features

- CPU: temperature, usage, frequency, power
- GPU: temperature, usage, clock, power, VRAM (multi-GPU support via pynvml)
- Memory: usage percentage, free GB
- Disk: SSD temperature
- Network: upload/download speeds
- Clock and date display
- Color-coded values (green/cyan/yellow/orange/red)
- Auto-detects hostname, CPU model, and GPU names
- Works with 320x240 and 320x320 LCD screens

## Why This Exists

trcc-linux 7.1.1 has a bug where CLI commands like `trcc color` and `trcc theme-load` silently fail on HID Type 2 devices. The issue is that these commands create PIL Images internally, but the send pipeline uses the Qt renderer which expects QImage objects. The PIL Image hits `QtRenderer.apply_rotation()` and crashes silently.

This dashboard bypasses the broken code path by:
1. Rendering frames with PIL/Pillow (full drawing API)
2. Converting to QImage via `QtRenderer.from_pil()`
3. Sending via `DeviceService.send_pil()` directly

The `trcc test` command works because it creates images through `ImageService.solid_color()` which already returns QImage objects.

## Requirements

- Linux with a Thermalright LCD cooler connected via USB
- [trcc-linux](https://github.com/Lexonight1/thermalright-trcc-linux) installed and detecting your device
- NVIDIA GPU (optional, for GPU stats)

## Installation

### 1. Install trcc-linux (if not already)

```bash
pipx install trcc-linux
pipx inject trcc-linux nvidia-ml-py   # optional, for GPU monitoring
sudo trcc setup-udev                   # USB permissions
# Unplug and replug the USB cable
```

### 2. Verify trcc detects your device

```bash
trcc detect
# Should show: Active: 0416:5302 — USBDISPLAY [0416:5302] (HID)

trcc test
# Should cycle colors on the LCD
```

### 3. Install the dashboard

```bash
git clone https://github.com/your-username/trcc-dashboard.git
cp trcc-dashboard/trcc_dashboard.py ~/trcc_dashboard.py
```

### 4. Run it

```bash
~/.local/share/pipx/venvs/trcc-linux/bin/python3 ~/trcc_dashboard.py
```

## Usage

```bash
# Default: auto-detect everything, update every 2 seconds
python3 trcc_dashboard.py

# Custom update interval
python3 trcc_dashboard.py --interval 1

# Custom hostname display
python3 trcc_dashboard.py --hostname myserver

# Custom hardware label (bottom line)
python3 trcc_dashboard.py --label "Ryzen 9 5900X | 2x RTX 3060"

# No NVIDIA GPU (CPU-only system)
python3 trcc_dashboard.py --no-gpu
```

## Auto-Start on Boot (systemd)

```bash
# Edit the service file to match your paths:
#   - User: your username
#   - ExecStart: path to trcc-linux's python3 and the dashboard script

sudo cp lcd-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lcd-dashboard.service
sudo systemctl start lcd-dashboard.service

# Check status
sudo systemctl status lcd-dashboard

# View logs
sudo journalctl -u lcd-dashboard -f
```

## Tested Hardware

| Cooler | LCD | Resolution | Protocol | Status |
|--------|-----|------------|----------|--------|
| Thermalright FW 360 White ARGB | 2.4" IPS | 320x240 | HID Type 2 | Working |

If you test on other Thermalright models, please open an issue or PR to update this table.

## Troubleshooting

**LCD stays on boot logo**

Make sure `trcc test` works first. If the color cycle displays on the screen, the dashboard will work too.

**`trcc test` doesn't work either**

- Run `trcc detect` to confirm device detection
- Run `sudo trcc setup-udev` and replug the USB cable
- Check `trcc hid-debug` for handshake status

**No GPU stats showing**

- Install nvidia-ml-py: `pipx inject trcc-linux nvidia-ml-py`
- Or run with `--no-gpu` for CPU-only systems

**Font rendering issues**

The dashboard looks for DejaVu Sans fonts. Install them if missing:

```bash
# Debian/Ubuntu
sudo apt install fonts-dejavu-core

# Fedora
sudo dnf install dejavu-sans-fonts

# Arch
sudo pacman -S ttf-dejavu
```

## License

MIT

## Acknowledgments

- [Lexonight1/thermalright-trcc-linux](https://github.com/Lexonight1/thermalright-trcc-linux) — the trcc-linux project that makes this possible
- [NVIDIA nvidia-ml-py](https://pypi.org/project/nvidia-ml-py/) — Python bindings for NVML
