#!/usr/bin/env python3
"""Shared utilities for tapitoCAM."""

import urllib.parse


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
# IP validation
# ---------------------------------------------------------------------------
def validate_ip(ip: str) -> bool:
    """Return True if *ip* is a valid IPv4 address."""
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit() or not 0 <= int(p) <= 255:
            return False
    return True


# ---------------------------------------------------------------------------
# URL encoding
# ---------------------------------------------------------------------------
def urlencode_component(value: str) -> str:
    """URL-encode a single component (username or password)."""
    return urllib.parse.quote(value, safe="")


def build_rtsp_url(
    username: str, password: str, ip: str, stream: str = "stream1"
) -> str:
    """Build an RTSP URL for a Tapo camera."""
    encoded_user = urlencode_component(username)
    encoded_pass = urlencode_component(password)
    return f"rtsp://{encoded_user}:{encoded_pass}@{ip}/{stream}"


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


def get_mpv_command(title: str, rtsp_url: str) -> list[str]:
    """Return the mpv command list for a camera stream."""
    return [
        "mpv",
        f"--title=tapitoCAM — {title}",
        *MPV_OPTIONS,
        rtsp_url,
    ]
