#!/usr/bin/env python3
"""CLI helper for tapitocam.sh — loads camera config from JSON and prints shell-parseable output."""

import json
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "tapitocam"
CONFIG_FILE = CONFIG_DIR / "cameras.json"

OLD_ENV_FILE = CONFIG_DIR / ".tapitocam.env"


def load_json_config() -> list[dict]:
    """Load cameras from JSON config."""
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        return data.get("cameras", [])
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def load_env_config() -> dict | None:
    """Load single camera from legacy .env config."""
    if not OLD_ENV_FILE.exists():
        return None
    import base64

    entry = {}
    with open(OLD_ENV_FILE) as f:
        for line in f:
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            val = value.strip()
            if key == "TAPO_USER":
                entry["username"] = val
            elif key == "TAPO_PASS":
                try:
                    entry["password"] = base64.b64decode(val).decode()
                except Exception:
                    entry["password"] = val
            elif key == "TAPO_IP":
                entry["ip"] = val
    if entry.get("username") and entry["password"] and entry.get("ip"):
        return entry
    return None


def print_camera_shell(camera: dict) -> None:
    """Print camera as shell variable assignments."""
    print(f"TAPO_USER='{camera['username']}'")
    # Password needs to be escaped for shell
    password = camera["password"].replace("'", "'\\''")
    print(f"TAPO_PASS='{password}'")
    print(f"TAPO_IP='{camera['ip']}'")
    print(f"TAPO_QUALITY='{camera.get('quality', 'hd')}'")


def print_camera_list() -> None:
    """Print all cameras for shell consumption."""
    cameras = load_json_config()
    if not cameras:
        # Try legacy
        env = load_env_config()
        if env:
            print_camera_shell(env)
        return

    # Print count
    print(f"TAPO_CAM_COUNT={len(cameras)}")
    for i, cam in enumerate(cameras):
        print(f"TAPO_CAM_{i}_ID={cam['id']}")
        print(f"TAPO_CAM_{i}_NAME='{cam['name']}'")
        print(f"TAPO_CAM_{i}_USER='{cam['username']}'")
        password = cam["password"].replace("'", "'\\''")
        print(f"TAPO_CAM_{i}_PASS='{password}'")
        print(f"TAPO_CAM_{i}_IP='{cam['ip']}'")
        print(f"TAPO_CAM_{i}_QUALITY='{cam.get('quality', 'hd')}'")


def print_single_camera(camera_id: int | None = None) -> bool:
    """Print a single camera (by id or first). Returns True if found."""
    cameras = load_json_config()
    if not cameras:
        env = load_env_config()
        if env:
            print_camera_shell(env)
            return True
        return False

    if camera_id is not None:
        cam = next((c for c in cameras if c["id"] == camera_id), None)
        if not cam:
            return False
    else:
        cam = cameras[0]

    print_camera_shell(cam)
    return True


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        print_camera_list()
    elif len(sys.argv) > 1 and sys.argv[1] == "--camera":
        cam_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
        if not print_single_camera(cam_id):
            sys.exit(1)
    else:
        # Default: print first camera for backward compatibility
        if not print_single_camera():
            sys.exit(1)


if __name__ == "__main__":
    main()
