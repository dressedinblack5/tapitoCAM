#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== tapitoCAM Installer ==="

# ── Check system dependencies ──
echo "[1/3] Checking system dependencies..."
if ! command -v mpv &>/dev/null; then
    echo "mpv not found. Install it first:"
    echo "  sudo apt install mpv   (Debian/Ubuntu)"
    echo "  sudo pacman -S mpv     (Arch)"
    exit 1
fi
echo "       mpv — found"

# ── Install Python dependencies ──
echo "[2/3] Installing Python dependencies..."

install_python_deps() {
    python3 -m pip install --user -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null ||
    python3 -m pip install --user --break-system-packages -r "$SCRIPT_DIR/requirements.txt"
}

if ! install_python_deps; then
    echo "Error: Failed to install Python dependencies."
    echo "Try using pipx instead:"
    echo "  pipx install pyside6 python-mpv onvif-zeep"
    exit 1
fi

# ── Install files ──
echo "[3/3] Installing tapitoCAM..."

# Install scripts
install -Dm755 "$SCRIPT_DIR/tapitocam.sh"         "$HOME/.local/bin/tapitocam"
install -Dm755 "$SCRIPT_DIR/tapitocam_gui.py"      "$HOME/.local/bin/tapitocam-gui"
install -Dm755 "$SCRIPT_DIR/tapitocam_cli.py"      "$HOME/.local/bin/tapitocam-cli-helper"

# Install shared modules (needed for imports)
install -Dm644 "$SCRIPT_DIR/cameraconfig.py"        "$HOME/.local/bin/cameraconfig.py"
install -Dm644 "$SCRIPT_DIR/cameradialog.py"        "$HOME/.local/bin/cameradialog.py"
install -Dm644 "$SCRIPT_DIR/cameratile.py"          "$HOME/.local/bin/cameratile.py"
install -Dm644 "$SCRIPT_DIR/styles.py"              "$HOME/.local/bin/styles.py"
install -Dm644 "$SCRIPT_DIR/utils.py"               "$HOME/.local/bin/utils.py"

# Install desktop entry
DESKTOP_SOURCE="/home/dressedinblack/Escritorio/TapitoCAM.desktop"
DESKTOP_DEST="$HOME/.local/share/applications/tapitoCAM.desktop"

if [[ -f "$DESKTOP_SOURCE" ]]; then
    install -Dm644 "$DESKTOP_SOURCE" "$DESKTOP_DEST"
else
    # Fallback: use dist/ template
    install -Dm644 "$SCRIPT_DIR/dist/tapitoCAM.desktop" "$DESKTOP_DEST"
fi

# Fix desktop Exec path to point to installed location
sed -i "s|Exec=.*|Exec=$HOME/.local/bin/tapitocam-gui|" "$DESKTOP_DEST"

echo ""
echo "Done! Add ~/.local/bin to your PATH if not already:"
echo '  export PATH="$HOME/.local/bin:$PATH"'
echo ""
echo "Run:  tapitocam       (CLI)"
echo "      tapitocam-gui   (GUI)"