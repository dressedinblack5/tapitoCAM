# tapitoCAM

TP-Link Tapo Camera RTSP Client for Linux — multi-camera control center.

![GUI Preview](assets/gui-preview.png)
![Tapo Camera Preview](assets/tc-preview.png)

## Features

- Multi-camera support — any number of Tapo cameras
- Standalone mpv streaming — one window per camera (Wayland-friendly)
- Full PTZ — pan, tilt, zoom, presets via ONVIF
- Motion detection — live ⚫/🔴 indicator
- HD / SD quality per camera
- OS keyring password storage
- CLI viewer with quality selection

## Install

```bash
git clone https://github.com/dressedinblack5/tapitoCAM.git
cd tapitoCAM
./install.sh
```

Requires: `mpv`, `python3`, `pyside6`, `onvif-zeep`. Optional: `keyring`.

Or run without installing: `./tapitocam_gui.py` (GUI) / `./tapitocam.sh` (CLI).

### Camera Setup

Create a **Camera Account** in the Tapo app: gear → Advanced Settings → Camera Account.

## Usage

### PTZ Controls

```
         ▲              Pan / Tilt — hold to move
      ◀  ■  ▶           Stop       — click ■
         ▼              Zoom       — hold 🔍+ or 🔍-
       🔍-  🔍+

  [Preset ▼]  ▶  💾  🗑            Recall / Save / Delete
```

Controls lock until streaming. PTZ connects async (1–3s), UI stays responsive.

Motion indicator (⚫/🔴) updates when the camera detects movement.

Presets are stored on the camera and cached locally. Each camera's presets
are isolated. Saving a preset prompts for a name.

### CLI

```
tapitocam -i 192.168.1.100
tapitocam -c 1 -q sd
tapitocam --list
```

## Security

Credentials are stored in the OS keyring (fallback: base64 `0o600` JSON).
The RTSP URL is never exposed on the command line — passed to mpv via `--playlist`.
Error messages are sanitized before display.

**Known:** ONVIF uses HTTP (no TLS). CLI writes RTSP URL to temp file briefly.

## Uninstall

```bash
rm -f ~/.local/bin/tapitocam ~/.local/bin/tapitocam-gui \
      ~/.local/bin/tapitocam-cli-helper \
      ~/.local/bin/cameraconfig.py ~/.local/bin/cameradialog.py \
      ~/.local/bin/cameratile.py ~/.local/bin/motionmonitor.py \
      ~/.local/bin/styles.py ~/.local/bin/utils.py \
      ~/.local/share/applications/tapitoCAM.desktop
rm -rf ~/.config/tapitocam
```
