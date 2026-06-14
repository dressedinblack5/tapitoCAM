# Multi-Camera: Manual QA Scenarios

## Prerequisites
- At least one Tapo camera on the network configured with a Camera Account
- For full 4-camera test: 4 cameras (can test with 1-3 as well)

## Scenario 1: First Launch After Upgrade
1. Ensure old `~/.config/tapitocam/.tapitocam.env` exists with valid credentials
2. Launch `./tapitocam_gui.py`
3. **Expected**: Tile 1 shows your camera with "● Ready" status
4. **Expected**: Old .env is deleted, `cameras.json` created
5. **Expected**: Other tiles show "No stream" placeholder

## Scenario 2: Camera Management Dialog
1. Click "Manage Cameras"
2. **Expected**: Dialog opens with existing camera(s) listed
3. Click "+ Add" — fill in name/username/password/IP, choose HD/SD, click OK
4. **Expected**: New camera appears in list
5. Click "✏ Edit" on a camera — change name, click OK
6. **Expected**: Name updated in list
7. Click "✕ Remove" — confirm — camera disappears
8. Click OK to close dialog
9. **Expected**: Grid tiles refresh with updated camera list

## Scenario 3: Single Camera Stream
1. Configure one camera
2. Click "▶ Start" on that tile
3. **Expected**: Status shows "Starting stream..." then "● Streaming" (green)
4. **Expected**: Video appears in the tile's container
5. Tile PTZ buttons become enabled (if ONVIF connects)
6. Click "■ Stop" — stream stops, status shows "● Stopped"

## Scenario 4: Multiple Camera Streams
1. Configure 2-4 cameras
2. Click "▶ Start" on each tile, or use "▶ Start All"
3. **Expected**: All configured tiles play their streams simultaneously
4. **Expected**: Each tile shows independent video
5. **Expected**: Each tile has its own PTZ working independently
6. Click "■ Stop All" — all streams stop

## Scenario 5: Per-Tile Quality Switching
1. Start a stream on one tile
2. While streaming is playing, change the HD/SD quality combo
3. **Expected**: Stream restarts with new quality

## Scenario 6: Tile Close
1. Start a stream
2. Click the "×" button on the tile's title bar
3. **Expected**: Stream stops, but other tiles (if any) remain unaffected

## Scenario 7: Error Handling
1. Configure a camera with an unreachable IP
2. Try to start the stream
3. **Expected**: Tile shows status error but doesn't pop up a modal dialog
4. **Expected**: Other tiles continue streaming normally

## Scenario 8: Window Close
1. Start 1+ streams
2. Close the window
3. **Expected**: All streams stop, all PTZ connections cleaned up, no lingering mpv processes

## Scenario 9: Partial Configuration (1-3 cameras)
1. Configure only 2 cameras
2. **Expected**: 2 tiles show camera info, 2 tiles show "No stream" placeholders
3. Streams work on the configured tiles only
