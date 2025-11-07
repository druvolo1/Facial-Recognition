"""
WebRTC Receiver for Tizen Camera Stream
Captures frames from WebRTC stream and sends to facial recognition API
"""
import asyncio
import base64
import json
import logging
from io import BytesIO

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaRecorder, MediaPlayer
from av import VideoFrame
import numpy as np
from PIL import Image
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store active peer connections and WebSocket clients
pcs = set()
ws_clients = set()

# Configuration
FACIAL_RECOGNITION_URL = "http://localhost:5000/api/displays/recognize"
DISPLAY_ID = "lobby_display_01"
LOCATION = "Front Lobby"
FRAME_CAPTURE_INTERVAL = 2.0  # Capture every 2 seconds


class VideoFrameCapture:
    """Captures frames from WebRTC video track"""

    def __init__(self, track, display_id, location):
        self.track = track
        self.display_id = display_id
        self.location = location
        self.running = False
        self.last_capture_time = 0

    async def start(self):
        """Start capturing frames from the video track"""
        self.running = True
        logger.info("=" * 50)
        logger.info("[VideoCapture] Starting frame capture loop")
        logger.info(f"[VideoCapture] Display ID: {self.display_id}")
        logger.info(f"[VideoCapture] Location: {self.location}")
        logger.info(f"[VideoCapture] Capture interval: {FRAME_CAPTURE_INTERVAL}s")
        logger.info("=" * 50)

        frame_number = 0
        try:
            while self.running:
                try:
                    # Receive frame from track
                    logger.info(f"[VideoCapture] Attempting to receive frame {frame_number}...")
                    frame = await self.track.recv()
                    frame_number += 1
                    logger.info(f"[VideoCapture] Frame {frame_number} received successfully!")

                    # Check if enough time has passed since last capture
                    current_time = asyncio.get_event_loop().time()
                    if current_time - self.last_capture_time >= FRAME_CAPTURE_INTERVAL:
                        self.last_capture_time = current_time
                        logger.info(f"[VideoCapture] Processing frame {frame_number}...")

                        # Process frame in background
                        asyncio.create_task(self.process_frame(frame))
                    else:
                        time_until_next = FRAME_CAPTURE_INTERVAL - (current_time - self.last_capture_time)
                        logger.info(f"[VideoCapture] Skipping frame {frame_number}, next capture in {time_until_next:.1f}s")

                except Exception as frame_error:
                    logger.error(f"[VideoCapture] Error receiving frame {frame_number}: {frame_error}")
                    logger.error(f"[VideoCapture] Error type: {type(frame_error).__name__}")
                    import traceback
                    logger.error(f"[VideoCapture] Traceback: {traceback.format_exc()}")
                    # Don't break the loop on individual frame errors
                    await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"[VideoCapture] Fatal error in capture loop: {e}")
            logger.error(f"[VideoCapture] Error type: {type(e).__name__}")
            import traceback
            logger.error(f"[VideoCapture] Traceback: {traceback.format_exc()}")
        finally:
            self.running = False
            logger.info("[VideoCapture] Capture loop stopped")

    async def process_frame(self, frame: VideoFrame):
        """Process a single frame and send to facial recognition"""
        try:
            # Convert AVFrame to PIL Image
            img = frame.to_ndarray(format="rgb24")
            pil_image = Image.fromarray(img)

            # Convert to JPEG base64
            buffer = BytesIO()
            pil_image.save(buffer, format="JPEG", quality=80)
            buffer.seek(0)

            image_bytes = buffer.read()
            base64_image = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode('utf-8')

            logger.info(f"[VideoCapture] Captured frame: {len(base64_image)} chars")

            # Broadcast frame to WebSocket viewers
            await broadcast_frame(base64_image)

            # Send to facial recognition API
            await self.send_to_recognition(base64_image)

        except Exception as e:
            logger.error(f"[VideoCapture] Error processing frame: {e}")

    async def send_to_recognition(self, base64_image):
        """Send frame to facial recognition endpoint"""
        try:
            # Use requests in thread executor to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    FACIAL_RECOGNITION_URL,
                    json={
                        "display_id": self.display_id,
                        "location": self.location,
                        "image": base64_image
                    },
                    timeout=10
                )
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"[Recognition] Success: {result.get('success')}, Faces: {len(result.get('faces', []))}")

                # Results would be broadcast to clients via WebSocket if needed
                # For now, just log them
                if result.get('faces'):
                    for face in result['faces']:
                        logger.info(f"[Recognition] Detected: {face.get('userid')} ({face.get('confidence')})")
            else:
                logger.error(f"[Recognition] API error: {response.status_code}")

        except Exception as e:
            logger.error(f"[Recognition] Request failed: {e}")

    def stop(self):
        """Stop capturing frames"""
        self.running = False


async def broadcast_frame(base64_image):
    """Broadcast frame to all connected WebSocket clients"""
    logger.info(f"[Broadcast] Called with image size: {len(base64_image)} chars")
    logger.info(f"[Broadcast] Active WebSocket clients: {len(ws_clients)}")

    if not ws_clients:
        logger.warning("[Broadcast] No WebSocket clients connected, skipping broadcast")
        return

    message = json.dumps({
        "type": "frame",
        "data": base64_image,
        "timestamp": asyncio.get_event_loop().time()
    })

    logger.info(f"[Broadcast] Message JSON size: {len(message)} chars")

    # Send to all connected clients
    disconnected = set()
    for ws in ws_clients:
        try:
            logger.info(f"[Broadcast] Sending to WebSocket client...")
            await ws.send_str(message)
            logger.info(f"[Broadcast] Successfully sent to client")
        except Exception as e:
            logger.error(f"[WebSocket] Error sending to client: {e}")
            disconnected.add(ws)

    # Remove disconnected clients
    ws_clients.difference_update(disconnected)
    logger.info(f"[Broadcast] Broadcast complete to {len(ws_clients)} clients")


async def websocket_handler(request):
    """Handle WebSocket connections for live viewer"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    ws_clients.add(ws)
    logger.info(f"[WebSocket] Viewer connected. Total viewers: {len(ws_clients)}")

    try:
        # Send initial message
        await ws.send_str(json.dumps({
            "type": "connected",
            "message": "Connected to WebRTC frame viewer"
        }))

        # Keep connection alive
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                # Could handle viewer commands here
                pass
            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f"[WebSocket] Connection error: {ws.exception()}")

    except Exception as e:
        logger.error(f"[WebSocket] Handler error: {e}")
    finally:
        ws_clients.discard(ws)
        logger.info(f"[WebSocket] Viewer disconnected. Total viewers: {len(ws_clients)}")

    return ws


async def viewer(request):
    """Serve the HTML viewer page"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>WebRTC Frame Viewer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(255,255,255,0.15);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }
        h1 { font-size: 2.5em; margin-bottom: 20px; text-align: center; }
        .video-container {
            background: #000;
            border-radius: 15px;
            padding: 10px;
            margin: 30px auto;
            box-shadow: 0 10px 40px rgba(0,0,0,0.5);
            max-width: 800px;
        }
        #liveImage {
            width: 100%;
            height: auto;
            border-radius: 10px;
            display: block;
        }
        .placeholder {
            text-align: center;
            padding: 100px 20px;
            color: rgba(255,255,255,0.7);
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 30px;
        }
        .stat {
            padding: 20px;
            background: rgba(255,255,255,0.2);
            border-radius: 12px;
            text-align: center;
        }
        .stat-label { font-size: 0.9em; opacity: 0.8; margin-bottom: 8px; }
        .stat-value { font-size: 2em; font-weight: bold; }
        .ws-status { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-left: 8px; }
        .ws-status.connected { background: #44ff44; animation: pulse 2s infinite; }
        .ws-status.disconnected { background: #ff4444; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>WebRTC Frame Viewer</h1>

        <div class="video-container">
            <img id="liveImage" style="display:none;" alt="Live Camera Feed">
            <div id="placeholder" class="placeholder">
                <div style="font-size: 60px;">📹</div>
                <h2>Waiting for Frames...</h2>
                <p>Frames will appear here when WebRTC connection is active</p>
            </div>
        </div>

        <div class="stats">
            <div class="stat">
                <div class="stat-label">WebSocket <span class="ws-status" id="wsIndicator"></span></div>
                <div class="stat-value" id="wsStatus">Connecting...</div>
            </div>
            <div class="stat">
                <div class="stat-label">Frames Received</div>
                <div class="stat-value" id="frameCount">0</div>
            </div>
            <div class="stat">
                <div class="stat-label">Last Update</div>
                <div class="stat-value" id="lastUpdate" style="font-size: 1.2em;">Never</div>
            </div>
            <div class="stat">
                <div class="stat-label">Frame Rate</div>
                <div class="stat-value" id="fps">0.0</div>
            </div>
        </div>
    </div>

    <script>
        console.log('='.repeat(70));
        console.log('WebRTC Frame Viewer - CLIENT SIDE LOGGING');
        console.log('='.repeat(70));

        var ws = null;
        var frameCount = 0;
        var liveImage = document.getElementById('liveImage');
        var placeholder = document.getElementById('placeholder');
        var frameCountEl = document.getElementById('frameCount');
        var lastUpdateEl = document.getElementById('lastUpdate');
        var wsStatusEl = document.getElementById('wsStatus');
        var wsIndicator = document.getElementById('wsIndicator');
        var fpsEl = document.getElementById('fps');
        var lastFrameTime = 0;
        var frameTimestamps = [];

        console.log('[Viewer] All elements loaded successfully');
        console.log('[Viewer] Will connect to WebSocket at: ws://' + window.location.host + '/ws');

        function connectWebSocket() {
            console.log('[Viewer] ='.repeat(35));
            console.log('[Viewer] Initiating WebSocket connection...');
            var wsUrl = 'ws://' + window.location.host + '/ws';
            console.log('[Viewer] WebSocket URL:', wsUrl);
            ws = new WebSocket(wsUrl);

            ws.onopen = function() {
                console.log('WebSocket connected');
                wsStatusEl.textContent = 'Connected';
                wsIndicator.className = 'ws-status connected';
            };

            ws.onmessage = function(event) {
                console.log('='.repeat(50));
                console.log('[WebSocket] Message received');
                console.log('[WebSocket] Raw data length:', event.data.length);

                try {
                    var message = JSON.parse(event.data);
                    console.log('[WebSocket] Message type:', message.type);

                    if (message.type === 'frame' && message.data) {
                        frameCount++;
                        console.log('[WebSocket] FRAME MESSAGE RECEIVED!');
                        console.log('[WebSocket] Frame count:', frameCount);
                        console.log('[WebSocket] Frame data length:', message.data.length);
                        console.log('[WebSocket] Frame timestamp:', message.timestamp);

                        liveImage.src = message.data;
                        liveImage.style.display = 'block';
                        placeholder.style.display = 'none';
                        frameCountEl.textContent = frameCount;

                        var now = new Date();
                        lastUpdateEl.textContent = now.toLocaleTimeString();

                        // Calculate FPS
                        var currentTime = Date.now();
                        if (lastFrameTime > 0) {
                            frameTimestamps.push(currentTime);
                            // Keep only last 10 timestamps
                            if (frameTimestamps.length > 10) {
                                frameTimestamps.shift();
                            }
                            // Calculate average FPS
                            if (frameTimestamps.length > 1) {
                                var timeSpan = (frameTimestamps[frameTimestamps.length - 1] - frameTimestamps[0]) / 1000;
                                var fps = (frameTimestamps.length - 1) / timeSpan;
                                fpsEl.textContent = fps.toFixed(1);
                            }
                        }
                        lastFrameTime = currentTime;

                        console.log('[WebSocket] Frame', frameCount, 'processed successfully');
                    } else if (message.type === 'connected') {
                        console.log('[WebSocket] Connected:', message.message);
                    } else {
                        console.log('[WebSocket] Unknown message type or missing data');
                        console.log('[WebSocket] Message:', message);
                    }
                } catch(e) {
                    console.error('[WebSocket] Failed to parse message:', e);
                    console.error('[WebSocket] Raw data:', event.data.substring(0, 200));
                }
                console.log('='.repeat(50));
            };

            ws.onerror = function(error) {
                console.error('WebSocket error:', error);
                wsStatusEl.textContent = 'Error';
                wsIndicator.className = 'ws-status disconnected';
            };

            ws.onclose = function() {
                console.log('WebSocket closed, reconnecting...');
                wsStatusEl.textContent = 'Reconnecting...';
                wsIndicator.className = 'ws-status disconnected';
                setTimeout(connectWebSocket, 3000);
            };
        }

        connectWebSocket();
    </script>
</body>
</html>
    """
    return web.Response(text=html, content_type='text/html')


async def offer(request):
    """Handle WebRTC offer from client"""
    params = await request.json()
    offer_sdp = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    logger.info("=" * 50)
    logger.info("[WebRTC] Received offer from client")
    logger.info(f"[WebRTC] Offer SDP type: {offer_sdp.type}")
    logger.info("=" * 50)

    # Create peer connection
    pc = RTCPeerConnection()
    pcs.add(pc)
    logger.info(f"[WebRTC] Peer connection created, total connections: {len(pcs)}")

    # Store frame capture instance and video track
    frame_capture = None
    video_track = None

    @pc.on("track")
    async def on_track(track):
        nonlocal frame_capture, video_track
        logger.info(f"[WebRTC] Track received: {track.kind}")

        if track.kind == "video":
            logger.info("[WebRTC] Video track received, WAITING for connection to be established")
            video_track = track

        # Keep track alive - this is critical for aiortc
        @track.on("ended")
        async def on_ended():
            logger.info(f"[WebRTC] Track {track.kind} ended")
            if frame_capture:
                frame_capture.stop()

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        nonlocal frame_capture, video_track
        logger.info(f"[WebRTC] Connection state: {pc.connectionState}")

        if pc.connectionState == "connected" and video_track and not frame_capture:
            logger.info("=" * 50)
            logger.info("[WebRTC] Connection FULLY ESTABLISHED - Now starting frame capture!")
            logger.info("=" * 50)
            frame_capture = VideoFrameCapture(video_track, DISPLAY_ID, LOCATION)
            asyncio.create_task(frame_capture.start())

        elif pc.connectionState == "failed" or pc.connectionState == "closed":
            await pc.close()
            pcs.discard(pc)
            if frame_capture:
                frame_capture.stop()

    # Handle offer
    logger.info("[WebRTC] Setting remote description...")
    await pc.setRemoteDescription(offer_sdp)
    logger.info("[WebRTC] Remote description set")

    # Create answer
    logger.info("[WebRTC] Creating answer...")
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    logger.info("[WebRTC] Answer created and local description set")

    logger.info("[WebRTC] Sending answer to client")

    return web.Response(
        content_type="application/json",
        text=json.dumps({
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type
        })
    )


async def on_shutdown(app):
    """Cleanup on shutdown"""
    logger.info("[WebRTC] Shutting down, closing peer connections")
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


def create_app():
    """Create aiohttp application"""
    app = web.Application()
    app.add_routes([
        web.get("/", viewer),               # HTML viewer page
        web.get("/ws", websocket_handler),  # WebSocket for live frames
        web.post("/webrtc/offer", offer),   # WebRTC signaling
    ])
    app.on_shutdown.append(on_shutdown)
    return app


if __name__ == "__main__":
    # Run standalone WebRTC receiver on port 8080
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=8080)
