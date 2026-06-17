#!/usr/bin/env python3
"""Shared utilities for tapitoCAM."""

import os
import re
import tempfile
from urllib.parse import quote as urlquote

# ---------------------------------------------------------------------------
# Connection error patterns (shared between GUI and CLI)
# ---------------------------------------------------------------------------
MPV_CONNECTION_ERROR_PATTERNS = (
    "failed to connect",
    "connection refused",
    "connection timed out",
    "error while opening",
    "cannot open",
    "no route to host",
    "host unreachable",
    "network is unreachable",
    "name or service not known",
    "resolve failed",
    "connection reset",
)


def is_mpv_connection_error(text: str) -> bool:
    """Return True if *text* from mpv stderr indicates a connection failure."""
    lower = text.lower()
    return any(pattern in lower for pattern in MPV_CONNECTION_ERROR_PATTERNS)


# ---------------------------------------------------------------------------
# Authorization error patterns
# ---------------------------------------------------------------------------
MPV_AUTH_ERROR_PATTERNS = (
    "401 unauthorized",
    "401",
    "authentication failed",
    "authenticate failed",
    "unauthorized",
    "invalid credentials",
    "access denied",
    "login failed",
    "wrong password",
)


def is_auth_error(text: str) -> bool:
    """Return True if *text* indicates an authorization/credential failure."""
    lower = text.lower()
    return any(pattern in lower for pattern in MPV_AUTH_ERROR_PATTERNS)


# ---------------------------------------------------------------------------
# URL encoding
# ---------------------------------------------------------------------------
def build_rtsp_url(
    username: str, password: str, ip: str, stream: str = "stream1"
) -> str:
    """Build an RTSP URL for a Tapo camera."""
    return f"rtsp://{urlquote(username, safe='')}:{urlquote(password, safe='')}@{ip}/{stream}"


# ---------------------------------------------------------------------------
# Default mpv options for low-latency streaming
# ---------------------------------------------------------------------------
MPV_OPTIONS = [
    "--profile=fast",
    "--untimed",
    "--cache=no",
    "--demuxer-readahead-secs=0",
    "--vd-lavc-threads=1",
    "--rtsp-transport=udp",
    "--demuxer-lavf-o-add=fflags=+nobuffer",
    "--demuxer-lavf-o-add=probesize=5000000",
    "--demuxer-lavf-o-add=analyzeduration=5000000",
    "--video-sync=audio",
]


def write_rtsp_playlist(rtsp_url: str) -> str:
    """Write an RTSP URL to a private temp file and return the path.

    The file is created with ``0o600`` permissions and contains only
    the URL.  Pass the returned path to `get_mpv_playlist_command`.
    The caller **must** call ``os.unlink(path)`` after mpv has started
    (or on error) to avoid leaving credentials on disk.
    """
    fd, path = tempfile.mkstemp(suffix=".m3u", prefix="tapitocam_")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(rtsp_url + "\n")
    except Exception:
        os.unlink(path)
        raise
    os.chmod(path, 0o600)
    return path


def get_mpv_playlist_command(title: str, playlist_path: str) -> list[str]:
    """Return the mpv command list using a playlist file (no credentials in argv)."""
    return [
        "mpv",
        f"--title=tapitoCAM — {title}",
        *MPV_OPTIONS,
        f"--playlist={playlist_path}",
    ]


# ---------------------------------------------------------------------------
# ONVIF error sanitizer
# ---------------------------------------------------------------------------

# Regex matching user:password@ embedded in URLs like
# ``http://admin:secret@192.168.1.100/onvif``
_URL_CREDENTIALS_RE = re.compile(r"://[^@:\s]+:[^@\s]+@")


def sanitize_onvif_error(msg: str) -> str:
    """Strip credential-like patterns from an ONVIF error message.

    Also shortens the message to a single line (max 150 chars) so it
    fits in the status bar without leaking sensitive data.
    """
    sanitized = _URL_CREDENTIALS_RE.sub("://***:***@", msg)
    # Replace any remaining password=XXX or passwd=XXX
    sanitized = re.sub(
        r"(?i)(password|passwd|pass)=[^\s&,;:]+",
        r"\1=***",
        sanitized,
    )
    # Remove newlines and truncate
    sanitized = sanitized.replace("\n", " ").replace("\r", "")
    if len(sanitized) > 150:
        sanitized = sanitized[:147] + "..."
    return sanitized
