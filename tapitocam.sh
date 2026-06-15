#!/bin/bash
# tapitocam.sh - TP-Link Tapo Camera RTSP Client

set -o pipefail

VERSION="1.2.0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${HOME}/.config/tapitocam"
ENV_FILE="${CONFIG_DIR}/.tapitocam.env"
PYTHON_HELPER="${SCRIPT_DIR}/tapitocam_cli.py"
# Fall back to system-wide installed helper
[[ -f "$PYTHON_HELPER" ]] || PYTHON_HELPER="$(command -v tapitocam_cli.py 2>/dev/null || true)"

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
check_deps() {
    local missing=0 cmd
    for cmd in mpv mktemp python3; do
        if ! command -v "$cmd" &>/dev/null; then
            echo "Error: '$cmd' is not installed."
            missing=1
        fi
    done
    [[ $missing -eq 0 ]]
}

# ---------------------------------------------------------------------------
# Config I/O — uses Python helper for JSON, falls back to .env
# ---------------------------------------------------------------------------
load_config() {
    local cam_index="${1:-0}"

    # Try JSON via Python helper first
    if [[ -f "$PYTHON_HELPER" ]]; then
        local output
        output=$(python3 "$PYTHON_HELPER" --camera "$cam_index" 2>/dev/null) && {
            eval "$output"
            return 0
        }
    fi

    # Fallback: legacy .env
    [[ -f "$ENV_FILE" ]] || return 1
    local line
    while IFS= read -r line; do
        [[ "$line" =~ ^#         ]] && continue
        [[ -z "$line"            ]] && continue
        [[ "$line" =~ ^TAPO_USER=(.*)$ ]] && TAPO_USER="${BASH_REMATCH[1]}"
        [[ "$line" =~ ^TAPO_PASS=(.*)$ ]] && TAPO_PASS=$(printf '%s' "${BASH_REMATCH[1]}" | base64 -d 2>/dev/null || printf '%s' "${BASH_REMATCH[1]}")
        [[ "$line" =~ ^TAPO_IP=(.*)$   ]] && TAPO_IP="${BASH_REMATCH[1]}"
        [[ "$line" =~ ^TAPO_QUALITY=(.*)$ ]] && TAPO_QUALITY="${BASH_REMATCH[1]}"
    done < "$ENV_FILE"
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
urlencode() {
    local str="$1" i c
    for ((i = 0; i < ${#str}; i++)); do
        c="${str:i:1}"
        case "$c" in
            [-._~a-zA-Z0-9]) printf '%s' "$c" ;;
            *) printf '%%%02X' "'$c" ;;
        esac
    done
}

validate_ip() {
    local ip="$1" octets
    [[ "$ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]] || return 1
    IFS='.' read -ra octets <<< "$ip"
    for octet in "${octets[@]}"; do
        ((octet >= 0 && octet <= 255)) || return 1
    done
    return 0
}

# ---------------------------------------------------------------------------
# Interactive setup (saves to JSON via Python helper)
# ---------------------------------------------------------------------------
setup_config() {
    echo "--- tapitoCAM Configuration ---"
    read -r -p "Enter Camera Name (e.g., Front Door): " TAPO_NAME
    read -r -p "Enter Tapo Username: " TAPO_USER
    read -r -s -p "Enter Tapo Password: " TAPO_PASS
    echo
    read -r -p "Enter Camera IP (e.g., 192.168.1.100): " TAPO_IP
    if ! validate_ip "$TAPO_IP"; then
        echo "Warning: The entered IP address appears invalid."
    fi
    read -r -p "Quality (hd/sd) [hd]: " TAPO_QUALITY
    TAPO_QUALITY="${TAPO_QUALITY:-hd}"

    read -r -p "Save this camera? (y/n): " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        # Write via Python helper (or directly if Python not available)
        if [[ -f "$PYTHON_HELPER" ]]; then
            python3 -c "
import json, sys
from pathlib import Path
p = Path.home() / '.config' / 'tapitocam' / 'cameras.json'
p.parent.mkdir(parents=True, exist_ok=True)
try:
    with open(p) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {'version': 1, 'cameras': []}
cameras = data.get('cameras', [])
new_id = max((c['id'] for c in cameras), default=-1) + 1
cameras.append({
    'id': new_id,
    'name': '${TAPO_NAME:-Camera $new_id}',
    'username': '$TAPO_USER',
    'password': '$TAPO_PASS',
    'ip': '$TAPO_IP',
    'quality': '$TAPO_QUALITY',
})
data['cameras'] = cameras
with open(p, 'w') as f:
    json.dump(data, f, indent=2)
print(f'Camera saved (id={new_id})')
" 2>/dev/null && echo "Settings saved." || {
            # Fallback to legacy .env
            save_env_config
        }
    fi
}

save_env_config() {
    mkdir -p "$CONFIG_DIR"
    {
        echo "# tapitoCAM configuration"
        echo "TAPO_USER=$TAPO_USER"
        echo "TAPO_PASS=$(printf '%s' "$TAPO_PASS" | base64 -w0)"
        echo "TAPO_IP=$TAPO_IP"
        echo "TAPO_QUALITY=${TAPO_QUALITY:-hd}"
    } > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
}

# ---------------------------------------------------------------------------
# Stream
# ---------------------------------------------------------------------------
is_network_error() {
    local log="$1"
    grep -Eiq "No route to host|Connection timed out|Connection refused|Failed to resolve|Failed to connect|Connection reset|Network is unreachable" "$log"
}

show_network_error() {
    local log="$1"
    grep -Ei "No route to host|Connection timed out|Connection refused|Failed to resolve|Failed to connect|Connection reset|Network is unreachable" "$log" | head -1
}

run_stream() {
    local quality="${1:-stream1}"
    [[ "$quality" == "sd" ]] && quality="stream2"

    local rtsp_url
    rtsp_url="rtsp://$(urlencode "$TAPO_USER"):$(urlencode "$TAPO_PASS")@${TAPO_IP}/${quality}"

    local url_file
    url_file=$(mktemp) || exit 1
    chmod 600 "$url_file"
    echo "$rtsp_url" > "$url_file"

    local mpv_opts=(
        --profile=fast
        --untimed
        --cache=no
        --demuxer-readahead-secs=0
        --vd-lavc-threads=1
        --rtsp-transport=udp
        --demuxer-lavf-o-add=fflags=+nobuffer
        --demuxer-lavf-o-add=probesize=5000000
        --demuxer-lavf-o-add=analyzeduration=5000000
        --video-sync=audio
    )

    local error_log
    error_log=$(mktemp) || exit 1

    mpv --log-file="$error_log" "${mpv_opts[@]}" --playlist="$url_file"
    local exit_code=$?

    rm -f "$url_file"

    if [[ $exit_code -ne 0 && $exit_code -ne 130 && -s "$error_log" ]]; then
        if is_network_error "$error_log"; then
            echo
            echo "!!! Connection Error Detected !!!"
            show_network_error "$error_log"
            echo
        fi
    fi

    rm -f "$error_log"
    return $exit_code
}

list_cameras() {
    if [[ -f "$PYTHON_HELPER" ]]; then
        python3 "$PYTHON_HELPER" --list 2>/dev/null | grep -E "^TAPO_CAM_" | while read -r line; do
            echo "$line"
        done
        return 0
    fi
    # Fallback
    echo "Single camera (legacy .env)"
}

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Stream your TP-Link Tapo camera over RTSP using mpv.

Options:
  -h, --help          Show this help message
  -r, --reset         Reset saved configuration
  -i, --ip IP         Set camera IP address (overrides saved config)
  -c, --camera ID     Select camera by ID (default: 0)
  -q, --quality HD|SD Select stream quality (default: HD)
  -l, --list          List configured cameras
EOF
    exit 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local reset_config=0
    local camera_id=0
    local quality="hd"

    check_deps || exit 1

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)      usage ;;
            -r|--reset)     reset_config=1; shift ;;
            -i|--ip)        TAPO_IP="$2"; shift 2 ;;
            -c|--camera)    camera_id="$2"; shift 2 ;;
            -q|--quality)   quality="$2"; shift 2 ;;
            -l|--list)      list_cameras; exit 0 ;;
            *)              echo "Unknown option: $1"; usage ;;
        esac
    done

    if [[ $reset_config -eq 1 ]]; then
        rm -f "$ENV_FILE"
        if [[ -f "$PYTHON_HELPER" ]]; then
            python3 -c "
import json
from pathlib import Path
p = Path.home() / '.config' / 'tapitocam' / 'cameras.json'
if p.exists():
    p.unlink()
    print('Configuration reset.')
" 2>/dev/null || echo "Configuration reset."
        fi
    fi

    # If IP was provided as flag, use it directly
    if [[ -z "${TAPO_IP:-}" ]]; then
        load_config "$camera_id"
    fi

    if [[ -z "${TAPO_USER:-}" || -z "${TAPO_PASS:-}" || -z "${TAPO_IP:-}" ]]; then
        setup_config
    fi

    if [[ -z "${TAPO_USER:-}" || -z "${TAPO_PASS:-}" || -z "${TAPO_IP:-}" ]]; then
        echo "Error: Missing credentials."
        exit 1
    fi

    while true; do
        run_stream "$quality"
        local rc=$?

        # Ctrl+C → exit cleanly
        [[ $rc -eq 130 ]] && break
        # Success → exit
        [[ $rc -eq 0 ]] && break

        # Connection error → offer to change IP
        read -r -p "Would you like to enter a different IP? (y/n): " ans
        if [[ "$ans" =~ ^[Yy]$ ]]; then
            read -r -p "Enter new Camera IP: " TAPO_IP
            save_env_config
            echo "IP updated to $TAPO_IP. Retrying..."
            continue
        fi
        break
    done
}

main "$@"