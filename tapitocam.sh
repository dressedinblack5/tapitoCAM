#!/bin/bash
# tapitocam.sh - TP-Link Tapo Camera RTSP Client

set -o pipefail

VERSION="1.1.0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${HOME}/.config/tapitocam"
CONFIG_FILE="${CONFIG_DIR}/.tapitocam.env"

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
check_deps() {
    local missing=0 cmd
    for cmd in mpv mktemp; do
        if ! command -v "$cmd" &>/dev/null; then
            echo "Error: '$cmd' is not installed."
            missing=1
        fi
    done
    [[ $missing -eq 0 ]]
}

# ---------------------------------------------------------------------------
# Config I/O
# ---------------------------------------------------------------------------
load_config() {
    [[ -f "$CONFIG_FILE" ]] || return 1
    local line
    while IFS= read -r line; do
        [[ "$line" =~ ^#         ]] && continue
        [[ -z "$line"            ]] && continue
        [[ "$line" =~ ^TAPO_USER=(.*)$ ]] && TAPO_USER="${BASH_REMATCH[1]}"
        [[ "$line" =~ ^TAPO_PASS=(.*)$ ]] && TAPO_PASS=$(printf '%s' "${BASH_REMATCH[1]}" | base64 -d 2>/dev/null || printf '%s' "${BASH_REMATCH[1]}")
        [[ "$line" =~ ^TAPO_IP=(.*)$   ]] && TAPO_IP="${BASH_REMATCH[1]}"
    done < "$CONFIG_FILE"
}

save_config() {
    mkdir -p "$CONFIG_DIR"
    {
        echo "# tapitoCAM configuration"
        echo "TAPO_USER=$TAPO_USER"
        echo "TAPO_PASS=$(printf '%s' "$TAPO_PASS" | base64 -w0)"
        echo "TAPO_IP=$TAPO_IP"
    } > "$CONFIG_FILE"
    chmod 600 "$CONFIG_FILE"
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
# Interactive setup
# ---------------------------------------------------------------------------
setup_config() {
    echo "--- tapitoCAM Configuration ---"
    read -r -p "Enter Tapo Username: " TAPO_USER
    read -r -s -p "Enter Tapo Password: " TAPO_PASS
    echo
    read -r -p "Enter Camera IP (e.g., 192.168.1.100): " TAPO_IP
    if ! validate_ip "$TAPO_IP"; then
        echo "Warning: The entered IP address appears invalid."
    fi

    read -r -p "Save these settings to .tapitocam.env? (y/n): " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        save_config
        echo "Settings saved."
    fi
}

# ---------------------------------------------------------------------------
# Stream
# ---------------------------------------------------------------------------
is_network_error() {
    local log="$1"
    grep -Eiq "No route to host|Connection timed out|Connection refused|Failed to resolve hostname" "$log"
}

show_network_error() {
    local log="$1"
    grep -Ei "No route to host|Connection timed out|Connection refused|Failed to resolve hostname" "$log" | head -1
}

run_stream() {
    local rtsp_url
    rtsp_url="rtsp://$(urlencode "$TAPO_USER"):$(urlencode "$TAPO_PASS")@${TAPO_IP}/stream1"

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

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Stream your TP-Link Tapo camera over RTSP using mpv.

Options:
  -h, --help       Show this help message
  -r, --reset      Reset saved configuration
  -i, --ip IP      Set camera IP address (overrides saved config)
EOF
    exit 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local reset_config=0

    check_deps || exit 1

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)  usage ;;
            -r|--reset) reset_config=1; shift ;;
            -i|--ip)    TAPO_IP="$2"; shift 2 ;;
            *)          echo "Unknown option: $1"; usage ;;
        esac
    done

    if [[ $reset_config -eq 1 ]]; then
        rm -f "$CONFIG_FILE"
        echo "Configuration reset."
    fi

    load_config

    if [[ -z "$TAPO_USER" || -z "$TAPO_PASS" || -z "$TAPO_IP" ]]; then
        setup_config
    fi

    if [[ -z "$TAPO_USER" || -z "$TAPO_PASS" || -z "$TAPO_IP" ]]; then
        echo "Error: Missing credentials."
        exit 1
    fi

    while true; do
        run_stream
        local rc=$?

        # Ctrl+C → exit cleanly
        [[ $rc -eq 130 ]] && break
        # Success → exit
        [[ $rc -eq 0 ]] && break

        # Connection error → offer to change IP
        read -r -p "Would you like to enter a different IP? (y/n): " ans
        if [[ "$ans" =~ ^[Yy]$ ]]; then
            read -r -p "Enter new Camera IP: " TAPO_IP
            save_config
            echo "IP updated to $TAPO_IP. Retrying..."
            continue
        fi
        break
    done
}

main "$@"
