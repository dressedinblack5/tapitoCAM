# tapitoCAM

TP-Link Tapo Camera RTSP Client for Linux — multi-camera control center.

![GUI Preview](assets/gui-preview.png)
![Tapo Camera Preview](assets/tc-preview.png)

## Features

- **Multi-camera support** — add, edit, and remove any number of Tapo cameras
- **Standalone mpv streaming** — one mpv window per camera (no embedded video; works great on Wayland)
- **PTZ control** — pan, tilt, zoom via ONVIF for each camera
- **HD / SD quality** — select stream1 (HD) or stream2 (SD) per camera
- **Camera Manager** — dedicated dialog for managing camera list, credentials, and IPs
- **CLI** — multi-camera RTSP viewer with quality selection
- **Secure credential handling** — OS keyring support, credential-free process listing

## Prerequisites

- **RTSP-compatible Tapo camera** (e.g., C200, C310, C320WS)
- **mpv** — video player (`apt install mpv`)
- **Python 3.10+** with PySide6 and onvif-zeep (for GUI):
  ```bash
  pip install pyside6 onvif-zeep
  ```
- **keyring** (optional) — for secure password storage in the OS keychain:
  ```bash
  pip install keyring
  ```

You also need to create a dedicated **Camera Account** in the Tapo app for RTSP access:

1. Open the Tapo app and select your camera.
2. Tap the gear icon → **Advanced Settings** → **Camera Account**.
3. Create a username and password (separate from your main TP-Link account).
4. Use these credentials with tapitoCAM to connect via the camera's local IP.

## Quick install

```bash
git clone https://github.com/dressedinblack5/tapitoCAM.git
cd tapitoCAM
./install.sh
```

This installs `tapitocam` (CLI) and `tapitocam-gui` to `~/.local/bin/` and
registers the desktop app.  Add `~/.local/bin` to your `PATH` if needed:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Run without installing

```bash
git clone https://github.com/dressedinblack5/tapitoCAM.git
cd tapitoCAM
./tapitocam.sh       # CLI
./tapitocam_gui.py   # GUI
```

## GUI Usage

### First launch

On first launch the GUI shows an empty control panel. Click **Manage** to
open the Camera Manager dialog and add your first camera.

### Camera Manager

- **+ Add** — enter a name, username, password, IP, and quality (HD/SD)
- **✏ Edit** — modify an existing camera's settings
- **✕ Remove** — delete a camera
- IP addresses are validated on save (each octet 0–255)
- Passwords are stored in the OS keyring when available (GNOME Keyring,
  KDE Wallet, macOS Keychain); a base64-encoded fallback copy is kept in
  `~/.config/tapitocam/cameras.json` with `0o600` permissions

### Streaming

- Select a camera from the dropdown, click **▶ Open Stream**
- mpv launches in its own window (one per camera)
- Use **■ Stop Stream** to close it, or **Start All / Stop All** for batch control
- If mpv cannot connect (wrong IP, unreachable host), the GUI shows the
  connection error on the status bar and kills the stuck process within 2 seconds
- The RTSP URL (containing credentials) is never exposed on the command line;
  it is written to a private temp file and passed to mpv via `--playlist`

### PTZ

Pan, tilt, and zoom buttons fire ONVIF continuous moves. The camera must
support ONVIF (most Tapo C-series models do). PTZ connects asynchronously
in a background thread — the UI stays responsive during the 1–3 s handshake.

### CLI Options

```
Usage: tapitocam.sh [OPTIONS]

  -h, --help          Show this help message
  -r, --reset         Reset saved configuration
  -i, --ip IP         Set camera IP address (overrides saved config)
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

## Uninstall

```bash
rm -f ~/.local/bin/tapitocam ~/.local/bin/tapitocam-gui \
      ~/.local/bin/tapitocam-cli-helper \
      ~/.local/bin/cameraconfig.py ~/.local/bin/cameradialog.py \
      ~/.local/bin/cameratile.py ~/.local/bin/styles.py ~/.local/bin/utils.py \
      ~/.local/share/applications/tapitoCAM.desktop
rm -rf ~/.config/tapitocam
```

## Security

tapitoCAM handles camera credentials and takes the following measures:

| Measure | What it does |
|---------|-------------|
| **Keyring storage** | Passwords are stored in the OS keyring (GNOME Keyring, KDE Wallet, macOS Keychain) when available. The config file keeps a base64-encoded fallback copy with `0o600` permissions.  Install `keyring` (`pip install keyring`) to enable this. |
| **Playlist approach** | The RTSP URL (containing username:password) is written to a private temp file (`0o600`) and passed to mpv via `--playlist=<file>`. Credentials never appear in `ps aux` or `/proc/<pid>/cmdline`.  Temp files are cleaned up on stream stop, app close, and crash. |
| **Error sanitization** | ONVIF connection error messages are sanitized before display — credential-like patterns (`user:pass@host`, `password=XXX`) are stripped from status bar messages. |
| **Config file** | `~/.config/tapitocam/cameras.json` is created with `0o600` permissions (owner read/write only). |
| **Subprocess safety** | mpv is spawned via `subprocess.Popen` with a list argv (no `shell=True`), preventing command injection. |

**Known limitations:**

- ONVIF connections use HTTP (no TLS) — credentials are sent in cleartext over the LAN. Use on a trusted network only.
- The CLI (`tapitocam.sh`) writes the RTSP URL to a temp file for mpv's `--playlist` flag. This file is created with `0o600` and deleted after use, but the password briefly touches disk.
- If the `keyring` library is not installed, passwords in the config file are only base64-encoded (not encrypted).

## Notes

- Config is stored in `~/.config/tapitocam/cameras.json` (one per system).
  Legacy `.tapitocam.env` is auto-migrated on first launch.
- Username and password are URL-encoded automatically for the RTSP URL.
- mpv is launched as a standalone subprocess per camera. This avoids Wayland
  window-embedding issues and keeps each stream isolated.
- Temporary mpv logs are discarded; connection and authorization errors are
  captured from stderr and displayed on the GUI status bar with distinct
  messages.
- Use `stream1` for HD and `stream2` for SD (useful on slow networks).
- Authorization errors (wrong username/password) are detected and shown as
  distinct messages on the status bar for both RTSP streams and PTZ connection.
