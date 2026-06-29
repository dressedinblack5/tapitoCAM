# tapitoCAM Knowledge Base

**Generated:** 2026-06-28
**Commit:** `cf85c88` on `main`
**License:** Apache-2.0

## Overview

TP-Link Tapo Camera RTSP Client for Linux — multi-camera control center.
PySide6 GUI launches standalone mpv windows per camera. ONVIF PTZ, pytapo
night mode/LED. Credentials stored in OS keyring.

## Structure

```
./                   # Flat layout, no src/ dir
├── tapitocam_gui.py     # Main GUI (1112 LOC)
├── tapitocam_cli.py     # CLI helper for shell scripts (75 LOC)
├── cameraconfig.py      # Keyring-aware config manager (248 LOC)
├── cameradialog.py      # Add/edit/remove camera dialogs (424 LOC)
├── cameratile.py        # ONVIF PTZ controller (219 LOC)
├── styles.py            # Tokyo Night Storm Qt stylesheet (153 LOC)
├── utils.py             # Shared: RTSP URLs, mpv commands, error sanitizers (137 LOC)
├── tests/               # unittest suite
├── docs/superpowers/    # Design docs (not part of runtime)
├── dist/                # Packaging (debian, PKGBUILD)
└── assets/              # Screenshots
```

## Where to Look

| Task | File | Entry Point |
|------|------|-------------|
| Add UI widget | `tapitocam_gui.py` | `MainWindow` class |
| Change camera config format | `cameraconfig.py` | `ConfigManager` class |
| Modify PTZ behavior | `cameratile.py` | `PTZController` class |
| Tweak theme | `styles.py` | `DARK_THEME` constant |
| Add shared utility | `utils.py` | — |
| Change camera dialog | `cameradialog.py` | `CameraManagerDialog` |
| Run tests | `tests/` | `python -m unittest discover` |

## Conventions

- **Flat layout** — no `src/` package; modules imported by bare name (`from cameraconfig import ConfigManager`)
- **Imports** — stdlib first, then Qt, then local; `# noqa: E402` after `os.environ`/`locale` setup at module top
- **Types** — Python 3.10+ syntax (`str \| None`), light typing (no type checker configured)
- **Threading** — `threading.Thread(target=..., daemon=True).start()` for camera I/O; `QTimer.singleShot(0, lambda)` to ship results back to main thread
- **Error handling** — `contextlib.suppress(OSError)` for best-effort cleanup; status bar messages for user-facing errors
- **Naming** — `_` prefixed private methods; `snake_case` for functions/variables; `CapsWord` for classes
- **Tests** — `unittest` (no pytest); files mirror module names (`test_cameraconfig.py` → `cameraconfig.py`)
- **Config** — Ruff with `py310` target, `line-length=88`, rules `E,F,I,N,UP,B,SIM,ARG`; naming warnings suppressed

## Anti-Patterns

- No `src/` package — modules are flat in repo root; beware circular imports
- No shebangs on non-entry modules (cameraconfig.py, cameratile.py, etc. have them but aren't meant to be executed directly)
- Auth fallback chain in night mode/LED (tries 3 credential combos) is deliberate — Tapo firmware inconsistencies
- `LC_NUMERIC=C` is set at module top before any other import — must stay first

## Commands

```bash
ruff check .                    # Lint
python -m unittest discover -v  # Run tests
python tapitocam_gui.py         # Run GUI
./tapitocam.sh                  # Run CLI
```

## Notes

- ONVIF uses HTTP (no TLS) — credentials sent in cleartext on LAN
- CLI writes RTSP URL to a temp file briefly — cleaned up after mpv starts
- No `pyproject.toml` build system configured — ad-hoc `install.sh` only
- `pytapo` auth is fragile — newer firmwares need `admin` + cloud account password
