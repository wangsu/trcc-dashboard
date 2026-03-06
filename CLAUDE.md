# CLAUDE.md

## Project Overview

trcc-dashboard is a real-time sensor dashboard for Thermalright LCD cooler screens on Linux. It renders CPU, GPU, memory, disk, and network stats using PIL/Pillow and sends frames to the LCD via trcc-linux's DeviceService.

## Architecture

Single-file Python script (`trcc_dashboard.py`) that:
1. Connects to the LCD via `trcc.cli._device._get_service()` (DeviceService)
2. Reads system metrics via `trcc.services.system.get_all_metrics()` + `pynvml` for multi-GPU
3. Renders frames with PIL/Pillow (`ImageDraw`)
4. Converts PIL Image to QImage via `QtRenderer.from_pil()` before sending
5. Sends to LCD via `DeviceService.send_pil()` in a loop

## Key Technical Detail

trcc-linux 7.1.1 has a bug: `send_pil()` calls `apply_device_rotation()` which uses `QtRenderer.apply_rotation()`. This expects QImage objects, not PIL Images. PIL Images crash silently. The workaround is to always convert PIL -> QImage before calling `send_pil()`.

## Dependencies

- trcc-linux (pip/pipx) — LCD device communication, system metrics
- nvidia-ml-py (optional) — multi-GPU stats via NVML
- Pillow — included with trcc-linux
- PySide6/Qt — included with trcc-linux (QtRenderer)

## Development

- This runs inside trcc-linux's pipx venv: `~/.local/share/pipx/venvs/trcc-linux/bin/python3`
- No separate venv or requirements.txt — everything comes from trcc-linux
- Test with `trcc detect` and `trcc test` before running the dashboard
- LCD is 320x240 (portrait native, rotated to landscape by the device protocol)

## File Structure

```
trcc_dashboard.py         # Main script (single file)
lcd-dashboard.service     # systemd unit for auto-start
README.md                 # User documentation
LICENSE                   # MIT
```

## Commands

```bash
# Run directly
~/.local/share/pipx/venvs/trcc-linux/bin/python3 trcc_dashboard.py

# Install systemd service
sudo cp lcd-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lcd-dashboard.service
```
