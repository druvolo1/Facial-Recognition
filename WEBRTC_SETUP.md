# WebRTC Server-Side Frame Capture Setup

## Overview
This solution bypasses Tizen VIDEO_HOLE limitation by sending the camera stream via WebRTC to the server, where frames are captured and processed server-side.

## Architecture
```
Tizen Display (USB Camera)
  ↓ getUserMedia() ✅
  ↓ WebRTC Stream via RTCPeerConnection
  ↓
Python Server (172.16.1.150:8080)
  ↓ Receives WebRTC stream (aiortc)
  ↓ Captures frames every 2 seconds
  ↓ Converts to base64 JPEG
  ↓ Calls existing /api/displays/recognize
  ↓
Flask/FastAPI (port 5000)
  ↓ Facial Recognition via CodeProject.AI
  ↓ Returns results
  ↓
Server logs results (can be sent back to Tizen if needed)
```

## Installation

### 1. Install Python Dependencies

On your server (172.16.1.150):

```bash
cd "C:\Users\Dave\Documents\Programming\Facial Recognition"

# Install WebRTC dependencies
pip install -r webrtc_requirements.txt
```

**Dependencies installed:**
- `aiortc>=1.6.0` - WebRTC implementation
- `aiohttp>=3.9.0` - Async HTTP server
- `av>=10.0.0` - Video frame processing
- `numpy>=1.24.0` - Array operations
- `Pillow>=10.0.0` - Image processing
- `requests>=2.31.0` - HTTP requests to Flask API

### 2. Start the Servers

**Terminal 1 - WebRTC Receiver (Port 8080):**
```bash
cd "C:\Users\Dave\Documents\Programming\Facial Recognition"
python webrtc_receiver.py
```

You should see:
```
INFO:aiohttp.access:...
======== Running on http://0.0.0.0:8080 ========
```

**Terminal 2 - Facial Recognition API (Port 5000):**
```bash
cd "C:\Users\Dave\Documents\Programming\Facial Recognition"

# If using FastAPI version:
python -m uvicorn app.main:app --host 0.0.0.0 --port 5000

# OR if using Flask version:
python app.py
```

### 3. Deploy Tizen App

1. Redeploy the updated Tizen app to your display
2. The app will automatically:
   - Request camera access
   - Create WebRTC peer connection to `http://172.16.1.150:8080`
   - Send offer and receive answer
   - Stream video to server

## Testing

### Check Tizen Console

You should see:
```
[WebRTC] Creating peer connection to: http://172.16.1.150:8080/webrtc/offer
[WebRTC] Peer connection created
[WebRTC] Added track: video
[WebRTC] Offer created, setting local description
[WebRTC] Received answer from server
[WebRTC] Connection state: connected
[WebRTC] Successfully connected to server!
```

### Check Server Logs

You should see:
```
[WebRTC] Received offer from client
[WebRTC] Track received: video
[WebRTC] Video track received, starting frame capture
[VideoCapture] Starting frame capture loop
[VideoCapture] Captured frame: 45231 chars
[Recognition] Success: True, Faces: 1
[Recognition] Detected: john_doe (0.95)
```

## Configuration

### Change Frame Capture Rate

In `webrtc_receiver.py`, line 21:
```python
FRAME_CAPTURE_INTERVAL = 2.0  # Capture every 2 seconds
```

### Change Display ID

In `webrtc_receiver.py`, line 18:
```python
DISPLAY_ID = "lobby_display_01"
LOCATION = "Front Lobby"
```

Or in `js/main.js`, line 228-229:
```javascript
var DISPLAY_ID = 'lobby_display_01';
var LOCATION = 'Front Lobby';
```

### Change Server URL

In `js/main.js`, line 226:
```javascript
var WEBRTC_SERVER_URL = 'http://172.16.1.150:8080/webrtc/offer';
```

## Troubleshooting

### "Connection refused" on Tizen

**Problem:** Server not reachable
**Solution:**
- Verify server is running: `python webrtc_receiver.py`
- Check firewall allows port 8080
- Verify IP address is correct (172.16.1.150)

### "No track received"

**Problem:** Camera stream not being sent
**Solution:**
- Check Tizen console for camera errors
- Verify camera permissions in config.xml
- Check `getUserMedia()` succeeded

### "No faces detected"

**Problem:** Recognition API not working
**Solution:**
- Check Flask server is running on port 5000
- Verify CodeProject.AI is running
- Check server logs for HTTP errors

### Port 8080 already in use

**Solution:**
```python
# In webrtc_receiver.py, last line:
web.run_app(app, host="0.0.0.0", port=8081)  # Change port
```

And update client:
```javascript
// In js/main.js:
var WEBRTC_SERVER_URL = 'http://172.16.1.150:8081/webrtc/offer';
```

## Next Steps (If Proof of Concept Works)

If this successfully captures frames and performs facial recognition:

1. **Optimize frame rate** - Adjust FRAME_CAPTURE_INTERVAL
2. **Add result feedback** - Send recognition results back to Tizen display
3. **Consider native development** - For production, develop native C++ extension to eliminate server dependency
4. **Load balancing** - If multiple displays, distribute across servers

## Files Modified

- **NEW:** `webrtc_receiver.py` - WebRTC server with frame capture
- **NEW:** `webrtc_requirements.txt` - Python dependencies
- **NEW:** `WEBRTC_SETUP.md` - This file
- **MODIFIED:** `js/main.js` - WebRTC client implementation
- **UNCHANGED:** All server-side recognition code (reused as-is)

## Benefits of This Approach

✅ **No VIDEO_HOLE issues** - Server-side capture bypasses Tizen limitation
✅ **Reuses existing code** - Flask API unchanged
✅ **Proof of concept** - Validates approach before native development
✅ **Quick implementation** - 2-3 hours vs weeks for native code
✅ **Easy debugging** - Python logs show everything

## Limitations

⚠️ **Network dependency** - Requires server connection
⚠️ **Latency** - Small delay due to WebRTC transmission
⚠️ **Server load** - Each display requires server processing

These limitations can be addressed with native development later if needed.
