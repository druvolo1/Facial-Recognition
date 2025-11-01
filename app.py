from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import base64
import os
import json
from datetime import datetime
from io import BytesIO
from PIL import Image
import re
from urllib.parse import urlparse
import subprocess
import hashlib
import pyttsx3

app = Flask(__name__)

# Enable CORS for all routes (allows SSSP displays to make API requests)
# Support for both null origin (file://) and any other origin
CORS(app,
     resources={r"/api/*": {"origins": "*"}},
     supports_credentials=False,
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "DELETE", "OPTIONS"],
     expose_headers=["Content-Type"],
     send_wildcard=True)

# CodeProject.AI configuration
CODEPROJECT_HOST = "172.16.1.150"
CODEPROJECT_PORT = 32168
CODEPROJECT_BASE_URL = f"http://{CODEPROJECT_HOST}:{CODEPROJECT_PORT}/v1"

# Create uploads directory if it doesn't exist
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Create audio directory for TTS files
AUDIO_FOLDER = "audio"
os.makedirs(AUDIO_FOLDER, exist_ok=True)

# User database file
USER_DB_FILE = "users.json"

# Display database file
DISPLAY_DB_FILE = "displays.json"

# Image processing settings
MAX_IMAGE_SIZE = (640, 480)  # Resize images to max 640x480 for faster processing


def resize_image_if_needed(image_bytes, max_size=MAX_IMAGE_SIZE):
    """Resize image if it's larger than max_size to speed up processing"""
    try:
        img = Image.open(BytesIO(image_bytes))
        original_size = img.size

        # Only resize if image is larger than max size
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            output = BytesIO()
            img.save(output, format='JPEG', quality=85)
            resized_bytes = output.getvalue()

            print(f"[RESIZE] Image resized from {original_size} to {img.size}")
            print(f"[RESIZE] Size reduced from {len(image_bytes)/1024:.2f}KB to {len(resized_bytes)/1024:.2f}KB")

            return resized_bytes
        else:
            print(f"[RESIZE] Image size {original_size} is OK, no resize needed")
            return image_bytes

    except Exception as e:
        print(f"[RESIZE] Warning: Could not resize image: {e}")
        return image_bytes


# User Database Functions
def load_users():
    """Load users from JSON database"""
    if os.path.exists(USER_DB_FILE):
        try:
            with open(USER_DB_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []


def save_users(users):
    """Save users to JSON database"""
    with open(USER_DB_FILE, 'w') as f:
        json.dump(users, f, indent=2)


def add_user(userid, name, photo_path, source="manual"):
    """Add a user to the database"""
    users = load_users()

    # Check if user already exists
    for user in users:
        if user['userid'] == userid:
            return False, "User already exists"

    user_data = {
        "userid": userid,
        "name": name,
        "photo_path": photo_path,
        "source": source,
        "registered_at": datetime.now().isoformat(),
        "photo_count": 1
    }

    users.append(user_data)
    save_users(users)
    return True, "User added successfully"


def delete_user(userid):
    """Delete a user from the database"""
    users = load_users()
    users = [u for u in users if u['userid'] != userid]
    save_users(users)
    return True


def get_user(userid):
    """Get a specific user"""
    users = load_users()
    for user in users:
        if user['userid'] == userid:
            return user
    return None


# Display Database Functions
def load_displays():
    """Load displays from JSON database"""
    if os.path.exists(DISPLAY_DB_FILE):
        try:
            with open(DISPLAY_DB_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []


def save_displays(displays):
    """Save displays to JSON database"""
    with open(DISPLAY_DB_FILE, 'w') as f:
        json.dump(displays, f, indent=2)


def register_or_update_display(display_id, location, capabilities=None):
    """Register or update a display"""
    displays = load_displays()

    # Check if display already exists
    for display in displays:
        if display['display_id'] == display_id:
            # Update existing display
            display['location'] = location
            display['last_seen'] = datetime.now().isoformat()
            if capabilities:
                display['capabilities'] = capabilities
            save_displays(displays)
            return display, False  # False = not newly created

    # Add new display
    display_data = {
        "display_id": display_id,
        "location": location,
        "capabilities": capabilities or {},
        "registered_at": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
        "detection_count": 0,
        "last_detection": None
    }

    displays.append(display_data)
    save_displays(displays)
    return display_data, True  # True = newly created


def update_display_detection(display_id, detection_data):
    """Update display with new detection information"""
    displays = load_displays()

    for display in displays:
        if display['display_id'] == display_id:
            display['last_seen'] = datetime.now().isoformat()
            display['detection_count'] = display.get('detection_count', 0) + len(detection_data.get('faces', []))
            display['last_detection'] = {
                "timestamp": datetime.now().isoformat(),
                "faces": detection_data.get('faces', [])
            }
            save_displays(displays)
            return True

    return False


def get_display(display_id):
    """Get a specific display"""
    displays = load_displays()
    for display in displays:
        if display['display_id'] == display_id:
            return display
    return None


def fetch_linkedin_profile(linkedin_url):
    """
    Fetch profile info from LinkedIn URL
    NOTE: LinkedIn has strong anti-scraping measures. This is a basic approach
    that may not work for all profiles. Consider using LinkedIn API for production.
    """
    try:
        print(f"[LINKEDIN] Fetching profile from: {linkedin_url}")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(linkedin_url, headers=headers, timeout=10)
        print(f"[LINKEDIN] Page fetch status: {response.status_code}")

        if response.status_code != 200:
            error_msg = f"Failed to fetch LinkedIn page (status {response.status_code})"
            print(f"[LINKEDIN] {error_msg}")
            return None, error_msg

        html = response.text
        print(f"[LINKEDIN] HTML length: {len(html)} characters")

        # Try to extract name from title tag or Open Graph meta
        name = None

        # Try og:title meta tag
        og_title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
        if og_title_match:
            name = og_title_match.group(1)
            print(f"[LINKEDIN] Raw name from og:title: {name}")
            # Clean up (remove " | LinkedIn" suffix)
            name = re.sub(r'\s*\|\s*LinkedIn.*$', '', name)
            # Clean up (remove " - Company Name" suffix if present)
            name = re.sub(r'\s*-\s*[A-Z].*$', '', name).strip()
        else:
            print(f"[LINKEDIN] No og:title meta tag found")

        # Try to find profile image
        photo_url = None
        og_image_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        if og_image_match:
            photo_url = og_image_match.group(1)
            print(f"[LINKEDIN] Raw photo URL: {photo_url}")
            # Decode HTML entities (&amp; -> &)
            import html as html_module
            photo_url = html_module.unescape(photo_url)
        else:
            print(f"[LINKEDIN] No og:image meta tag found")

        if not name:
            error_msg = "Could not extract name from LinkedIn profile"
            print(f"[LINKEDIN] ERROR: {error_msg}")
            return None, error_msg

        if not photo_url:
            error_msg = "Could not extract photo from LinkedIn profile"
            print(f"[LINKEDIN] ERROR: {error_msg}")
            return None, error_msg

        print(f"[LINKEDIN] Extracted name: {name}")
        print(f"[LINKEDIN] Photo URL: {photo_url}")

        # Download the photo
        photo_response = requests.get(photo_url, timeout=10, headers=headers)
        print(f"[LINKEDIN] Photo download status: {photo_response.status_code}")

        if photo_response.status_code == 200:
            photo_data = photo_response.content
            print(f"[LINKEDIN] Downloaded photo: {len(photo_data)} bytes")

            return {
                'name': name,
                'photo_data': photo_data,
                'photo_url': photo_url
            }, None
        else:
            error_msg = f"Could not download profile photo (HTTP {photo_response.status_code})"
            print(f"[LINKEDIN] {error_msg}")
            return None, error_msg

    except requests.exceptions.Timeout:
        return None, "Request timed out"
    except requests.exceptions.ConnectionError:
        return None, "Connection error"
    except Exception as e:
        print(f"[LINKEDIN] Error: {e}")
        return None, str(e)


@app.route('/')
def index():
    """Home page with links to registration and recognition"""
    return render_template('index.html')


@app.route('/register')
def register_page():
    """Registration page"""
    return render_template('register.html')


@app.route('/recognize')
def recognize_page():
    """Recognition page"""
    return render_template('recognize.html')


@app.route('/diagnostics')
def diagnostics_page():
    """Diagnostics page"""
    return render_template('diagnostics.html')


@app.route('/manage')
def manage_page():
    """User management page"""
    return render_template('manage.html')


@app.route('/greet')
def greet_page():
    """AI Greeter page"""
    return render_template('greet.html')


@app.route('/monitor')
def monitor_page():
    """Display monitoring page"""
    return render_template('monitor.html')


@app.route('/uploads/<filename>')
def serve_upload(filename):
    """Serve uploaded files"""
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/audio/<filename>')
def serve_audio(filename):
    """Serve generated audio files"""
    return send_from_directory(AUDIO_FOLDER, filename)


@app.route('/api/tts', methods=['POST'])
def text_to_speech():
    """
    Generate speech audio and lip sync data using pyttsx3 + rhubarb-lip-sync
    Expects JSON: {
        "text": "Hello, welcome!"
    }
    Returns: {
        "success": true,
        "audio_url": "/audio/filename.wav",
        "visemes": [...rhubarb viseme data...]
    }
    """
    try:
        print(f"\n{'='*60}")
        print(f"[TTS] Text-to-speech request at {datetime.now().strftime('%H:%M:%S')}")

        data = request.get_json()
        text = data.get('text', '')

        if not text:
            return jsonify({"success": False, "error": "Text is required"}), 400

        print(f"[TTS] Text: {text}")

        # Create a hash of the text for caching
        text_hash = hashlib.md5(text.encode()).hexdigest()[:12]
        audio_filename = f"tts_{text_hash}.wav"
        audio_path = os.path.join(AUDIO_FOLDER, audio_filename)
        json_filename = f"tts_{text_hash}.json"
        json_path = os.path.join(AUDIO_FOLDER, json_filename)

        # Check if already generated (cache)
        if os.path.exists(audio_path) and os.path.exists(json_path):
            print(f"[TTS] Using cached audio and visemes")
            with open(json_path, 'r') as f:
                viseme_data = json.load(f)

            return jsonify({
                "success": True,
                "audio_url": f"/audio/{audio_filename}",
                "visemes": viseme_data,
                "cached": True
            })

        # Generate audio using pyttsx3
        print(f"[TTS] Generating audio with pyttsx3...")
        try:
            # Initialize with specific driver for Windows
            try:
                engine = pyttsx3.init('sapi5')  # Windows SAPI5
            except:
                engine = pyttsx3.init()  # Fallback to default

            # Set properties for better quality
            voices = engine.getProperty('voices')
            print(f"[TTS] Available voices: {len(voices)}")

            # Try to use a female voice (usually index 1 on Windows)
            if len(voices) > 1:
                engine.setProperty('voice', voices[1].id)
                print(f"[TTS] Using voice: {voices[1].name}")
            elif len(voices) > 0:
                engine.setProperty('voice', voices[0].id)
                print(f"[TTS] Using voice: {voices[0].name}")

            engine.setProperty('rate', 150)  # Speed
            engine.setProperty('volume', 1.0)

            # Save to file
            engine.save_to_file(text, audio_path)
            engine.runAndWait()

            # Important: Stop the engine to release resources
            engine.stop()

            print(f"[TTS] ✓ Audio generated: {audio_filename}")

        except Exception as e:
            print(f"[TTS] ✗ Error generating audio: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({
                "success": False,
                "error": f"Failed to generate audio: {str(e)}"
            }), 500

        # Run rhubarb-lip-sync on the audio file
        print(f"[TTS] Running rhubarb-lip-sync...")
        try:
            # Run rhubarb with JSON output
            result = subprocess.run(
                ['rhubarb', '-f', 'json', audio_path],
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )

            # Parse JSON output
            viseme_data = json.loads(result.stdout)

            # Save viseme data for caching
            with open(json_path, 'w') as f:
                json.dump(viseme_data, f)

            print(f"[TTS] ✓ Lip sync data generated")
            print(f"[TTS] ✓ Viseme cues: {len(viseme_data.get('mouthCues', []))}")

        except subprocess.TimeoutExpired:
            print(f"[TTS] ✗ Rhubarb timed out")
            return jsonify({
                "success": False,
                "error": "Lip sync generation timed out"
            }), 500
        except subprocess.CalledProcessError as e:
            print(f"[TTS] ✗ Rhubarb error: {e.stderr}")
            return jsonify({
                "success": False,
                "error": f"Rhubarb error: {e.stderr}",
                "suggestion": "Make sure rhubarb-lip-sync is installed and in PATH"
            }), 500
        except FileNotFoundError:
            print(f"[TTS] ✗ Rhubarb not found in PATH")
            return jsonify({
                "success": False,
                "error": "rhubarb-lip-sync not found",
                "suggestion": "Install rhubarb-lip-sync and add to PATH. See RHUBARB_SETUP.md"
            }), 500

        print(f"{'='*60}\n")

        return jsonify({
            "success": True,
            "audio_url": f"/audio/{audio_filename}",
            "visemes": viseme_data,
            "cached": False
        })

    except Exception as e:
        print(f"[TTS] ✗ Exception: {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*60}\n")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/register', methods=['POST'])
def register_face():
    """
    Register face images to CodeProject.AI
    Expects JSON: {
        "name": "John Doe",
        "photos": ["data:image/jpeg;base64,...", ...]
    }
    """
    try:
        print(f"\n{'='*60}")
        print(f"[REGISTER] New registration request at {datetime.now().strftime('%H:%M:%S')}")

        data = request.get_json()
        name = data.get('name')
        photos = data.get('photos', [])

        print(f"[REGISTER] User: {name}")
        print(f"[REGISTER] Photos to register: {len(photos)}")

        if not name:
            print(f"[REGISTER] ERROR: Name is required")
            return jsonify({"success": False, "error": "Name is required"}), 400

        if not photos or len(photos) == 0:
            print(f"[REGISTER] ERROR: No photos provided")
            return jsonify({"success": False, "error": "At least one photo is required"}), 400

        # Register each photo with CodeProject.AI
        successful_registrations = 0
        errors = []

        for idx, photo_data in enumerate(photos):
            try:
                print(f"[REGISTER] Processing photo {idx+1}/{len(photos)}")

                # Extract base64 data from data URL
                if ',' in photo_data:
                    photo_data = photo_data.split(',')[1]

                # Decode base64 image
                image_bytes = base64.b64decode(photo_data)
                image_size_kb = len(image_bytes) / 1024
                print(f"[REGISTER]   Image size: {image_size_kb:.2f} KB")

                # Save locally for backup
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{name.replace(' ', '_')}_{timestamp}_{idx}.jpg"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                with open(filepath, 'wb') as f:
                    f.write(image_bytes)
                print(f"[REGISTER]   Saved locally: {filename}")

                # Register with CodeProject.AI
                files = {
                    'image': (filename, BytesIO(image_bytes), 'image/jpeg')
                }
                params = {
                    'userid': name
                }

                print(f"[REGISTER]   Sending to CodeProject.AI...")
                print(f"[REGISTER]   URL: {CODEPROJECT_BASE_URL}/vision/face/register")
                print(f"[REGISTER]   Timeout: 60 seconds")

                import time
                request_start = time.time()

                response = requests.post(
                    f"{CODEPROJECT_BASE_URL}/vision/face/register",
                    files=files,
                    data=params,
                    timeout=60
                )

                request_time = time.time() - request_start
                print(f"[REGISTER]   Response received in {request_time:.2f} seconds")
                print(f"[REGISTER]   Response status: {response.status_code}")

                if response.status_code == 200:
                    result = response.json()
                    print(f"[REGISTER]   Result: {result}")
                    if result.get('success'):
                        successful_registrations += 1
                        print(f"[REGISTER]   ✓ Photo {idx+1} registered successfully")
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        errors.append(f"Photo {idx+1}: {error_msg}")
                        print(f"[REGISTER]   ✗ Photo {idx+1} failed: {error_msg}")
                else:
                    errors.append(f"Photo {idx+1}: HTTP {response.status_code}")
                    print(f"[REGISTER]   ✗ Photo {idx+1} failed with status {response.status_code}")

            except requests.exceptions.Timeout as e:
                error_msg = f"Timeout after 60 seconds"
                errors.append(f"Photo {idx+1}: {error_msg}")
                print(f"[REGISTER]   ✗ Photo {idx+1} TIMEOUT: {e}")
                print(f"[REGISTER]   ⚠ CodeProject.AI is not responding - check if face module is loaded")
            except requests.exceptions.ConnectionError as e:
                error_msg = f"Connection error"
                errors.append(f"Photo {idx+1}: {error_msg}")
                print(f"[REGISTER]   ✗ Photo {idx+1} CONNECTION ERROR: {e}")
            except Exception as e:
                errors.append(f"Photo {idx+1}: {str(e)}")
                print(f"[REGISTER]   ✗ Photo {idx+1} exception: {e}")

        # Return results
        print(f"[REGISTER] Registration complete: {successful_registrations}/{len(photos)} successful")

        if successful_registrations > 0:
            # Create profile photo from the front-facing image (index 1)
            profile_photo_path = None
            try:
                print(f"[REGISTER] Creating profile photo...")

                # Use photo index 1 (the "Look straight ahead" / "Front" capture)
                profile_photo_idx = min(1, len(photos) - 1)  # Use index 1 if available, else 0
                profile_photo_data = photos[profile_photo_idx]

                # Extract base64 data
                if ',' in profile_photo_data:
                    profile_photo_data = profile_photo_data.split(',')[1]

                profile_image_bytes = base64.b64decode(profile_photo_data)

                # Detect face in the image to get bounding box
                print(f"[REGISTER] Detecting face for cropping...")
                files = {
                    'image': ('profile.jpg', BytesIO(profile_image_bytes), 'image/jpeg')
                }

                detect_response = requests.post(
                    f"{CODEPROJECT_BASE_URL}/vision/face/recognize",
                    files=files,
                    timeout=30
                )

                if detect_response.status_code == 200:
                    detect_result = detect_response.json()
                    predictions = detect_result.get('predictions', [])

                    if predictions:
                        # Get the first detected face
                        face = predictions[0]
                        x_min = int(face.get('x_min', 0))
                        y_min = int(face.get('y_min', 0))
                        x_max = int(face.get('x_max', 0))
                        y_max = int(face.get('y_max', 0))

                        print(f"[REGISTER] Face detected at: ({x_min}, {y_min}) to ({x_max}, {y_max})")

                        # Crop the image with some padding
                        img = Image.open(BytesIO(profile_image_bytes))
                        width, height = img.size

                        # Add 30% padding around the face
                        padding_x = int((x_max - x_min) * 0.3)
                        padding_y = int((y_max - y_min) * 0.3)

                        crop_x_min = max(0, x_min - padding_x)
                        crop_y_min = max(0, y_min - padding_y)
                        crop_x_max = min(width, x_max + padding_x)
                        crop_y_max = min(height, y_max + padding_y)

                        print(f"[REGISTER] Cropping with padding: ({crop_x_min}, {crop_y_min}) to ({crop_x_max}, {crop_y_max})")

                        # Crop the image
                        cropped_img = img.crop((crop_x_min, crop_y_min, crop_x_max, crop_y_max))

                        # Save profile photo
                        userid = name.replace(' ', '_').lower()
                        profile_filename = f"{userid}_profile.jpg"
                        profile_photo_path = os.path.join(UPLOAD_FOLDER, profile_filename)
                        cropped_img.save(profile_photo_path, 'JPEG', quality=90)

                        print(f"[REGISTER] ✓ Profile photo saved: {profile_filename}")
                    else:
                        print(f"[REGISTER] ⚠ No face detected for cropping, using original image")
                        # Save uncropped version
                        userid = name.replace(' ', '_').lower()
                        profile_filename = f"{userid}_profile.jpg"
                        profile_photo_path = os.path.join(UPLOAD_FOLDER, profile_filename)
                        with open(profile_photo_path, 'wb') as f:
                            f.write(profile_image_bytes)
                else:
                    print(f"[REGISTER] ⚠ Face detection failed, using original image")
                    # Save uncropped version
                    userid = name.replace(' ', '_').lower()
                    profile_filename = f"{userid}_profile.jpg"
                    profile_photo_path = os.path.join(UPLOAD_FOLDER, profile_filename)
                    with open(profile_photo_path, 'wb') as f:
                        f.write(profile_image_bytes)

                # Add user to database
                if profile_photo_path:
                    userid = name.replace(' ', '_').lower()
                    success, message = add_user(userid, name, profile_photo_path, source="manual")
                    if success:
                        print(f"[REGISTER] ✓ User added to database")
                    else:
                        print(f"[REGISTER] ⚠ Could not add to database: {message}")

            except Exception as e:
                print(f"[REGISTER] ⚠ Error creating profile photo: {e}")
                import traceback
                traceback.print_exc()

        print(f"{'='*60}\n")

        if successful_registrations > 0:
            return jsonify({
                "success": True,
                "message": f"Successfully registered {successful_registrations} out of {len(photos)} photos for {name}",
                "registered_count": successful_registrations,
                "total_count": len(photos),
                "errors": errors if errors else None
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to register any photos",
                "details": errors
            }), 500

    except Exception as e:
        print(f"[REGISTER] ✗ EXCEPTION: {e}")
        import traceback
        print(f"[REGISTER] Traceback:\n{traceback.format_exc()}")
        print(f"{'='*60}\n")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/recognize', methods=['POST'])
def recognize_face():
    """
    Recognize face in image using CodeProject.AI
    Expects JSON: {
        "image": "data:image/jpeg;base64,..."
    }
    """
    import time
    start_time = time.time()

    try:
        print(f"\n{'='*60}")
        print(f"[RECOGNIZE] New recognition request at {datetime.now().strftime('%H:%M:%S')}")

        data = request.get_json()
        image_data = data.get('image')

        if not image_data:
            print("[RECOGNIZE] ERROR: No image data in request")
            return jsonify({"success": False, "error": "Image is required"}), 400

        # Extract base64 data from data URL
        if ',' in image_data:
            image_data = image_data.split(',')[1]

        print(f"[RECOGNIZE] Base64 data length: {len(image_data)} characters")

        # Decode base64 image
        image_bytes = base64.b64decode(image_data)
        image_size_kb = len(image_bytes) / 1024
        print(f"[RECOGNIZE] Original image size: {image_size_kb:.2f} KB")

        # Resize image if needed to speed up processing
        image_bytes = resize_image_if_needed(image_bytes)
        final_size_kb = len(image_bytes) / 1024
        print(f"[RECOGNIZE] Final image size: {final_size_kb:.2f} KB")

        # Send to CodeProject.AI for recognition
        files = {
            'image': ('frame.jpg', BytesIO(image_bytes), 'image/jpeg')
        }

        url = f"{CODEPROJECT_BASE_URL}/vision/face/recognize"
        print(f"[RECOGNIZE] Sending POST to: {url}")
        print(f"[RECOGNIZE] Timeout set to: 30 seconds")

        request_start = time.time()
        response = requests.post(
            url,
            files=files,
            timeout=30
        )
        request_time = time.time() - request_start
        print(f"[RECOGNIZE] Response received in {request_time:.2f} seconds")
        print(f"[RECOGNIZE] Status code: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"[RECOGNIZE] Response JSON: {result}")

            # Extract face recognition results
            predictions = result.get('predictions', [])
            print(f"[RECOGNIZE] Found {len(predictions)} face prediction(s)")

            if predictions:
                # Get the best match (highest confidence)
                recognized_faces = []
                for idx, pred in enumerate(predictions):
                    userid = pred.get('userid', 'unknown')
                    confidence = pred.get('confidence', 0)
                    print(f"[RECOGNIZE]   Face #{idx+1}: {userid} (confidence: {confidence:.2%})")

                    recognized_faces.append({
                        "userid": userid,
                        "confidence": confidence,
                        "x_min": pred.get('x_min', 0),
                        "y_min": pred.get('y_min', 0),
                        "x_max": pred.get('x_max', 0),
                        "y_max": pred.get('y_max', 0)
                    })

                total_time = time.time() - start_time
                print(f"[RECOGNIZE] ✓ SUCCESS - Total time: {total_time:.2f}s")
                print(f"{'='*60}\n")

                return jsonify({
                    "success": True,
                    "faces": recognized_faces,
                    "count": len(recognized_faces)
                })
            else:
                print(f"[RECOGNIZE] No faces detected in image")
                total_time = time.time() - start_time
                print(f"[RECOGNIZE] ✓ Complete - Total time: {total_time:.2f}s")
                print(f"{'='*60}\n")

                return jsonify({
                    "success": True,
                    "faces": [],
                    "count": 0,
                    "message": "No faces detected"
                })
        else:
            print(f"[RECOGNIZE] ERROR: CodeProject.AI returned status {response.status_code}")
            try:
                error_body = response.text
                print(f"[RECOGNIZE] Response body: {error_body}")
            except:
                pass
            print(f"{'='*60}\n")

            return jsonify({
                "success": False,
                "error": f"CodeProject.AI returned status {response.status_code}"
            }), 500

    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        print(f"[RECOGNIZE] ✗ TIMEOUT after {elapsed:.2f} seconds")
        print(f"[RECOGNIZE] CodeProject.AI did not respond within 30 seconds")
        print(f"[RECOGNIZE] URL: {CODEPROJECT_BASE_URL}/vision/face/recognize")
        print(f"{'='*60}\n")
        return jsonify({
            "success": False,
            "error": "Request to CodeProject.AI timed out (30s)",
            "suggestion": "CodeProject.AI may be processing slowly. Try again or check server load."
        }), 504
    except requests.exceptions.ConnectionError as e:
        elapsed = time.time() - start_time
        print(f"[RECOGNIZE] ✗ CONNECTION ERROR after {elapsed:.2f} seconds")
        print(f"[RECOGNIZE] Cannot connect to CodeProject.AI: {e}")
        print(f"[RECOGNIZE] URL: {CODEPROJECT_BASE_URL}/vision/face/recognize")
        print(f"{'='*60}\n")
        return jsonify({
            "success": False,
            "error": "Cannot connect to CodeProject.AI",
            "suggestion": "Verify CodeProject.AI is running at 172.16.1.150:32168"
        }), 503
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[RECOGNIZE] ✗ EXCEPTION after {elapsed:.2f} seconds")
        print(f"[RECOGNIZE] Error: {type(e).__name__}: {e}")
        import traceback
        print(f"[RECOGNIZE] Traceback:\n{traceback.format_exc()}")
        print(f"{'='*60}\n")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/list-faces', methods=['GET'])
def list_faces():
    """
    List all registered faces in CodeProject.AI
    """
    try:
        response = requests.get(
            f"{CODEPROJECT_BASE_URL}/vision/face/list",
            timeout=5
        )

        if response.status_code == 200:
            result = response.json()
            return jsonify(result)
        else:
            return jsonify({
                "success": False,
                "error": f"CodeProject.AI returned status {response.status_code}"
            }), 500

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/delete-face/<userid>', methods=['DELETE'])
def delete_face(userid):
    """
    Delete a registered face from CodeProject.AI
    """
    try:
        response = requests.post(
            f"{CODEPROJECT_BASE_URL}/vision/face/delete",
            data={'userid': userid},
            timeout=5
        )

        if response.status_code == 200:
            return jsonify({"success": True, "message": f"Deleted {userid}"})
        else:
            return jsonify({
                "success": False,
                "error": f"CodeProject.AI returned status {response.status_code}"
            }), 500

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/users', methods=['GET'])
def list_users():
    """Get list of all registered users"""
    try:
        users = load_users()
        return jsonify({"success": True, "users": users})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/users/linkedin', methods=['POST'])
def fetch_linkedin():
    """Fetch profile info from LinkedIn URL"""
    try:
        data = request.get_json()
        linkedin_url = data.get('url')

        if not linkedin_url:
            return jsonify({"success": False, "error": "LinkedIn URL is required"}), 400

        # Fetch profile
        profile, error = fetch_linkedin_profile(linkedin_url)

        if error:
            # Return generic user-friendly message instead of technical error
            print(f"[API] LinkedIn fetch failed: {error}")
            return jsonify({
                "success": False,
                "error": "Unable to create profile from LinkedIn. Please try again later or use manual upload."
            }), 400

        # Convert photo to base64 for preview
        photo_base64 = base64.b64encode(profile['photo_data']).decode('utf-8')

        return jsonify({
            "success": True,
            "name": profile['name'],
            "photo": f"data:image/jpeg;base64,{photo_base64}",
            "photo_url": profile['photo_url']
        })

    except Exception as e:
        print(f"[API] Error fetching LinkedIn: {e}")
        return jsonify({
            "success": False,
            "error": "Unable to create profile from LinkedIn. Please try again later or use manual upload."
        }), 500


@app.route('/api/users', methods=['POST'])
def create_user():
    """Register a new user with photo"""
    try:
        data = request.get_json()
        name = data.get('name')
        photo_data = data.get('photo')  # base64 encoded
        source = data.get('source', 'linkedin')

        if not name or not photo_data:
            return jsonify({"success": False, "error": "Name and photo are required"}), 400

        # Create userid from name
        userid = name.replace(' ', '_').lower()

        # Check if user already exists
        if get_user(userid):
            return jsonify({"success": False, "error": "User already exists"}), 400

        # Extract base64 data from data URL
        if ',' in photo_data:
            photo_data = photo_data.split(',')[1]

        # Decode base64 image
        image_bytes = base64.b64decode(photo_data)

        # Save locally
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{userid}_{timestamp}.jpg"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, 'wb') as f:
            f.write(image_bytes)

        print(f"[USER] Registering new user: {name} ({userid})")
        print(f"[USER] Photo saved: {filename}")

        # Register with CodeProject.AI
        files = {
            'image': (filename, BytesIO(image_bytes), 'image/jpeg')
        }
        params = {
            'userid': userid
        }

        response = requests.post(
            f"{CODEPROJECT_BASE_URL}/vision/face/register",
            files=files,
            data=params,
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                # Add to local database
                add_user(userid, name, filepath, source)
                print(f"[USER] ✓ User registered successfully")

                return jsonify({
                    "success": True,
                    "message": f"User {name} registered successfully",
                    "userid": userid
                })
            else:
                error = result.get('error', 'Unknown error')
                print(f"[USER] ✗ CodeProject.AI error: {error}")
                return jsonify({"success": False, "error": error}), 500
        else:
            print(f"[USER] ✗ CodeProject.AI returned status {response.status_code}")
            return jsonify({
                "success": False,
                "error": f"CodeProject.AI returned status {response.status_code}"
            }), 500

    except Exception as e:
        print(f"[USER] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/users/<userid>', methods=['DELETE'])
def delete_user_endpoint(userid):
    """Delete a user from both database and CodeProject.AI"""
    try:
        print(f"[USER] Deleting user: {userid}")

        # Get user info first
        user = get_user(userid)
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404

        # Delete from CodeProject.AI
        response = requests.post(
            f"{CODEPROJECT_BASE_URL}/vision/face/delete",
            data={'userid': userid},
            timeout=10
        )

        if response.status_code == 200:
            print(f"[USER] ✓ Deleted from CodeProject.AI")

            # Delete from local database
            delete_user(userid)

            # Delete photo file
            if user.get('photo_path') and os.path.exists(user['photo_path']):
                os.remove(user['photo_path'])
                print(f"[USER] ✓ Deleted photo file")

            print(f"[USER] ✓ User deleted successfully")

            return jsonify({
                "success": True,
                "message": f"User {userid} deleted successfully"
            })
        else:
            print(f"[USER] ✗ CodeProject.AI returned status {response.status_code}")
            return jsonify({
                "success": False,
                "error": f"Failed to delete from CodeProject.AI (status {response.status_code})"
            }), 500

    except Exception as e:
        print(f"[USER] ✗ Error deleting user: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/users/sync', methods=['POST'])
def sync_users_from_codeproject():
    """Sync users from CodeProject.AI to local database"""
    try:
        print(f"\n{'='*60}")
        print(f"[SYNC] Syncing users from CodeProject.AI")

        # Query CodeProject.AI for all registered faces
        response = requests.post(
            f"{CODEPROJECT_BASE_URL}/vision/face/list",
            timeout=10
        )

        print(f"[SYNC] CodeProject.AI response status: {response.status_code}")

        if response.status_code != 200:
            return jsonify({
                "success": False,
                "error": f"CodeProject.AI returned status {response.status_code}"
            }), 500

        result = response.json()
        print(f"[SYNC] Response data: {result}")

        # CodeProject.AI returns faces in different formats, try to handle both
        faces = []
        if 'faces' in result:
            faces = result['faces']
        elif isinstance(result, list):
            faces = result

        print(f"[SYNC] Found {len(faces)} faces in CodeProject.AI")

        local_users = load_users()
        existing_userids = {u['userid'] for u in local_users}

        added = 0
        skipped = 0
        updated = 0

        for face in faces:
            # Try to extract userid from different possible formats
            userid = face if isinstance(face, str) else face.get('userid') or face.get('name')

            if not userid:
                print(f"[SYNC] ⚠ Skipping face with no userid: {face}")
                continue

            print(f"[SYNC] Processing: {userid}")

            if userid in existing_userids:
                print(f"[SYNC]   Already in database, skipping")
                skipped += 1
            else:
                # Add to local database
                # Since we don't have the photo, we'll mark it as synced
                user_data = {
                    "userid": userid,
                    "name": userid.replace('_', ' ').title(),  # Convert userid to readable name
                    "photo_path": None,
                    "source": "synced",
                    "registered_at": datetime.now().isoformat(),
                    "photo_count": 1
                }
                local_users.append(user_data)
                added += 1
                print(f"[SYNC]   ✓ Added to database")

        # Save updated user list
        save_users(local_users)

        message = f"Sync complete: {added} added, {skipped} skipped, {len(faces)} total in CodeProject.AI"
        print(f"[SYNC] {message}")
        print(f"{'='*60}\n")

        return jsonify({
            "success": True,
            "message": message,
            "added": added,
            "skipped": skipped,
            "total": len(faces)
        })

    except requests.exceptions.Timeout:
        print(f"[SYNC] ✗ Timeout")
        return jsonify({
            "success": False,
            "error": "Request to CodeProject.AI timed out"
        }), 504
    except Exception as e:
        print(f"[SYNC] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/displays/register', methods=['POST'])
def register_display():
    """Register or update a display"""
    try:
        data = request.get_json()
        display_id = data.get('display_id')
        location = data.get('location', 'Unknown Location')
        capabilities = data.get('capabilities')

        if not display_id:
            return jsonify({"success": False, "error": "display_id is required"}), 400

        display, is_new = register_or_update_display(display_id, location, capabilities)

        print(f"[DISPLAY] {'Registered' if is_new else 'Updated'} display: {display_id} at {location}")

        return jsonify({
            "success": True,
            "message": f"Display {'registered' if is_new else 'updated'} successfully",
            "display": display,
            "is_new": is_new
        })

    except Exception as e:
        print(f"[DISPLAY] Error registering display: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/displays/recognize', methods=['POST'])
def display_recognize():
    """Handle face recognition from display"""
    import time
    start_time = time.time()

    try:
        data = request.get_json()
        display_id = data.get('display_id')
        location = data.get('location', 'Unknown')
        image_data = data.get('image')

        if not display_id or not image_data:
            return jsonify({"success": False, "error": "display_id and image are required"}), 400

        print(f"\n[DISPLAY-REC] Recognition request from {display_id} ({location})")

        # Extract base64 data from data URL
        if ',' in image_data:
            image_data = image_data.split(',')[1]

        # Decode base64 image
        image_bytes = base64.b64decode(image_data)

        # Resize image if needed
        image_bytes = resize_image_if_needed(image_bytes)

        # Send to CodeProject.AI for recognition
        files = {
            'image': ('frame.jpg', BytesIO(image_bytes), 'image/jpeg')
        }

        request_start = time.time()
        response = requests.post(
            f"{CODEPROJECT_BASE_URL}/vision/face/recognize",
            files=files,
            timeout=30
        )
        request_time = time.time() - request_start

        if response.status_code == 200:
            result = response.json()
            predictions = result.get('predictions', [])

            faces = []
            for pred in predictions:
                faces.append({
                    "userid": pred.get('userid', 'unknown'),
                    "confidence": pred.get('confidence', 0),
                    "x_min": pred.get('x_min', 0),
                    "y_min": pred.get('y_min', 0),
                    "x_max": pred.get('x_max', 0),
                    "y_max": pred.get('y_max', 0)
                })

            # Update display with detection info
            if faces:
                update_display_detection(display_id, {"faces": faces})
                print(f"[DISPLAY-REC] Detected {len(faces)} face(s) in {request_time:.2f}s")
            else:
                # Still update last_seen even with no detections
                displays = load_displays()
                for display in displays:
                    if display['display_id'] == display_id:
                        display['last_seen'] = datetime.now().isoformat()
                        save_displays(displays)
                        break

            total_time = time.time() - start_time

            return jsonify({
                "success": True,
                "faces": faces,
                "count": len(faces),
                "processing_time": f"{total_time:.2f}s"
            })
        else:
            print(f"[DISPLAY-REC] CodeProject.AI error: {response.status_code}")
            return jsonify({
                "success": False,
                "error": f"CodeProject.AI returned status {response.status_code}"
            }), 500

    except Exception as e:
        print(f"[DISPLAY-REC] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/displays/heartbeat', methods=['POST'])
def display_heartbeat():
    """Update display last-seen timestamp"""
    try:
        data = request.get_json()
        display_id = data.get('display_id')
        location = data.get('location')

        if not display_id:
            return jsonify({"success": False, "error": "display_id is required"}), 400

        # Update last_seen timestamp
        displays = load_displays()
        for display in displays:
            if display['display_id'] == display_id:
                display['last_seen'] = datetime.now().isoformat()
                if location:
                    display['location'] = location
                save_displays(displays)
                return jsonify({"success": True, "message": "Heartbeat received"})

        # If display not found, register it
        register_or_update_display(display_id, location or 'Unknown Location')
        return jsonify({"success": True, "message": "Display registered via heartbeat"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/displays', methods=['GET'])
def list_displays():
    """Get list of all registered displays"""
    try:
        displays = load_displays()

        # Calculate online/offline status (offline if no heartbeat in last 2 minutes)
        now = datetime.now()
        for display in displays:
            last_seen = datetime.fromisoformat(display['last_seen'])
            time_diff = (now - last_seen).total_seconds()
            display['status'] = 'online' if time_diff < 120 else 'offline'
            display['time_since_seen'] = time_diff

        return jsonify({"success": True, "displays": displays})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/displays/<display_id>', methods=['DELETE'])
def delete_display(display_id):
    """Delete a display from the database"""
    try:
        print(f"[DISPLAY] Deleting display: {display_id}")

        # Load displays
        displays = load_displays()

        # Find display
        display_found = False
        for display in displays:
            if display['display_id'] == display_id:
                display_found = True
                break

        if not display_found:
            return jsonify({"success": False, "error": "Display not found"}), 404

        # Remove from list
        displays = [d for d in displays if d['display_id'] != display_id]

        # Save updated list
        save_displays(displays)

        print(f"[DISPLAY] ✓ Display deleted successfully")

        return jsonify({
            "success": True,
            "message": f"Display {display_id} deleted successfully"
        })

    except Exception as e:
        print(f"[DISPLAY] ✗ Error deleting display: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/health-check', methods=['GET'])
def health_check():
    """
    Check connectivity to CodeProject.AI server
    """
    try:
        # Try to ping CodeProject.AI base server
        base_url = f"http://{CODEPROJECT_HOST}:{CODEPROJECT_PORT}"
        print(f"[HEALTH] Testing connection to {base_url}")

        response = requests.get(base_url, timeout=10)

        # Any response (200, 404, 405, etc.) means server is alive
        if response.status_code in [200, 404, 405]:
            print(f"[HEALTH] ✓ Server responded with status {response.status_code}")
            return jsonify({
                "success": True,
                "message": "CodeProject.AI is reachable and responding",
                "status_code": response.status_code,
                "server": f"{CODEPROJECT_HOST}:{CODEPROJECT_PORT}",
                "endpoints": {
                    "register": f"{CODEPROJECT_BASE_URL}/vision/face/register",
                    "recognize": f"{CODEPROJECT_BASE_URL}/vision/face/recognize"
                }
            })
        else:
            print(f"[HEALTH] ⚠ Server responded with unexpected status {response.status_code}")
            return jsonify({
                "success": False,
                "message": f"CodeProject.AI responded with status {response.status_code}",
                "status_code": response.status_code,
                "server": f"{CODEPROJECT_HOST}:{CODEPROJECT_PORT}"
            })

    except requests.exceptions.Timeout:
        return jsonify({
            "success": False,
            "error": "Connection to CodeProject.AI timed out",
            "server": f"{CODEPROJECT_HOST}:{CODEPROJECT_PORT}",
            "suggestion": "Check if CodeProject.AI is running and accessible"
        }), 504

    except requests.exceptions.ConnectionError:
        return jsonify({
            "success": False,
            "error": "Cannot connect to CodeProject.AI",
            "server": f"{CODEPROJECT_HOST}:{CODEPROJECT_PORT}",
            "suggestion": "Verify the server address and port are correct"
        }), 503

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "server": f"{CODEPROJECT_HOST}:{CODEPROJECT_PORT}"
        }), 500


def test_codeproject_connection():
    """Test connection to CodeProject.AI on startup"""
    print(f"\n{'='*60}")
    print(f"[STARTUP] Testing CodeProject.AI connection...")
    print(f"[STARTUP] Server: {CODEPROJECT_BASE_URL}")

    try:
        # Try the base server first
        base_url = f"http://{CODEPROJECT_HOST}:{CODEPROJECT_PORT}"
        response = requests.get(base_url, timeout=10)

        if response.status_code in [200, 404, 405]:
            # Server is reachable (even 404/405 means server responded)
            print(f"[STARTUP] ✓ CodeProject.AI server is REACHABLE (status: {response.status_code})")
            print(f"[STARTUP] ✓ Face recognition endpoints should be available")
            print(f"[STARTUP]   Register: POST {CODEPROJECT_BASE_URL}/vision/face/register")
            print(f"[STARTUP]   Recognize: POST {CODEPROJECT_BASE_URL}/vision/face/recognize")
            print(f"{'='*60}\n")
            return True
        else:
            print(f"[STARTUP] ⚠ CodeProject.AI responded with status {response.status_code}")
            print(f"[STARTUP] ⚠ Face recognition may not work properly")
            print(f"{'='*60}\n")
            return False

    except requests.exceptions.Timeout:
        print(f"[STARTUP] ✗ Connection TIMEOUT")
        print(f"[STARTUP] ✗ CodeProject.AI did not respond within 10 seconds")
        print(f"[STARTUP] ⚠ Check if CodeProject.AI is running")
        print(f"{'='*60}\n")
        return False

    except requests.exceptions.ConnectionError as e:
        print(f"[STARTUP] ✗ CONNECTION FAILED")
        print(f"[STARTUP] ✗ Cannot reach {CODEPROJECT_BASE_URL}")
        print(f"[STARTUP] ✗ Error: {e}")
        print(f"[STARTUP] ⚠ Verify CodeProject.AI is running at {CODEPROJECT_HOST}:{CODEPROJECT_PORT}")
        print(f"{'='*60}\n")
        return False

    except Exception as e:
        print(f"[STARTUP] ✗ UNEXPECTED ERROR")
        print(f"[STARTUP] ✗ {type(e).__name__}: {e}")
        print(f"{'='*60}\n")
        return False


if __name__ == '__main__':
    print(f"\n{'*'*60}")
    print(f"*{' '*58}*")
    print(f"*  Face Recognition Server with CodeProject.AI{' '*12}*")
    print(f"*{' '*58}*")
    print(f"{'*'*60}\n")

    print(f"Configuration:")
    print(f"  CodeProject.AI: {CODEPROJECT_BASE_URL}")
    print(f"  Flask Server: http://localhost:5000")
    print(f"\nEndpoints:")
    print(f"  - Home:         http://localhost:5000/")
    print(f"  - Registration: http://localhost:5000/register")
    print(f"  - Recognition:  http://localhost:5000/recognize")
    print(f"  - Diagnostics:  http://localhost:5000/diagnostics")

    # Test CodeProject.AI connection
    test_codeproject_connection()

    print(f"Starting Flask server...")
    print(f"Press Ctrl+C to stop\n")

    app.run(debug=True, host='0.0.0.0', port=5000)
