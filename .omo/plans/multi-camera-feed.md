# Plan: Multi-Camera Feed (2×2 Grid)

**User**: dressedinblack  
**Date**: 2026-06-14  
**Type**: Feature — new architecture, extends existing GUI  
**Scope**: GUI only, 4 cameras, 2×2 grid, per-tile PTZ, per-tile quality

---

## 1. Goal

Add a 2×2 multi-camera grid to the tapitoCAM GUI, replacing the current single-camera form with a grid of 4 independent camera tiles, each with its own stream, PTZ controls, and quality selector.

---

## 2. Requirements (locked)

| Item | Decision |
|---|---|
| Camera count | 4 (2×2 grid, extensible format) |
| PTZ | Per tile (pan/tilt, individual PTZWorker) |
| Quality | Per tile (HD stream1 / SD stream2 combo) |
| Config format | JSON (`cameras.json`) |
| Camera management | Dedicated dialog (add/edit/remove) |
| Backward compat | Migrate old `.tapitocam.env` → JSON on first launch |
| Auto-connect | Manual per-tile (no auto-stream) |
| Tests | After implementation |
| CLI | Unchanged (stays single-camera) |

---

## 3. Architecture Overview

```
tapitocam_gui.py        # Main entry — slim, delegates to modules
├── cameraconfig.py     # ConfigManager — JSON I/O, .env migration, CRUD
├── cameradialog.py     # CameraManagerDialog — list/add/edit/remove cameras
├── cameratile.py       # CameraTileWidget — one tile: mpv + PTZ + quality + status
│   └── PTZWorker       # Per-tile PTZ (extracted reusable worker)
└── MainWindow          # Redesigned: top toolbar + 2×2 grid of tiles
```

### Config file: `~/.config/tapitocam/cameras.json`

```json
{
  "version": 1,
  "cameras": [
    {
      "id": 0,
      "name": "Front Door",
      "username": "...",
      "password": "...",
      "ip": "192.168.1.100",
      "quality": "hd"
    }
  ]
}
```

### Data flow

```
ConfigManager (read/write JSON)
  → CameraManagerDialog (manage cameras)
  → MainWindow (holds 2×2 grid of CameraTileWidget)
      → CameraTileWidget.load_camera(config_entry)
      → CameraTileWidget has own: mpv.MPV, PTZWorker, quality combo
```

---

## 4. Work Breakdown

### Phase 1 — Config Foundation (1 subagent)

**Deliverable**: `tapitocam/cameraconfig.py`

**File**: new `tapitocam/` package (or keep flat — the team can name the file `cameraconfig.py` in project root).

**Class `ConfigManager`**:
- `__init__(config_dir: Path = ~/.config/tapitocam)`
- `load() -> list[dict]` — read/write JSON
- `save(cameras: list[dict])` — atomic write (write to temp, rename)
- `add_camera(entry: dict) -> int` — return new id
- `update_camera(camera_id: int, entry: dict)`
- `remove_camera(camera_id: int)`
- `migrate_from_env()` — detect old `.tapitocam.env`, read it, convert to JSON entry, remove old file
- `get_defaults_path() -> Path`
- Password stored as base64 (same as current scheme)

**Validation** (same as current `_validate_ip`):
- IP: 4 octets 0-255
- Required fields: username, password, ip
- Name defaults to "Camera {id}" if empty
- Quality defaults to "hd"

**Must do**:
- Create `cameraconfig.py` in project root
- Implement all methods above
- Handle file-not-found gracefully (return empty list)
- Password base64 encoding/decoding (match existing scheme)

**Must not do**:
- Do NOT import PySide6/Qt — pure Python only
- Do NOT modify tapitocam_gui.py
- Do NOT write tests yet (Phase 6)

---

### Phase 2 — Camera Tile Widget (1 subagent)

**Deliverable**: `tapitocam/cameratile.py`

**Class `CameraTileWidget(QWidget)`**:

Layout (top to bottom):
```
┌──────────────────┐
│  Stream (mpv)     │  ← QWidget acting as mpv embedding container
│                   │
│ [▶ Start] [HD▼]   │  ← stream controls
│ ▲ ▼ ◀ ▶ [Stop ▲ ]│  ← PTZ + stop button
│ ● Status label    │
└──────────────────┘
```

**Methods/API**:
- `load_camera(config: dict)` — sets credentials, IP, name
- `start_stream()` — creates mpv player, plays RTSP URL
- `stop_stream()` — stops mpv, cleans up
- `set_quality(index: int)` — 0=HD(stream1), 1=SD(stream2)
- `pressed_* / released_*` for PTZ buttons (same pattern as current)
- `get_camera_id() -> int`
- `is_streaming() -> bool`

**PTZ**: 
- One `PTZWorker` + `QThread` per tile (reuse existing PTZWorker class — extract it from MainWindow into cameratile.py or keep in cameratile.py)
- The current `PTZWorker` class should be extracted from `MainWindow` into `cameratile.py` so each tile gets its own instance

**Must do**:
- Create `cameratile.py` in project root
- Extract PTZWorker into cameratile.py (importable)
- Each tile creates its own PTZWorker + QThread on `start_stream()`
- Connect PTZ buttons via pressed/released (same pattern as current code)
- Stream controls: start button, stop button, quality combo
- Status label: "● Checking...", "● Online", "● Offline", "● Streaming"
- Close/X button to remove tile from grid
- Dark theme styling (match existing stylesheet)
- Python-MPV embed: use `wid` parameter for embedding in the tile widget

**Must not do**:
- Do NOT modify tapitocam_gui.py yet
- Do NOT modify cameraconfig.py
- Do NOT write tests yet

---

### Phase 3 — Camera Manager Dialog (1 subagent, parallel with Phase 2)

**Deliverable**: `tapitocam/cameradialog.py`

**Class `CameraManagerDialog(QDialog)`**:

Layout:
```
┌──────────────────────────────────┐
│ Camera Manager           [X]     │
├──────────────────────────────────┤
│ ┌──────────────────────────────┐ │
│ │ Camera 1  | 192.168.1.100  │ │  ← QListWidget
│ │ Camera 2  | 192.168.1.101  │ │
│ │ ...                        │ │
│ └──────────────────────────────┘ │
│ [+ Add] [✏ Edit] [✕ Remove]     │
├──────────────────────────────────┤
│           [OK] [Cancel]          │
└──────────────────────────────────┘
```

- Uses `ConfigManager` to read/write
- Add: opens inline form or sub-dialog with: Name, Username, Password, IP, Quality (HD/SD)
- Edit: same form pre-filled with existing values
- Remove: confirmation dialog ("Remove Camera X?")
- Returns the updated list of cameras when OK is clicked
- Validates IP before saving
- Minimum dial width ~400px

**Must do**:
- Create `cameradialog.py` in project root
- Import ConfigManager from cameraconfig
- Implement add/edit/remove with validation
- Dark theme styling (match existing stylesheet pattern)
- Clean separation: dialog returns camera list, caller saves

**Must not do**:
- Do NOT modify tapitocam_gui.py yet
- Do NOT write tests yet

---

### Phase 4 — Main Window Redesign (1 subagent)

**Deliverable**: Modify `tapitocam_gui.py`

**Changes to MainWindow**:

1. **Remove**: old credential form (username_edit, password_edit, ip_edit, save_btn, reset_btn)
2. **Remove**: old status_label
3. **Remove**: old quality_combo from stream row
4. **Remove**: old ptz_widget
5. **Add**: Top toolbar/row with:
   - "Manage Cameras" button → opens CameraManagerDialog
   - "Start All" / "Stop All" button
   - App title "tapitoCAM — Multi-View"
6. **Add**: 2×2 QGridLayout in center container
   - 4 CameraTileWidget instances (tile_0..tile_3)
   - Each tile loaded from corresponding camera config entry
   - Empty/placeholder state when <4 cameras configured
7. **Add**: On Tile close → optionally just stop stream, not remove config (or "remove from grid" concept)
8. **Window resize**: Minimum 800×600 (adjust to fit 2×2 grid of decent tiles)
9. **On init**: Call ConfigManager.load(), populate tiles
10. **Migration**: On first launch, if no cameras.json but old .env exists, migrate automatically

**Signals/connections**:
- `self.camera_manager_btn.clicked` → open dialog → reload tiles
- `self.start_all_btn.clicked` → start all configured tiles
- `self.stop_all_btn.clicked` → stop all tiles
- `tile_n.close_requested` → stop stream, hide tile

**Must do**:
- Modify EXISTING tapitocam_gui.py
- Import from cameraconfig, cameradialog, cameratitle
- Keep the same app.setStyle(app.setStyle("Fusion")) and dark stylesheet
- Keep closeEvent cleanup (cleanup all tiles' PTZ and players)
- Keep network error handling (per tile now)

**Must not do**:
- Do NOT change the CLI (tapitocam.sh)
- Do NOT remove existing functionality that isn't being replaced
- Do NOT write tests yet

---

### Phase 5 — Integration & Polish (manual validation)

1. **Migration test**: Start with old .env, verify auto-migration to JSON
2. **Edge cases**: 
   - 0 cameras configured → tiles show "No camera" placeholder
   - 1-3 cameras → fill grid left-to-right, empty tiles show placeholder
   - 4+ → first 4 only (or scroll — but 4 is the limit for now)
3. **PTZ per tile**: Verify each tile has independent PTZ
4. **Stream restart**: Stop + restart individual tiles
5. **Error handling**: Tile shows error, doesn't crash other tiles
6. **Cleanup**: Closing app stops all streams and PTZ workers cleanly

---

### Phase 6 — Tests (1 subagent)

**Deliverable**: `tests/test_cameraconfig.py`

**Framework**: unittest (no extra deps)

**Tests**:
1. `test_config_create_default` — fresh config dir returns empty list
2. `test_config_add_camera` — add returns id, persists to JSON
3. `test_config_update_camera` — update fields preserves other cameras
4. `test_config_remove_camera` — remove by id
5. `test_config_ip_validation` — invalid IPs rejected
6. `test_config_migrate_from_env` — old .env → JSON migration
7. `test_config_empty_name_defaults` — blank name sets "Camera N"
8. `test_config_password_base64` — password round-trips through base64

**Can add in same file**:
- `test_cameradialog_validation` — tests dialog validation logic (if extractable)

**Must do**:
- Create `tests/` directory with `__init__.py`
- Use `tempfile.TemporaryDirectory` for config files
- All tests pass with `python3 -m unittest discover tests/`

**Must not do**:
- Do NOT test GUI widgets (no Qt event loop tests)
- Do NOT add external dependencies

---

## 5. Parallel Execution Plan

```
Phase 1 ─────────────────────────────────────────────────
  cameraconfig.py (standalone, pure Python)

Phase 2 ─────────────┐   Phase 3 ────────────┐
  cameratile.py      │     cameradialog.py    │  ← PARALLEL
  (PTZWorker, mpv    │     (ConfigManager     │
   + embedding)      │      + UI dialog)      │
                     └───────────────────────┘

Phase 4 ────────────────────────────────────────
  tapitocam_gui.py rewrite (depends on 1,2,3)

Phase 5 ──── Integration polish (manual)

Phase 6 ──── Tests (depends on Phase 1 module)
```

**Creation order**: Phase 1 → Phase 2 + Phase 3 (parallel) → Phase 4 → Phase 5 → Phase 6

**Delegation strategy**:
- Phase 1: 1× `deep` agent
- Phase 2: 1× `unspecified-high` or `deep` agent (it has visual + PTZ + mpv concerns)
- Phase 3: 1× `visual-engineering` agent (pure UI dialog)
- Phase 4: 1× `deep` agent (complex integration)
- Phase 6: 1× `quick` agent (well-defined tests, pure Python)

---

## 6. Acceptance Criteria

- [ ] 2×2 grid of 4 camera tiles visible in main window
- [ ] Each tile can independently play/hide its RTSP stream
- [ ] Each tile has working PTZ (pan/tilt/stop)
- [ ] Each tile has HD/SD quality selector — switching restarts stream
- [ ] "Manage Cameras" button opens dialog to add/edit/remove cameras
- [ ] Config persisted to ~/.config/tapitocam/cameras.json
- [ ] Old .tapitocam.env auto-migrated on first launch
- [ ] "Start All" / "Stop All" controls all tiles
- [ ] Closing one tile's stream does not affect others
- [ ] App close cleanly terminates all streams and PTZ connections
- [ ] All unittest tests pass
- [ ] No regressions in existing error handling patterns

---

## 7. Critical Implementation Details

### mpv Embedding (new pattern)

Current code does NOT embed mpv in the Qt window — it launches mpv as a standalone window. For grid tiles, we need **embedded video** inside each CameraTileWidget.

**Pattern** (python-mpv + PySide6):
```python
# In CameraTileWidget:
self.video_container = QWidget(self)
self.video_container.setAttribute(Qt.WA_NativeWindow)  # ensure native window handle

# Create mpv instance bound to this container
import mpv
self.player = mpv.MPV(
    wid=str(int(self.video_container.winId())),  # embed here
    profile="fast",
    untimed=True,
    # ... rest of options same as current
)
```

Container must be a direct child of the tile with `WA_NativeWindow` set to ensure it gets a native window ID. Mpv renders directly into this container.

### Per-Tile Error Handling

Current `_handle_network_error` shows a global dialog asking to change IP. For tiles:
- Each tile handles its own stream errors independently
- Tile shows a status label error message
- Tile does NOT pop up a modal (other tiles should keep running)
- Optionally: show a small retry button on the tile

### PTZWorker Cleanup Per Tile

Each CameraTileWidget owns its own PTZWorker + QThread. On tile stop or widget destruction:
1. Stop continuous move (PTZ stop)
2. Quit thread, wait up to 3s
3. Delete worker and thread
4. Terminate mpv player
5. Delete mpv player

### Container Widget for Video

Each CameraTileWidget needs a dedicated `QWidget` that serves as the mpv rendering surface:
- Created once in `__init__`
- Used as the video area placeholder
- When no stream is active, shows a placeholder label ("Camera N — Not Streaming")
- On stream start, mpv renders into this widget's native window

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Multiple mpv instances consume too much RAM/CPU | Test with 4 cameras first; document minimum specs |
| python-mpv embedding in QGridLayout widget order issues | Test tile embedding early; use existing `wid` pattern |
| PTZ conflicts (same ONVIF port per camera) | Each PTZWorker connects to its own camera IP:2020 — no conflict |
| Config migration corrupts existing .env | Migration is read-only on old file; atomic write to new |
| matplotlib on vfbs/framebuffer (ci testing) | Tests avoid GUI; manual QA for visual parts |
