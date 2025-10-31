# Samsung SSSP Face Recognition App

This is a Samsung Smart Signage Platform (SSSP) application that runs on Samsung Tizen commercial displays and provides real-time face recognition monitoring.

## Features

- **WebRTC Camera Access**: Captures video from display's built-in camera or USB webcam
- **Real-time Face Recognition**: Sends frames to CodeProject.AI every 3 seconds for face recognition
- **Live Detection Display**: Shows bounding boxes and names over detected faces
- **Detection History**: Displays recent face detections with confidence scores
- **Server Connectivity**: Registers with central server and reports all detections
- **Heartbeat Monitoring**: Sends status updates every 30 seconds

## Prerequisites

- Samsung Tizen commercial display (SSSP 6.0 or higher recommended)
- USB webcam connected to the display (if no built-in camera)
- Network connectivity to your Flask server
- Flask server running with face recognition endpoints

## Installation

### 1. Configure the Application

Edit `index.html` and update the server configuration:

```javascript
const SERVER_URL = 'http://YOUR_SERVER_IP:5000'; // Change to your Flask server IP
```

### 2. Package the Application

Create a ZIP file containing:
- `config.xml`
- `index.html`
- `icon.png` (optional, create a 117x117 PNG icon)

**Package structure:**
```
FaceRecMonitor.zip
├── config.xml
├── index.html
└── icon.png (optional)
```

### 3. Deploy to Samsung Display

#### Option A: Using Samsung MagicInfo (Recommended)
1. Log into MagicInfo Server
2. Go to Content > HTML5
3. Upload the ZIP file
4. Publish to your display(s)
5. Set the app to run on startup if desired

#### Option B: Using Tizen Studio
1. Open Tizen Studio
2. Create new Web Application project
3. Replace files with SSSP app files
4. Build and package as `.wgt` file
5. Install on display via USB or network

#### Option C: Manual Installation via USB
1. Copy the ZIP file to a USB drive
2. Insert USB into the display
3. Navigate to Settings > General > External Device Manager
4. Select and install the HTML5 app

### 4. Set Display Location (Optional)

You can specify the location by adding a URL parameter when launching the app:

```
http://localhost/index.html?location=Main%20Entrance
```

Or in MagicInfo, set the URL parameters in the content settings.

## Configuration Options

### In `index.html`:

```javascript
// Server URL (REQUIRED)
const SERVER_URL = 'http://YOUR_SERVER_IP:5000';

// Recognition interval (milliseconds)
const RECOGNITION_INTERVAL = 3000; // Check every 3 seconds

// Maximum detection history to display
const MAX_DETECTION_HISTORY = 10;
```

### In `config.xml`:

Update the application metadata:

```xml
<widget id="http://yourdomain.com/FaceRecognitionMonitor">
    <name>Face Recognition Monitor</name>
    <description>Your description</description>
    <author email="your@email.com">Your Company</author>
</widget>
```

## Usage

### Automatic Startup

Once deployed, the app will:

1. **Initialize**: Get display information and generate unique display ID
2. **Register**: Connect to your Flask server and register itself
3. **Start Camera**: Request webcam access and start video feed
4. **Monitor**: Begin periodic face recognition (every 3 seconds)
5. **Report**: Send all detections back to the server for monitoring

### Display Information

The app shows:
- Display ID (unique identifier)
- Location name
- Connection status
- Live video feed with bounding boxes
- Recent face detections with timestamps and confidence scores

### Monitoring Dashboard

View all connected displays from your central dashboard:
```
http://YOUR_SERVER_IP:5000/monitor
```

The dashboard shows:
- All registered displays
- Online/offline status
- Location of each display
- Recent face detections
- Total detection counts
- Last seen timestamps

## Troubleshooting

### Camera Not Working

**Check permissions:**
- Tizen displays may require camera permissions to be granted
- Go to Settings > Security & Restrictions and allow camera access

**USB Camera:**
- Ensure USB camera is properly connected
- Some displays may not support all USB camera models
- Check display documentation for compatible cameras

### Cannot Connect to Server

**Check network:**
```bash
# On your server, ensure Flask is accessible
curl http://YOUR_SERVER_IP:5000/api/health-check
```

**Firewall:**
- Ensure port 5000 is open on your server
- Check display's network settings and gateway

**CORS Issues:**
- Flask app already includes CORS headers for display communication
- If issues persist, check browser console (if accessible)

### Display Shows "Registration Failed"

- Verify `SERVER_URL` in `index.html` is correct
- Check that Flask server is running
- Verify network connectivity
- Check Flask server logs for error messages

### No Faces Detected

- Ensure users are registered in the system first
- Check lighting conditions (need good, even lighting)
- Verify camera is properly positioned
- Test face recognition from the main web interface first

## API Endpoints Used

The SSSP app communicates with these Flask endpoints:

- `POST /api/displays/register` - Register display on startup
- `POST /api/displays/recognize` - Send frames for face recognition
- `POST /api/displays/heartbeat` - Send periodic status updates

## Display ID Generation

The app generates a unique display ID using:

1. **Tizen Device Info** (if available): Uses device model/serial
2. **LocalStorage Persistence**: Stores generated ID for consistency
3. **Fallback**: Generates ID from timestamp + random string

Format: `display_1634567890_abc123xyz`

## Development & Testing

### Test on PC Browser

You can test the SSSP app in a regular browser:

1. Update `SERVER_URL` to `http://localhost:5000`
2. Open `index.html` in Chrome/Firefox
3. Allow camera permissions
4. App will work similarly to on-display operation

Note: Tizen-specific APIs will not be available, so it will use fallback methods.

### Debug Mode

Open browser console (if accessible on display) to see:
- `[INIT]` - Initialization messages
- `[DISPLAY]` - Display registration status
- `[CAMERA]` - Camera access and status
- `[REGISTER]` - Server registration
- `[RECOGNITION]` - Face detection results
- `[HEARTBEAT]` - Connectivity status

## Performance Considerations

- **Recognition Interval**: 3 seconds balances responsiveness and server load
- **Image Resolution**: Default 1280x720, resized to 640x480 before sending
- **Network Bandwidth**: ~100-200 KB per recognition request
- **Display Resources**: Minimal CPU/memory usage, suitable for 24/7 operation

## Security Notes

- App requires camera permission
- All communication with server is over HTTP (consider HTTPS for production)
- Display ID is persistent but can be reset by clearing app data
- No sensitive data is stored locally

## Support

For issues or questions:
- Check Flask server logs for errors
- View browser console on display (if accessible)
- Verify all prerequisites are met
- Test individual components (camera, network, recognition)

## License

This is a proof-of-concept application for demonstration purposes.
