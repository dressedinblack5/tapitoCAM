# tapitoCAM

TP-Link Tapo Camera RTSP Client for Linux.

![CLI Preview](assets/cli-preview.png)
![Tapo Camera Preview](assets/tc-preview.png)

## Prerequisites

- **RTSP-compatible Tapo camera** (e.g., C200, C310, C320WS)
- **mpv** — video player (`apt install mpv`)
- **Python 3.10+ and PySide6** (for GUI):
  ```bash
  pip install pyside6 python-mpv onvif-zeep
  ```

You also need to create a dedicated **Camera Account** in the Tapo app for RTSP access:

1. Open the Tapo app and select your camera.
2. Tap the gear icon → **Advanced Settings** → **Camera Account**.
3. Create a username and password (separate from your main TP-Link account).
4. Use these credentials with tapitoCAM to connect via the camera's local IP.

## How to use

1. Clone and enter the repository:
   ```bash
   git clone https://github.com/dressedinblack5/tapitoCAM.git ~/Downloads/tapitoCAM
   cd ~/Downloads/tapitoCAM
   ```

2. Run the script:

   **CLI (lightweight):**
   ```bash
   ./tapitocam.sh
   ```

   **GUI (PTZ controls):**
   ```bash
   ./tapitocam_gui.py
   ```

On first run you'll be prompted for your Tapo username, password, and camera IP.
Credentials are saved to `.tapitocam.env` (stored with `chmod 600` in the script directory).

You can also launch the GUI from your app launcher — the included `tapitoCAM.desktop`
file registers `tapitocam_gui.py` as a desktop application.

### CLI Options

```
Usage: tapitocam.sh [OPTIONS]

  -h, --help       Show this help message
  -r, --reset      Reset saved configuration
  -i, --ip IP      Set camera IP address (overrides saved config)
```

Examples:
```bash
./tapitocam.sh -i 192.168.1.100
./tapitocam.sh --reset
```

## Notes

- Username and password are URL-encoded automatically to handle special characters.
- IP addresses are validated (each octet 0-255).
- Temporary mpv logs are cleaned up automatically on exit.
- The GUI supports PTZ (pan/tilt/zoom) control via ONVIF and stream quality selection.
- Use `stream1` for HD and `stream2` for SD (useful on slow networks).
