#!/usr/bin/env python3
"""CLI helper for tapitocam.sh — loads camera config and prints shell-parseable output."""

import sys

from cameraconfig import CONFIG_DIR_DEFAULT as CONFIG_DIR


def load_json_config() -> list[dict]:
    """Load cameras via ConfigManager (keyring-aware)."""
    from cameraconfig import ConfigManager

    return ConfigManager(CONFIG_DIR).load()


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
