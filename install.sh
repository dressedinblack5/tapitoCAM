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
python3 -m pip install --user -r "$SCRIPT_DIR/requirements.txt"

# ── Install files ──
echo "[3/3] Installing tapitoCAM..."

# Install scripts
install -Dm755 "$SCRIPT_DIR/tapitocam.sh"         "$HOME/.local/bin/tapitocam"
install -Dm755 "$SCRIPT_DIR/tapitocam_gui.py"     "$HOME/.local/bin/tapitocam-gui"

# Install desktop entry (for current user only)
install -Dm644 "$SCRIPT_DIR/tapitoCAM.desktop"    "$HOME/.local/share/applications/tapitoCAM.desktop"

# Fix desktop Exec path to point to installed location
sed -i "s|Exec=tapitocam_gui.py|Exec=$HOME/.local/bin/tapitocam-gui|" \
    "$HOME/.local/share/applications/tapitoCAM.desktop"

echo ""
echo "Done! Add ~/.local/bin to your PATH if not already:"
echo '  export PATH="$HOME/.local/bin:$PATH"'
echo ""
echo "Run:  tapitocam       (CLI)"
echo "      tapitocam-gui   (GUI)"
