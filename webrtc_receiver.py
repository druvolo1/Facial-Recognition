"""
WebRTC Receiver for Tizen Camera Stream
Captures frames from WebRTC stream and sends to facial recognition API
"""
import asyncio
import base64
import json
import logging
import os
import time
from io import BytesIO

from aiohttp import web, ClientSession, ClientTimeout, FormData
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaRecorder, MediaPlayer
from av import VideoFrame
import numpy as np
from PIL import Image

# Optional database imports for person name lookups
try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("[Database] SQLAlchemy not available - person name lookups will be disabled")
    logger.warning("[Database] Install with: pip install sqlalchemy pymysql")

# Configure logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Store active peer connections and WebSocket clients
pcs = set()
ws_clients = set()  # All WebSocket clients (for backwards compatibility)
ws_clients_by_device = {}  # device_id -> set of WebSocket clients for that device

# Store active video tracks by device_id for on-demand capture
active_video_tracks = {}  # device_id -> VideoFrameCapture instance

# Store active peer connections by device_id for one-connection-per-device enforcement
active_device_connections = {}  # device_id -> RTCPeerConnection

# Configuration
# FACIAL_RECOGNITION_URL = "http://localhost:5000/api/displays/recognize"  # COMMENTED OUT FOR TESTING
CODEPROJECT_AI_URL = "http://172.16.1.150:32168/v1/vision/face/recognize"
DATABASE_URL = "mariadb+pymysql://app_user:testpass123@172.16.1.150:3306/facial_recognition"
DISPLAY_ID = "lobby_display_01"
LOCATION = "Front Lobby"
FRAME_CAPTURE_INTERVAL = 1.0  # Capture every 1 second (1 fps)

# WebRTC Network Configuration
PUBLIC_IP = "ruvolo.loseyourip.com"  # Your public hostname/IP
PORT_RANGE_MIN = 50000  # UDP port range start
PORT_RANGE_MAX = 50100  # UDP port range end (forward these UDP ports!)

# Configure aiortc to use public hostname and port range
os.environ['AIORTC_NAT_IP'] = PUBLIC_IP
os.environ['AIORTC_PORT_MIN'] = str(PORT_RANGE_MIN)
os.environ['AIORTC_PORT_MAX'] = str(PORT_RANGE_MAX)

# Scalability limits
MAX_CONNECTIONS = 100  # Maximum WebRTC peer connections
MAX_CONCURRENT_RECOGNITION = 10  # Maximum concurrent facial recognition API requests

# Database engine and cache (lazy initialization)
db_engine = None
person_name_cache = {}

# Semaphore to limit concurrent facial recognition API requests
recognition_semaphore = None  # Initialized in create_app()

def get_db_engine():
    """Lazy initialization of database engine"""
    global db_engine

    if not SQLALCHEMY_AVAILABLE:
        return None

    if db_engine is None:
        try:
            db_engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
            logger.info("[Database] ✓ Database connection initialized")
        except Exception as e:
            logger.error(f"[Database] Failed to create database engine: {e}")
            logger.error("[Database] Person name lookups will be disabled")
            db_engine = False  # Mark as failed to avoid retrying
    return db_engine if db_engine is not False else None


def validate_device_credentials(device_id, device_token):
    """
    Validate device credentials against database.

    Returns:
        tuple: (is_valid: bool, error_message: str or None, device_type: str or None)
    """
    engine = get_db_engine()
    if engine is None:
        logger.warning("[Auth] Database not available - authentication disabled")
        return (True, None, None)  # Allow connection if DB unavailable (failsafe)

    try:
        with Session(engine) as session:
            # Query device table
            query = text("""
                SELECT device_token, is_approved, device_type
                FROM device
                WHERE device_id = :device_id
                LIMIT 1
            """)
            result = session.execute(query, {"device_id": device_id})
            row = result.first()

            if not row:
                logger.warning(f"[Auth] Device not found: {device_id}")
                return (False, "Device not registered", None)

            stored_token, is_approved, device_type = row

            if not is_approved:
                logger.warning(f"[Auth] Device not approved: {device_id}")
                return (False, "Device not approved", None)

            if stored_token != device_token:
                logger.warning(f"[Auth] Invalid token for device: {device_id}")
                return (False, "Invalid device token", None)

            # Check device type is scanner or kiosk (only these should connect to WebRTC)
            if device_type not in ['people_scanner', 'registration_kiosk']:
                logger.warning(f"[Auth] Invalid device type for WebRTC: {device_type}")
                return (False, f"Device type '{device_type}' cannot connect to WebRTC relay", None)

            logger.info(f"[Auth] ✓ Device authenticated: {device_id} (type: {device_type})")
            return (True, None, device_type)

    except Exception as e:
        logger.error(f"[Auth] Database query error: {e}")
        return (False, "Authentication error", None)


def get_codeproject_url_for_device(device_id):
    """
    Get the CodeProject/InsightFace server URL for a device based on its location.

    Returns:
        str: The endpoint URL with /v1 prefix, or fallback to hardcoded URL
    """
    engine = get_db_engine()
    if engine is None:
        logger.warning(f"[Config] Database not available - using fallback CodeProject URL")
        return CODEPROJECT_AI_URL

    try:
        with Session(engine) as session:
            # Query device -> location -> codeproject_server -> endpoint_url
            query = text("""
                SELECT cs.endpoint_url
                FROM device d
                JOIN location l ON d.location_id = l.id
                JOIN codeproject_server cs ON l.codeproject_server_id = cs.id
                WHERE d.device_id = :device_id
                LIMIT 1
            """)
            result = session.execute(query, {"device_id": device_id})
            row = result.first()

            if row and row[0]:
                endpoint_url = row[0]
                # Ensure it ends with /v1 for compatibility
                if not endpoint_url.endswith('/v1'):
                    endpoint_url = endpoint_url.rstrip('/') + '/v1'
                logger.info(f"[Config] Using CodeProject server for device {device_id}: {endpoint_url}")
                return endpoint_url + '/vision/face/recognize'
            else:
                logger.warning(f"[Config] No CodeProject server found for device {device_id}, using fallback")
                return CODEPROJECT_AI_URL

    except Exception as e:
        logger.error(f"[Config] Error looking up CodeProject server: {e}")
        return CODEPROJECT_AI_URL


class VideoFrameCapture:
    """Captures frames from WebRTC video track"""

    def __init__(self, track, display_id, location, device_id=None):
        self.track = track
        self.display_id = display_id
        self.location = location
        self.device_id = device_id
        self.running = False
        self.last_capture_time = 0
        self.last_no_match_log_time = 0  # Track when we last logged "no faces matched"

        # Get CodeProject server URL based on device's location
        if device_id:
            self.recognition_url = get_codeproject_url_for_device(device_id)
        else:
            self.recognition_url = CODEPROJECT_AI_URL
            logger.warning("[VideoCapture] No device_id provided, using fallback CodeProject URL")

    async def start(self):
        """Start capturing frames from the video track"""
        self.running = True
        # logger.info("=" * 50)
        logger.info("[VideoCapture] Starting frame capture loop")
        # logger.info(f"[VideoCapture] Display ID: {self.display_id}")
        # logger.info(f"[VideoCapture] Location: {self.location}")
        # logger.info(f"[VideoCapture] Capture interval: {FRAME_CAPTURE_INTERVAL}s")
        # logger.info("=" * 50)

        frame_number = 0
        try:
            while self.running:
                try:
                    # Receive frame from track
                    # logger.info(f"[VideoCapture] Attempting to receive frame {frame_number}...")
                    # logger.info(f"[VideoCapture] Track state: {self.track.readyState if hasattr(self.track, 'readyState') else 'unknown'}")

                    # Add timeout to detect hanging
                    try:
                        frame = await asyncio.wait_for(self.track.recv(), timeout=5.0)
                    except asyncio.TimeoutError:
                        logger.error(f"[VideoCapture] TIMEOUT waiting for frame {frame_number} after 5 seconds!")
                        logger.error(f"[VideoCapture] Track may not be sending data or codec issue")
                        await asyncio.sleep(1)
                        continue

                    frame_number += 1
                    # logger.info(f"[VideoCapture] Frame {frame_number} received successfully!")
                    # logger.info(f"[VideoCapture] Frame type: {type(frame)}, format: {frame.format if hasattr(frame, 'format') else 'unknown'}")

                    # Check if enough time has passed since last capture
                    current_time = asyncio.get_event_loop().time()
                    if current_time - self.last_capture_time >= FRAME_CAPTURE_INTERVAL:
                        self.last_capture_time = current_time
                        # logger.info(f"[VideoCapture] Processing frame {frame_number}...")

                        # Process frame in background
                        asyncio.create_task(self.process_frame(frame))
                    # else:
                        # time_until_next = FRAME_CAPTURE_INTERVAL - (current_time - self.last_capture_time)
                        # logger.info(f"[VideoCapture] Skipping frame {frame_number}, next capture in {time_until_next:.1f}s")

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

            # Convert to JPEG base64 with high quality for facial recognition
            buffer = BytesIO()
            pil_image.save(buffer, format="JPEG", quality=95)
            buffer.seek(0)

            image_bytes = buffer.read()
            base64_image = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode('utf-8')

            # logger.info(f"[VideoCapture] Captured frame: {len(base64_image)} chars")

            # Broadcast frame to WebSocket viewers
            await broadcast_frame(base64_image)

            # Send to facial recognition API
            await self.send_to_recognition(base64_image)

        except Exception as e:
            logger.error(f"[VideoCapture] Error processing frame: {e}")

    async def get_person_name(self, person_id):
        """Fetch person name from database using person_id (UUID)"""
        if person_id == 'unknown':
            return 'Unknown Person'

        # Check cache first
        if person_id in person_name_cache:
            return person_name_cache[person_id]

        try:
            # Query database in thread executor to avoid blocking
            loop = asyncio.get_event_loop()
            person_name = await loop.run_in_executor(
                None,
                lambda: self._query_person_name(person_id)
            )

            # Cache the result
            person_name_cache[person_id] = person_name
            return person_name

        except Exception as e:
            logger.debug(f"[Recognition] Could not fetch name for {person_id}: {e}")
            return person_id  # Fallback to person_id if query fails

    def _query_person_name(self, person_id):
        """Synchronous database query for person name"""
        # Get database engine (lazy init)
        engine = get_db_engine()
        if engine is None:
            # Database not available, return person_id
            return person_id

        try:
            with Session(engine) as session:
                # Query registered_face table using codeproject_user_id (matches CodeProject.AI's userid)
                query = text("SELECT person_name FROM registered_face WHERE codeproject_user_id = :codeproject_user_id LIMIT 1")
                result = session.execute(query, {"codeproject_user_id": person_id})
                row = result.first()
                if row:
                    return row[0]
                else:
                    logger.debug(f"[Recognition] No person found with codeproject_user_id: {person_id}")
                    return person_id
        except Exception as e:
            logger.error(f"[Recognition] Database query error: {e}")
            return person_id

    async def send_to_recognition(self, base64_image):
        """Send frame directly to CodeProject.AI using async HTTP with concurrency limit"""
        global recognition_semaphore

        # Check queue depth before acquiring semaphore
        if recognition_semaphore is not None:
            waiting = recognition_semaphore._waiters
            if waiting and len(waiting) > 20:
                logger.warning(f"[Recognition] ⚠ Queue depth high: {len(waiting)} requests waiting, dropping frame")
                return  # Drop frame if queue is too deep

        try:
            # Acquire semaphore to limit concurrent recognition requests
            async with recognition_semaphore if recognition_semaphore else asyncio.Lock():
                # Extract base64 data (remove data URL prefix if present)
                if ',' in base64_image:
                    base64_data = base64_image.split(',')[1]
                else:
                    base64_data = base64_image

                # Decode base64 to bytes
                image_bytes = base64.b64decode(base64_data)
                image_size_kb = len(image_bytes) / 1024

                # Use async aiohttp client instead of blocking requests
                timeout = ClientTimeout(total=10)
                async with ClientSession(timeout=timeout) as session:
                    # Prepare multipart form data
                    data = FormData()
                    data.add_field('image',
                                  BytesIO(image_bytes),
                                  filename='frame.jpg',
                                  content_type='image/jpeg')

                    async with session.post(self.recognition_url, data=data) as response:
                        if response.status == 200:
                            result = await response.json()
                            predictions = result.get('predictions', [])
                            success = result.get('success', False)

                            # Enrich predictions with person names
                            enriched_predictions = []
                            if predictions:
                                logger.info("[Recognition] ✓ Faces detected:")
                                for i, pred in enumerate(predictions, 1):
                                    userid = pred.get('userid', 'unknown')
                                    confidence = pred.get('confidence', 0)

                                    # Fetch person name from backend
                                    person_name = await self.get_person_name(userid)

                                    # Add person_name to prediction
                                    enriched_pred = {**pred, 'person_name': person_name}
                                    enriched_predictions.append(enriched_pred)

                                    logger.info(f"  {i}. {person_name} ({confidence:.1%})")
                            else:
                                # Only log "no faces matched" once every 30 seconds to reduce spam
                                current_time = time.time()
                                if current_time - self.last_no_match_log_time >= 30:
                                    logger.info("[Recognition] No faces matched (suppressing repeats for 30s)")
                                    self.last_no_match_log_time = current_time

                            # Broadcast enriched results to WebSocket clients (only to this device)
                            await broadcast_recognition_result({
                                "success": success,
                                "faces": enriched_predictions,
                                "image_size_kb": image_size_kb,
                                "timestamp": asyncio.get_event_loop().time()
                            }, device_id=self.device_id)

                        else:
                            logger.error(f"[Recognition] ✗ API error: {response.status}")

        except asyncio.TimeoutError:
            logger.error("[Recognition] ✗ Request timeout (10s)")
        except Exception as e:
            logger.error(f"[Recognition] ✗ Request failed: {e}")

    def stop(self):
        """Stop capturing frames"""
        self.running = False

    async def capture_single_frame(self):
        """Capture a single frame on demand (for kiosk photo capture)"""
        try:
            logger.info("[OnDemandCapture] Capturing single frame...")
            # Receive frame from track
            frame = await asyncio.wait_for(self.track.recv(), timeout=5.0)

            # Convert AVFrame to PIL Image
            img = frame.to_ndarray(format="rgb24")
            pil_image = Image.fromarray(img)

            # Convert to JPEG base64 with maximum quality for kiosk registration
            buffer = BytesIO()
            pil_image.save(buffer, format="JPEG", quality=98)
            buffer.seek(0)

            image_bytes = buffer.read()
            base64_image = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode('utf-8')

            logger.info(f"[OnDemandCapture] ✓ Frame captured successfully")
            return base64_image

        except asyncio.TimeoutError:
            logger.error("[OnDemandCapture] Timeout waiting for frame")
            return None
        except Exception as e:
            logger.error(f"[OnDemandCapture] Error capturing frame: {e}")
            return None


async def broadcast_frame(base64_image):
    """Broadcast frame to all connected WebSocket clients"""
    # logger.info(f"[Broadcast] Called with image size: {len(base64_image)} chars")
    # logger.info(f"[Broadcast] Active WebSocket clients: {len(ws_clients)}")

    if not ws_clients:
        # logger.warning("[Broadcast] No WebSocket clients connected, skipping broadcast")
        return

    message = json.dumps({
        "type": "frame",
        "data": base64_image,
        "timestamp": asyncio.get_event_loop().time()
    })

    # logger.info(f"[Broadcast] Message JSON size: {len(message)} chars")

    # Send to all connected clients
    disconnected = set()
    for ws in ws_clients:
        try:
            # logger.info(f"[Broadcast] Sending to WebSocket client...")
            await ws.send_str(message)
            # logger.info(f"[Broadcast] Successfully sent to client")
        except Exception as e:
            logger.error(f"[WebSocket] Error sending to client: {e}")
            disconnected.add(ws)

    # Remove disconnected clients
    ws_clients.difference_update(disconnected)
    # logger.info(f"[Broadcast] Broadcast complete to {len(ws_clients)} clients")


async def broadcast_recognition_result(result_data, device_id=None):
    """
    Broadcast recognition results to WebSocket clients
    If device_id is provided, only send to that device's clients
    Otherwise, broadcast to all clients (legacy behavior)
    """
    # Determine which clients to send to
    if device_id and device_id in ws_clients_by_device:
        target_clients = ws_clients_by_device[device_id]
    else:
        target_clients = ws_clients

    if not target_clients:
        return

    message = json.dumps({
        "type": "recognition",
        "data": result_data
    })

    disconnected = set()
    for ws in target_clients:
        try:
            await ws.send_str(message)
        except Exception as e:
            logger.error(f"[WebSocket] Error sending recognition result: {e}")
            disconnected.add(ws)

    # Clean up disconnected clients
    if device_id and device_id in ws_clients_by_device:
        ws_clients_by_device[device_id].difference_update(disconnected)
    ws_clients.difference_update(disconnected)


async def websocket_handler(request):
    """Handle WebSocket connections for live viewer"""
    # Get authentication from query parameters (WebSocket can't use custom headers in browser)
    device_id = request.query.get('device_id')
    device_token = request.query.get('device_token')

    # Validate credentials if provided
    if device_id and device_token:
        is_valid, error_message, device_type = validate_device_credentials(device_id, device_token)
        if not is_valid:
            logger.warning(f"[WebSocket] ✗ Authentication failed for {device_id}: {error_message}")
            return web.Response(
                status=403,
                content_type="application/json",
                text=json.dumps({"error": error_message})
            )
        logger.info(f"[WebSocket] ✓ Authenticated connection from device: {device_id} (type: {device_type})")
    else:
        logger.info(f"[WebSocket] Unauthenticated viewer connected (browser viewer)")

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    ws_clients.add(ws)

    # Track device-specific WebSocket connections
    if device_id:
        if device_id not in ws_clients_by_device:
            ws_clients_by_device[device_id] = set()
        ws_clients_by_device[device_id].add(ws)
        logger.info(f"[WebSocket] Device {device_id} connected. Total viewers: {len(ws_clients)}")
    else:
        logger.info(f"[WebSocket] Unauthenticated viewer connected. Total viewers: {len(ws_clients)}")

    try:
        # Send initial message
        await ws.send_str(json.dumps({
            "type": "connected",
            "message": "Connected to WebRTC frame viewer"
        }))

        # Keep connection alive and handle commands
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    msg_type = data.get('type')

                    if msg_type == 'ping':
                        # Handle keepalive ping
                        await ws.send_str(json.dumps({"type": "pong"}))

                    elif msg_type == 'capture_frame':
                        # Handle on-demand frame capture for kiosk
                        device_id = data.get('device_id')
                        frame_index = data.get('frame_index', 0)

                        logger.info(f"[WebSocket] Capture request from device {device_id}, frame {frame_index}")

                        # Get the video track for this device
                        if device_id in active_video_tracks:
                            frame_capture = active_video_tracks[device_id]
                            captured_image = await frame_capture.capture_single_frame()

                            if captured_image:
                                # Send back the captured frame
                                await ws.send_str(json.dumps({
                                    "type": "capture_result",
                                    "data": {
                                        "success": True,
                                        "image": captured_image,
                                        "frame_index": frame_index
                                    }
                                }))
                                logger.info(f"[WebSocket] ✓ Frame {frame_index} sent to device {device_id}")
                            else:
                                # Failed to capture
                                await ws.send_str(json.dumps({
                                    "type": "capture_result",
                                    "data": {
                                        "success": False,
                                        "frame_index": frame_index,
                                        "error": "Failed to capture frame"
                                    }
                                }))
                                logger.error(f"[WebSocket] ✗ Failed to capture frame {frame_index}")
                        else:
                            logger.warning(f"[WebSocket] No active video track for device {device_id}")
                            await ws.send_str(json.dumps({
                                "type": "capture_result",
                                "data": {
                                    "success": False,
                                    "frame_index": frame_index,
                                    "error": "No active video connection"
                                }
                            }))

                    elif msg_type == 'refresh_config':
                        # Handle CodeProject server config refresh
                        device_id = data.get('device_id')
                        logger.info(f"[WebSocket] Config refresh request from device {device_id}")

                        # Get the video track for this device and refresh its recognition URL
                        if device_id in active_video_tracks:
                            frame_capture = active_video_tracks[device_id]
                            old_url = frame_capture.recognition_url
                            new_url = get_codeproject_url_for_device(device_id)
                            frame_capture.recognition_url = new_url
                            logger.info(f"[Config] ✓ Updated recognition URL for {device_id}: {old_url} → {new_url}")
                        else:
                            logger.warning(f"[WebSocket] No active video track for device {device_id}, config will update on next connection")

                except json.JSONDecodeError:
                    logger.error(f"[WebSocket] Failed to parse message: {msg.data}")
                except Exception as e:
                    logger.error(f"[WebSocket] Error handling message: {e}")

            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f"[WebSocket] Connection error: {ws.exception()}")

            elif msg.type == web.WSMsgType.CLOSE:
                logger.info(f"[WebSocket] Client requested close")
                break

    except asyncio.CancelledError:
        # Don't log cancellation as an error - this is normal during shutdown
        logger.debug(f"[WebSocket] Connection cancelled (shutdown)")
        raise
    except ConnectionResetError:
        logger.info(f"[WebSocket] Connection reset by client")
    except Exception as e:
        logger.error(f"[WebSocket] Handler error: {e}")
    finally:
        ws_clients.discard(ws)

        # Remove from device-specific tracking
        if device_id and device_id in ws_clients_by_device:
            ws_clients_by_device[device_id].discard(ws)
            if len(ws_clients_by_device[device_id]) == 0:
                del ws_clients_by_device[device_id]

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
        .recognition-card {
            margin-top: 30px;
            padding: 30px;
            background: rgba(255,255,255,0.2);
            border-radius: 15px;
            display: none;
        }
        .recognition-card h2 {
            font-size: 1.8em;
            margin-bottom: 20px;
            text-align: center;
        }
        .recognition-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .recognition-info-item {
            padding: 15px;
            background: rgba(255,255,255,0.3);
            border-radius: 10px;
            text-align: center;
        }
        .recognition-info-label {
            font-size: 0.9em;
            opacity: 0.9;
            margin-bottom: 8px;
        }
        .recognition-info-value {
            font-size: 1.5em;
            font-weight: bold;
        }
        .faces-detected {
            margin-top: 20px;
        }
        .face-card {
            background: linear-gradient(135deg, #48bb78 0%, #38a169 100%);
            padding: 20px;
            border-radius: 12px;
            margin: 10px 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .face-card.no-match {
            background: linear-gradient(135deg, #fc8181 0%, #f56565 100%);
        }
        .face-name {
            font-size: 1.5em;
            font-weight: bold;
        }
        .face-confidence {
            font-size: 1.2em;
            opacity: 0.9;
        }
        .recognition-history {
            margin-top: 30px;
            padding: 30px;
            background: rgba(255,255,255,0.2);
            border-radius: 15px;
            display: none;
        }
        .recognition-history h2 {
            font-size: 1.8em;
            margin-bottom: 20px;
            text-align: center;
        }
        .history-list {
            max-height: 400px;
            overflow-y: auto;
            padding-right: 10px;
        }
        .history-item {
            background: rgba(255,255,255,0.3);
            padding: 15px 20px;
            border-radius: 10px;
            margin: 10px 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            animation: slideIn 0.3s ease-out;
        }
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateX(-20px);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }
        .history-time {
            font-size: 0.9em;
            opacity: 0.8;
            white-space: nowrap;
        }
        .history-faces {
            flex: 1;
            margin: 0 15px;
        }
        .history-face {
            display: inline-block;
            background: rgba(72,187,120,0.8);
            padding: 5px 12px;
            border-radius: 20px;
            margin: 2px;
            font-size: 0.95em;
        }
        .history-face.unknown {
            background: rgba(252,129,129,0.8);
        }
        .history-count {
            font-size: 1.2em;
            font-weight: bold;
            background: rgba(102,126,234,0.8);
            padding: 5px 12px;
            border-radius: 20px;
            white-space: nowrap;
        }
        /* Scrollbar styling */
        .history-list::-webkit-scrollbar {
            width: 8px;
        }
        .history-list::-webkit-scrollbar-track {
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
        }
        .history-list::-webkit-scrollbar-thumb {
            background: rgba(255,255,255,0.3);
            border-radius: 10px;
        }
        .history-list::-webkit-scrollbar-thumb:hover {
            background: rgba(255,255,255,0.5);
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

        <!-- Recognition Results Card -->
        <div class="recognition-card" id="recognitionCard">
            <h2>🔍 Face Recognition</h2>
            <div class="recognition-info">
                <div class="recognition-info-item">
                    <div class="recognition-info-label">Status</div>
                    <div class="recognition-info-value" id="recStatus">--</div>
                </div>
                <div class="recognition-info-item">
                    <div class="recognition-info-label">Image Size</div>
                    <div class="recognition-info-value" id="recImageSize">--</div>
                </div>
                <div class="recognition-info-item">
                    <div class="recognition-info-label">Faces Found</div>
                    <div class="recognition-info-value" id="recFaceCount">0</div>
                </div>
                <div class="recognition-info-item">
                    <div class="recognition-info-label">Last Scan</div>
                    <div class="recognition-info-value" id="recLastScan" style="font-size: 1.1em;">--</div>
                </div>
            </div>
            <div class="faces-detected" id="facesDetected"></div>
        </div>

        <!-- Recognition History -->
        <div class="recognition-history" id="recognitionHistory">
            <h2>📋 Recognition History</h2>
            <div class="history-list" id="historyList"></div>
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
                // console.log('='.repeat(50));
                // console.log('[WebSocket] Message received');
                // console.log('[WebSocket] Raw data length:', event.data.length);

                try {
                    var message = JSON.parse(event.data);
                    // console.log('[WebSocket] Message type:', message.type);

                    if (message.type === 'frame' && message.data) {
                        frameCount++;
                        // console.log('[WebSocket] FRAME MESSAGE RECEIVED!');
                        // console.log('[WebSocket] Frame count:', frameCount);
                        // console.log('[WebSocket] Frame data length:', message.data.length);
                        // console.log('[WebSocket] Frame timestamp:', message.timestamp);

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

                        // console.log('[WebSocket] Frame', frameCount, 'processed successfully');
                    } else if (message.type === 'connected') {
                        console.log('[WebSocket] Connected:', message.message);
                    } else if (message.type === 'recognition') {
                        console.log('[Recognition] RESULT RECEIVED!');
                        console.log('[Recognition] Data:', message.data);
                        handleRecognitionResult(message.data);
                    } else {
                        console.log('[WebSocket] Unknown message type:', message.type);
                    }
                } catch(e) {
                    console.error('[WebSocket] Failed to parse message:', e);
                }
                // console.log('='.repeat(50));
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

        var recognitionHistory = [];
        var maxHistoryItems = 50;

        function handleRecognitionResult(data) {
            console.log('[Recognition] Processing result data...');

            var now = new Date();

            // Show recognition card
            var recognitionCard = document.getElementById('recognitionCard');
            recognitionCard.style.display = 'block';

            // Update status
            var recStatus = document.getElementById('recStatus');
            if (data.success) {
                recStatus.textContent = '✓ Success';
                recStatus.style.color = '#48bb78';
            } else {
                recStatus.textContent = '✗ Failed';
                recStatus.style.color = '#fc8181';
            }

            // Update image size
            document.getElementById('recImageSize').textContent = data.image_size_kb.toFixed(2) + ' KB';

            // Update face count
            var faceCount = data.faces ? data.faces.length : 0;
            document.getElementById('recFaceCount').textContent = faceCount;

            // Update last scan time
            document.getElementById('recLastScan').textContent = now.toLocaleTimeString();

            // Display detected faces
            var facesDetected = document.getElementById('facesDetected');
            facesDetected.innerHTML = '';

            if (faceCount > 0) {
                console.log('[Recognition] Displaying', faceCount, 'faces');
                data.faces.forEach(function(face, index) {
                    var faceCard = document.createElement('div');
                    faceCard.className = 'face-card';

                    var userid = face.userid || 'unknown';
                    var confidence = face.confidence || 0;

                    if (userid === 'unknown') {
                        faceCard.classList.add('no-match');
                    }

                    faceCard.innerHTML =
                        '<div class="face-name">👤 ' + userid.replace(/_/g, ' ').toUpperCase() + '</div>' +
                        '<div class="face-confidence">' + (confidence * 100).toFixed(1) + '%</div>';

                    facesDetected.appendChild(faceCard);

                    console.log('[Recognition] Face', (index + 1) + ':', userid, '(' + (confidence * 100).toFixed(1) + '%)');
                });

                // Add to history
                addToHistory(now, data.faces);
            } else {
                console.log('[Recognition] No faces detected');
                facesDetected.innerHTML = '<div style="text-align: center; padding: 20px; opacity: 0.7;">No faces detected in this frame</div>';
            }
        }

        function addToHistory(timestamp, faces) {
            // Show history section
            var historySection = document.getElementById('recognitionHistory');
            historySection.style.display = 'block';

            // Add to history array
            recognitionHistory.unshift({
                timestamp: timestamp,
                faces: faces
            });

            // Keep only max items
            if (recognitionHistory.length > maxHistoryItems) {
                recognitionHistory.pop();
            }

            // Update history display
            updateHistoryDisplay();
        }

        function updateHistoryDisplay() {
            var historyList = document.getElementById('historyList');
            historyList.innerHTML = '';

            recognitionHistory.forEach(function(item, index) {
                var historyItem = document.createElement('div');
                historyItem.className = 'history-item';

                // Time
                var timeDiv = document.createElement('div');
                timeDiv.className = 'history-time';
                timeDiv.textContent = item.timestamp.toLocaleTimeString();

                // Faces
                var facesDiv = document.createElement('div');
                facesDiv.className = 'history-faces';

                item.faces.forEach(function(face) {
                    var faceSpan = document.createElement('span');
                    faceSpan.className = 'history-face';
                    var userid = face.userid || 'unknown';
                    if (userid === 'unknown') {
                        faceSpan.classList.add('unknown');
                    }
                    faceSpan.textContent = userid.replace(/_/g, ' ').toUpperCase() + ' (' + (face.confidence * 100).toFixed(0) + '%)';
                    facesDiv.appendChild(faceSpan);
                });

                // Count
                var countDiv = document.createElement('div');
                countDiv.className = 'history-count';
                countDiv.textContent = item.faces.length + ' face' + (item.faces.length !== 1 ? 's' : '');

                historyItem.appendChild(timeDiv);
                historyItem.appendChild(facesDiv);
                historyItem.appendChild(countDiv);

                historyList.appendChild(historyItem);
            });
        }

        connectWebSocket();
    </script>
</body>
</html>
    """
    return web.Response(text=html, content_type='text/html')


async def offer(request):
    """Handle WebRTC offer from client"""
    # Get authentication credentials from headers
    device_id = request.headers.get("X-Device-ID")
    device_token = request.headers.get("X-Device-Token")

    if not device_id or not device_token:
        logger.warning("[WebRTC] ✗ Missing authentication credentials")
        return web.Response(
            status=401,
            content_type="application/json",
            text=json.dumps({"error": "Missing device credentials"})
        )

    # Validate device credentials
    is_valid, error_message, device_type = validate_device_credentials(device_id, device_token)
    if not is_valid:
        logger.warning(f"[WebRTC] ✗ Authentication failed for {device_id}: {error_message}")
        return web.Response(
            status=403,
            content_type="application/json",
            text=json.dumps({"error": error_message})
        )

    logger.info(f"[WebRTC] ✓ Device authenticated: {device_id} (type: {device_type})")

    # Check if device already has an active connection
    if device_id in active_device_connections:
        old_pc = active_device_connections[device_id]
        logger.info(f"[WebRTC] Device {device_id} already connected - closing old connection")
        try:
            await old_pc.close()
            if old_pc in pcs:
                pcs.remove(old_pc)
        except Exception as e:
            logger.warning(f"[WebRTC] Error closing old connection: {e}")

    # Check connection limit
    if len(pcs) >= MAX_CONNECTIONS:
        logger.error(f"[WebRTC] ✗ Connection limit reached ({MAX_CONNECTIONS}), rejecting new connection")
        return web.Response(
            status=503,
            content_type="application/json",
            text=json.dumps({
                "error": "Connection limit reached",
                "max_connections": MAX_CONNECTIONS,
                "current_connections": len(pcs)
            })
        )

    params = await request.json()
    offer_sdp = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    logger.info("=" * 50)
    logger.info("[WebRTC] Received offer from client")
    logger.info(f"[WebRTC] Device ID: {device_id}")
    logger.info(f"[WebRTC] Offer SDP type: {offer_sdp.type}")
    logger.info("[WebRTC] FULL SDP OFFER:")
    logger.info(offer_sdp.sdp)
    logger.info("=" * 50)

    # Create peer connection with STUN server
    ice_servers = [
        RTCIceServer(urls=["stun:stun.l.google.com:19302"])
        # TURN server removed - using reverse proxy for now
    ]
    configuration = RTCConfiguration(iceServers=ice_servers)
    pc = RTCPeerConnection(configuration=configuration)

    pcs.add(pc)
    active_device_connections[device_id] = pc  # Track connection by device_id
    logger.info(f"[WebRTC] Peer connection created with public IP: {PUBLIC_IP}")
    logger.info(f"[WebRTC] Using UDP port range: {PORT_RANGE_MIN}-{PORT_RANGE_MAX}")
    logger.info(f"[WebRTC] Total connections: {len(pcs)}/{MAX_CONNECTIONS}")

    # Store frame capture instance and video track
    frame_capture = None
    video_track = None

    @pc.on("track")
    async def on_track(track):
        nonlocal frame_capture, video_track
        logger.info(f"[WebRTC] Track received: {track.kind}")
        logger.info(f"[WebRTC] Track ID: {track.id}")

        if track.kind == "video":
            logger.info("[WebRTC] Video track received, WAITING for connection to be established")
            logger.info(f"[WebRTC] Video track details: {track}")
            # Log codec information if available
            if hasattr(track, '_RTCRtpReceiver__codecs'):
                logger.info(f"[WebRTC] Track codecs: {track._RTCRtpReceiver__codecs}")
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
            frame_capture = VideoFrameCapture(video_track, DISPLAY_ID, LOCATION, device_id)

            # Register this device's video track for on-demand capture
            active_video_tracks[device_id] = frame_capture
            logger.info(f"[WebRTC] Registered device {device_id} for on-demand capture")

            asyncio.create_task(frame_capture.start())

        elif pc.connectionState == "failed" or pc.connectionState == "closed":
            await pc.close()
            pcs.discard(pc)
            if frame_capture:
                frame_capture.stop()
            # Remove from active tracks
            if device_id in active_video_tracks:
                del active_video_tracks[device_id]
                logger.info(f"[WebRTC] Removed device {device_id} from active tracks")
            # Remove from active device connections
            if device_id in active_device_connections and active_device_connections[device_id] == pc:
                del active_device_connections[device_id]
                logger.info(f"[WebRTC] Removed device {device_id} from active connections")

    # Handle offer
    logger.info("[WebRTC] Setting remote description...")
    await pc.setRemoteDescription(offer_sdp)
    logger.info("[WebRTC] Remote description set")

    # Create answer
    logger.info("[WebRTC] Creating answer...")
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    logger.info("[WebRTC] Answer created and local description set")
    logger.info("[WebRTC] FULL SDP ANSWER:")
    logger.info(pc.localDescription.sdp)
    logger.info("=" * 50)

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
    global recognition_semaphore

    # Initialize semaphore for limiting concurrent recognition requests
    recognition_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RECOGNITION)
    logger.info(f"[Scalability] Connection limit: {MAX_CONNECTIONS}")
    logger.info(f"[Scalability] Max concurrent recognition requests: {MAX_CONCURRENT_RECOGNITION}")

    # CORS middleware to allow test page access
    @web.middleware
    async def cors_middleware(request, handler):
        # Handle preflight OPTIONS request
        if request.method == 'OPTIONS':
            response = web.Response()
        else:
            response = await handler(request)

        # Add CORS headers
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Device-ID, X-Device-Token'
        return response

    app = web.Application(middlewares=[cors_middleware])
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
