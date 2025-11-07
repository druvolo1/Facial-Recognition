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

# Store active peer connections
pcs = set()

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
        logger.info("[VideoCapture] Starting frame capture loop")

        try:
            while self.running:
                # Receive frame from track
                frame = await self.track.recv()

                # Check if enough time has passed since last capture
                current_time = asyncio.get_event_loop().time()
                if current_time - self.last_capture_time >= FRAME_CAPTURE_INTERVAL:
                    self.last_capture_time = current_time

                    # Process frame in background
                    asyncio.create_task(self.process_frame(frame))

        except Exception as e:
            logger.error(f"[VideoCapture] Error in capture loop: {e}")
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


async def offer(request):
    """Handle WebRTC offer from client"""
    params = await request.json()
    offer_sdp = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    logger.info("[WebRTC] Received offer from client")

    # Create peer connection
    pc = RTCPeerConnection()
    pcs.add(pc)

    # Store frame capture instance
    frame_capture = None

    @pc.on("track")
    def on_track(track):
        nonlocal frame_capture
        logger.info(f"[WebRTC] Track received: {track.kind}")

        if track.kind == "video":
            logger.info("[WebRTC] Video track received, starting frame capture")
            frame_capture = VideoFrameCapture(track, DISPLAY_ID, LOCATION)
            asyncio.create_task(frame_capture.start())

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"[WebRTC] Connection state: {pc.connectionState}")
        if pc.connectionState == "failed" or pc.connectionState == "closed":
            await pc.close()
            pcs.discard(pc)
            if frame_capture:
                frame_capture.stop()

    # Handle offer
    await pc.setRemoteDescription(offer_sdp)

    # Create answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

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
        web.post("/webrtc/offer", offer),
    ])
    app.on_shutdown.append(on_shutdown)
    return app


if __name__ == "__main__":
    # Run standalone WebRTC receiver on port 8080
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=8080)
