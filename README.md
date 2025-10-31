# Face Recognition System with CodeProject.AI

A proof-of-concept face registration and recognition system using CodeProject.AI.

## Features

- **Video-based Registration**: Automated capture of face images from multiple angles
- **Real-time Recognition**: Continuous face recognition in camera feed
- **User-friendly Interface**: Clean web interface for both registration and recognition
- **CodeProject.AI Integration**: Leverages CodeProject.AI's face recognition capabilities

## Prerequisites

- Python 3.8 or higher
- CodeProject.AI server running (your instance: `172.16.1.150:32168`)
- Webcam
- Modern web browser with camera support (Chrome, Firefox, Edge)

## Installation

1. Create a virtual environment:

**Windows:**
```bash
python -m venv venv
```

**Linux/Mac:**
```bash
python3 -m venv venv
```

2. Activate the virtual environment:

**Windows:**
```bash
venv\Scripts\activate
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

4. Ensure CodeProject.AI is running and accessible at `172.16.1.150:32168`

## Running the Application

1. Ensure your virtual environment is activated (see Installation step 2)

2. Start the Flask server:
```bash
python app.py
```

3. Open your web browser and navigate to:
```
http://localhost:5000
```

## Usage

### Managing Users

The system provides two ways to register users:

#### Option 1: Manage Users (LinkedIn Integration - Recommended)

1. Click "Manage Users" on the home page
2. Enter a LinkedIn profile URL (e.g., https://www.linkedin.com/in/username)
3. Click "Fetch Profile" - the system will automatically extract:
   - Person's name
   - Profile photo
4. Review the preview to confirm the information is correct
5. Click "Confirm & Register" to add the user

**Features:**
- View all registered users in a table
- Delete users (removes from both database and CodeProject.AI)
- See registration date and source
- User photos displayed as thumbnails

**Note:** LinkedIn scraping may not work for all profiles due to LinkedIn's anti-scraping measures. For production use, consider using the LinkedIn API.

#### Option 2: Manual Registration (Video Capture)

1. Click "Register New Face" on the home page
2. Enter your full name
3. Click "Start Camera" to enable your webcam
4. Click "Begin Video Capture" to start the automated capture process
5. Follow the on-screen instructions to move your head to different angles
6. After capture completes, click "Submit to CodeProject.AI" to register your face

The system will automatically capture 6 images from different angles:
- Front
- Left angle
- Center
- Right angle
- Down angle
- Final center

### Running Face Recognition

1. Click "Start Recognition" on the home page
2. Click "Start Camera" to enable your webcam
3. Click "Start Recognition" to begin real-time face detection
4. The system will check for faces every 2 seconds
5. Recognized faces will be displayed with:
   - Person's name (if registered)
   - Confidence level (as percentage)
   - Bounding box on the video feed

## Project Structure

```
Facial Recognition/
├── app.py                      # Flask server with API endpoints
├── templates/
│   ├── index.html             # Home page
│   ├── register.html          # Manual registration page (video capture)
│   ├── recognize.html         # Real-time recognition page
│   ├── manage.html            # User management page (LinkedIn integration)
│   └── diagnostics.html       # System diagnostics page
├── uploads/                   # Local backup of captured images
├── users.json                 # User database
├── requirements.txt           # Python dependencies
├── test_codeproject.py        # CodeProject.AI connectivity test
└── README.md                  # This file
```

## API Endpoints

### User Management
- **GET /api/users** - List all registered users
- **POST /api/users** - Register a new user
  - Body: `{ "name": "John Doe", "photo": "base64...", "source": "linkedin" }`
- **POST /api/users/linkedin** - Fetch profile from LinkedIn URL
  - Body: `{ "url": "https://linkedin.com/in/username" }`
  - Returns: Name and photo for preview
- **DELETE /api/users/<userid>** - Delete user from database and CodeProject.AI

### Face Recognition
- **POST /api/register** - Register face images (manual video capture)
  - Body: `{ "name": "John Doe", "photos": ["base64...", ...] }`
- **POST /api/recognize** - Recognize faces in an image
  - Body: `{ "image": "base64..." }`
  - Returns: List of detected faces with names and confidence

### System
- **GET /api/health-check** - Check CodeProject.AI connectivity
- **GET /api/list-faces** - List registered faces in CodeProject.AI
- **DELETE /api/delete-face/<userid>** - Delete face from CodeProject.AI only

## Configuration

To change the CodeProject.AI server address, edit `app.py`:

```python
CODEPROJECT_HOST = "172.16.1.150"
CODEPROJECT_PORT = 32168
```

## Tips for Best Results

- **Lighting**: Use good, even lighting without harsh shadows
- **Distance**: Stay 1-2 feet from the camera
- **Multiple angles**: The registration process captures multiple angles automatically
- **Clear view**: Remove sunglasses; minimize glare on regular glasses
- **Stable position**: Hold steady during capture to avoid blur

## Troubleshooting

**Camera not working:**
- Ensure browser has camera permissions
- Check if another application is using the camera
- Try a different browser

**Registration fails:**
- Verify CodeProject.AI is running: `http://172.16.1.150:32168`
- Check network connectivity to CodeProject.AI server
- Ensure face is clearly visible and well-lit

**Recognition not detecting faces:**
- Ensure lighting is adequate
- Move closer to the camera
- Check if faces were properly registered

## Notes

- Captured images are backed up locally in the `uploads/` directory
- Recognition runs every 2 seconds to balance performance and responsiveness
- Multiple faces can be detected simultaneously
- Confidence threshold can be adjusted in the recognition logic if needed

## License

This is a proof-of-concept application for demonstration purposes.
