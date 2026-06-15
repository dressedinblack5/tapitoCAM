# tapitoCAM

TP-Link Tapo Camera RTSP Client for Linux — multi-camera control center.

![GUI Preview](assets/gui-preview.png)
![Tapo Camera Preview](assets/tc-preview.png)

## Features

- **Multi-camera support** — add, edit, and remove any number of Tapo cameras
- **Standalone mpv streaming** — one mpv window per camera (no embedded video; works great on Wayland)
- **Full PTZ control** — pan, tilt, zoom, presets via ONVIF
- **Motion detection** — PullPoint event polling with live indicator
- **HD / SD quality** — select stream1 (HD) or stream2 (SD) per camera
- **Camera Manager** — dedicated dialog for managing camera list, credentials, and IPs
- **CLI** — command-line RTSP viewer with quality selection
- **Secure credentials** — OS keyring storage, no credentials in process listings

## Prerequisites

- **RTSP-compatible Tapo camera** (e.g., C200, C310, C320WS)
- **mpv** — video player
  ```bash
  sudo apt install mpv
  ```
- **Python 3.10+** with PySide6 and onvif-zeep:
  ```bash
  pip install pyside6 onvif-zeep
  ```
- **keyring** (optional) — OS keychain password storage:
  ```bash
  pip install keyring
  ```

### Camera Account Setup

1. Open the Tapo app and select your camera
2. Gear icon → **Advanced Settings** → **Camera Account**
3. Create a username and password (separate from your TP-Link account)
4. Use these credentials in tapitoCAM

## Quick Install

```bash
git clone https://github.com/dressedinblack5/tapitoCAM.git
cd tapitoCAM
./install.sh
```

This installs `tapitocam` (CLI) and `tapitocam-gui` to `~/.local/bin/`.
Add to PATH if needed: `export PATH="$HOME/.local/bin:$PATH"`

### Run Without Installing

```bash
git clone https://github.com/dressedinblack5/tapitoCAM.git
cd tapitoCAM
./tapitocam.sh       # CLI
./tapitocam_gui.py   # GUI
```

## GUI Usage

### First Launch

Click **Manage** to open the Camera Manager and add your first camera.

### Camera Manager

- **+ Add** — name, username, password, IP, quality (HD/SD)
- **✏ Edit** — modify an existing camera
- **✕ Remove** — delete a camera
- IP addresses validated on save; passwords stored in OS keychain (keyring)

### Streaming

- Select a camera → click **▶ Open Stream**
- mpv launches in its own window (one per camera)
- **■ Stop Stream** to close, or **Start All / Stop All** for batch
- The RTSP URL is never exposed on the command line — credentials are
  hidden from `ps aux` and `/proc`
- Connection errors (unreachable host, auth failure) are shown persistently
  in the status bar until the next event

### PTZ Controls

```
         ▲              Pan / Tilt  —  press & hold to move
      ◀  ■  ▶           Stop        —  release or click ■
         ▼              Zoom        —  press & hold 🔍+ or 🔍-
       🔍-  🔍+

  [Preset ▼]  ▶  💾  🗑            Presets — recall, save (with name prompt), delete
```

All controls are locked until the camera is streaming. PTZ connects
asynchronously in the background — the UI stays responsive during the
1–3 second ONVIF handshake.

**Presets** are stored on the camera via ONVIF and cached locally in
`cameras.json` to survive camera reboots. Each camera's presets are
isolated — switching cameras loads that camera's preset list automatically.

### Motion Detection

The camera's built-in `CellMotionDetector` is polled via ONVIF PullPoint
events. A motion indicator (⚫/🔴) appears in the info panel next to the
streaming status. Detection starts when streaming begins and stops when
the stream closes. Unreachable cameras show a one-time status bar notice
and stop retrying.

## CLI

```
Usage: tapitocam [OPTIONS]

  -h, --help          Show help
  -r, --reset         Reset saved configuration
  -i, --ip IP         Set camera IP (overrides saved config)
  -c, --camera ID     Select camera by ID (default: 0)
  -q, --quality HD|SD Select stream quality (default: HD)
  -l, --list          List configured cameras
```

Examples:
```bash
tapitocam -i 192.168.1.100
tapitocam -c 1 -q sd
tapitocam --list
tapitocam --reset
```

## Security

| Measure | What it does |
|---------|-------------|
| **Keyring storage** | Passwords stored in OS keychain (GNOME Keyring, KDE Wallet, macOS Keychain). Fallback base64 copy in config with `0o600`. |
| **Playlist approach** | RTSP URL written to private temp file (`0o600`), passed to mpv via `--playlist`. Never visible in `ps` or `/proc`. |
| **Error sanitization** | ONVIF error messages stripped of credential-like patterns before display. |
| **Config permissions** | `~/.config/tapitocam/cameras.json` created with `0o600` (owner read/write only). |
| **Safe subprocess** | mpv spawned via `subprocess.Popen` with a list argv — no `shell=True`, no injection risk. |

**Known limitations:**
- ONVIF uses HTTP (no TLS) — credentials travel in cleartext over the LAN
- CLI writes RTSP URL to temp file briefly (deleted after use, `0o600`)
- Without keyring, config passwords are base64-encoded only (not encrypted)
- Tapo cameras have a 1-subscription PullPoint limit; motion detection
  retries with exponential backoff until a slot is free

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

## Notes

- Config: `~/.config/tapitocam/cameras.json` (legacy `.tapitocam.env` auto-migrated)
- Credentials are URL-encoded automatically for the RTSP URL
- mpv launched as standalone subprocess per camera — no Wayland embedding issues
- `stream1` = HD, `stream2` = SD (useful on slow networks)
- Auth errors (wrong user/password) detected for both RTSP and PTZ connections
- Error messages persist on the status bar until replaced by the next event
- Compatible with Debian and Arch (packaging files in `dist/`)
