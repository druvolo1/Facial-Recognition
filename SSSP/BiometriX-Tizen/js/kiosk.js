// Configuration - Hard-coded for Tizen
const SERVER_URL = 'http://172.16.1.102:5000';
const WEBRTC_SERVER_URL = 'http://172.16.1.102:8080';
const REQUIRED_PHOTOS = 7;
const HEARTBEAT_INTERVAL = 15000; // 15 seconds

const POSITIONS = [
    { text: 'Look straight ahead', duration: 2000 },
    { text: 'Turn slightly to the left', duration: 2000 },
    { text: 'Turn slightly to the right', duration: 2000 },
    { text: 'Tilt your head slightly down', duration: 2000 },
    { text: 'Tilt your head slightly up', duration: 2000 },
    { text: 'Look straight ahead again', duration: 2000 },
    { text: 'Now take a profile photo - look straight and smile!', duration: 2000 }
];

// Get device information
const deviceId = localStorage.getItem('deviceId');
const deviceName = localStorage.getItem('deviceName');
const deviceType = localStorage.getItem('deviceType');
const deviceToken = localStorage.getItem('deviceToken');

// Validate device data
if (!deviceId || !deviceName || !deviceToken || deviceType !== 'registration_kiosk') {
    console.log('[KIOSK] Missing or invalid device data - redirecting to registration');
    localStorage.clear();
    window.location.href = 'index.html';
}

// State variables
let stream = null;
let peerConnection = null;
let websocket = null;
let capturedPhotos = [];
let currentPositionIndex = 0;
let capturing = false;
let audioEnabled = true;
let shiftActive = false;
let webrtcRetryTimeout = null;
let heartbeatInterval = null;

// DOM elements
const stepName = document.getElementById('step-name');
const stepCamera = document.getElementById('step-camera');
const stepSuccess = document.getElementById('step-success');

const personNameInput = document.getElementById('person-name');
const nameContinueBtn = document.getElementById('name-continue-btn');

const camera = document.getElementById('camera');
const guidanceIndicator = document.getElementById('guidanceIndicator');
const progressFill = document.getElementById('progressFill');
const beginBtn = document.getElementById('begin-btn');
const submitBtn = document.getElementById('submit-btn');
const audioToggle = document.getElementById('audio-toggle');
const alertContainer = document.getElementById('alert-container');

// Keyboard elements
const shiftKey = document.getElementById('shift-key');
const backspaceKey = document.getElementById('backspace-key');
const spaceKey = document.getElementById('space-key');
const keys = document.querySelectorAll('.key[data-key]');

// Show device info
document.getElementById('device-info').textContent = `Device: ${deviceName}`;

// Initialize on load
window.onload = init;

// Add Tizen key handler
document.addEventListener('keydown', function(e) {
    switch(e.keyCode){
    case 10009: // RETURN button
        tizen.application.getCurrentApplication().exit();
        break;
    default:
        console.log('Key code : ' + e.keyCode);
        break;
    }
});

async function init() {
    console.log('[KIOSK] Initializing kiosk interface');
    console.log('[KIOSK] Device:', deviceName, '(' + deviceId + ')');

    setupKeyboard();

    // Start periodic heartbeat
    await performHeartbeat();
    heartbeatInterval = setInterval(performHeartbeat, HEARTBEAT_INTERVAL);
}

async function performHeartbeat() {
    try {
        const response = await fetch(`${SERVER_URL}/api/devices/heartbeat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Device-ID': deviceId,
                'X-Device-Token': deviceToken
            }
        });

        if (!response.ok) {
            console.error('[HEARTBEAT] Failed:', response.status);
            return;
        }

        const data = await response.json();
        console.log('[HEARTBEAT] Success');

        // Check if device type changed - redirect to appropriate interface
        if (data.device_type && data.device_type !== deviceType) {
            console.log('[HEARTBEAT] Device type changed from', deviceType, 'to', data.device_type);
            localStorage.setItem('deviceType', data.device_type);
            localStorage.setItem('deviceName', data.device_name || deviceName);

            if (data.device_type === 'registration_kiosk') {
                window.location.href = 'kiosk.html';
            } else if (data.device_type === 'people_scanner') {
                window.location.href = 'scanner.html';
            } else if (data.device_type === 'location_dashboard') {
                window.location.href = 'dashboard.html';
            }
        }

    } catch (error) {
        console.error('[HEARTBEAT] Error:', error);
    }
}

// ================================================
// ON-SCREEN KEYBOARD
// ================================================
function setupKeyboard() {
    // Regular letter keys
    keys.forEach(key => {
        key.addEventListener('click', () => {
            const letter = key.getAttribute('data-key');
            const char = shiftActive ? letter : letter.toLowerCase();
            personNameInput.value += char;

            // Reset shift after one key press
            if (shiftActive) {
                shiftActive = false;
                shiftKey.classList.remove('active');
            }
        });
    });

    // Shift key
    shiftKey.addEventListener('click', () => {
        shiftActive = !shiftActive;
        shiftKey.classList.toggle('active', shiftActive);
    });

    // Backspace key
    backspaceKey.addEventListener('click', () => {
        personNameInput.value = personNameInput.value.slice(0, -1);
    });

    // Space key
    spaceKey.addEventListener('click', () => {
        personNameInput.value += ' ';
    });
}

// ================================================
// STEP NAVIGATION
// ================================================
nameContinueBtn.addEventListener('click', () => {
    const name = personNameInput.value.trim();
    if (!name) {
        showAlert('Please enter your name');
        return;
    }
    goToStep('camera');
    startWebRTC();
});

function goToStep(step) {
    document.querySelectorAll('.step').forEach(s => s.classList.remove('active'));

    if (step === 'name') {
        stepName.classList.add('active');
    } else if (step === 'camera') {
        stepCamera.classList.add('active');
    } else if (step === 'success') {
        stepSuccess.classList.add('active');
    }
}

// ================================================
// WEBRTC
// ================================================
async function startWebRTC() {
    console.log('========================================');
    console.log('[WebRTC] Starting WebRTC connection');
    console.log('[WebRTC] Server:', WEBRTC_SERVER_URL);
    console.log('========================================');

    try {
        // Request camera access
        const constraints = {
            video: {
                width: { ideal: 1280 },
                height: { ideal: 720 },
                facingMode: 'user'
            },
            audio: false
        };

        console.log('[Camera] Requesting camera access...');
        stream = await navigator.mediaDevices.getUserMedia(constraints);
        console.log('[Camera] ✓ Camera access granted');

        // Display video stream
        camera.srcObject = stream;

        // Create peer connection
        const configuration = {
            iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
        };

        peerConnection = new RTCPeerConnection(configuration);
        console.log('[WebRTC] Peer connection created');

        // Add stream tracks to peer connection with high quality encoding
        stream.getTracks().forEach(function(track) {
            const sender = peerConnection.addTrack(track, stream);
            console.log('[WebRTC] Added track:', track.kind);

            // Set high bitrate for better quality (especially for kiosk photo capture)
            if (track.kind === 'video') {
                try {
                    const params = sender.getParameters();
                    if (!params.encodings || params.encodings.length === 0) {
                        params.encodings = [{}];
                    }
                    // Set maximum bitrate for high quality (5 Mbps)
                    if (params.encodings && params.encodings[0]) {
                        params.encodings[0].maxBitrate = 5000000; // 5 Mbps
                        // Disable frame scaling for maximum resolution
                        params.encodings[0].scaleResolutionDownBy = 1.0;
                        sender.setParameters(params).then(() => {
                            console.log('[WebRTC] ✓ High quality encoding enabled (5 Mbps)');
                        }).catch(err => {
                            console.warn('[WebRTC] Could not set encoding parameters:', err);
                        });
                    } else {
                        console.warn('[WebRTC] Encodings not supported, using default quality');
                    }
                } catch (err) {
                    console.warn('[WebRTC] Could not configure encoding parameters:', err);
                }
            }
        });

        // Handle ICE candidates
        peerConnection.onicecandidate = function(event) {
            if (event.candidate) {
                console.log('[WebRTC] ICE candidate generated');
            } else {
                console.log('[WebRTC] All ICE candidates sent');
            }
        };

        // Handle connection state changes
        peerConnection.onconnectionstatechange = function() {
            console.log('[WebRTC] Connection state:', peerConnection.connectionState);

            if (peerConnection.connectionState === 'connected') {
                console.log('[WebRTC] ✓ Connection established - ready for capture');
            } else if (peerConnection.connectionState === 'failed' ||
                       peerConnection.connectionState === 'disconnected' ||
                       peerConnection.connectionState === 'closed') {
                console.warn('[WebRTC] Connection lost - will retry in 1 second...');

                // If we're in the middle of capturing, abort
                if (capturing) {
                    stopCapture();
                    showAlert('Connection lost during capture. Please try again.');
                }

                retryWebRTC();
            }
        };

        // Create and send offer
        await createAndSendOffer();

        // Connect WebSocket
        connectWebSocket();

    } catch (error) {
        console.error('[WebRTC] Failed to start:', error);
        showAlert('Connection failed - retrying automatically...');

        // Retry after 1 second
        retryWebRTC();
    }
}

async function createAndSendOffer() {
    try {
        console.log('[WebRTC] Creating offer...');
        const offer = await peerConnection.createOffer();
        await peerConnection.setLocalDescription(offer);
        console.log('[WebRTC] Local description set');

        // Send offer to server with device authentication
        const response = await fetch(`${WEBRTC_SERVER_URL}/webrtc/offer`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Device-ID': deviceId,
                'X-Device-Token': deviceToken
            },
            body: JSON.stringify({
                sdp: peerConnection.localDescription.sdp,
                type: peerConnection.localDescription.type,
                device_id: deviceId
            })
        });

        if (!response.ok) {
            throw new Error('Server returned ' + response.status);
        }

        const answer = await response.json();
        console.log('[WebRTC] Received answer from server');

        const remoteDesc = new RTCSessionDescription(answer);
        await peerConnection.setRemoteDescription(remoteDesc);
        console.log('[WebRTC] ✓ Peer connection established');

    } catch (error) {
        console.error('[WebRTC] Signaling error:', error);
        throw error;
    }
}

function connectWebSocket() {
    console.log('[WebSocket] Connecting to:', WEBRTC_SERVER_URL + '/ws');

    websocket = new WebSocket('ws://' + WEBRTC_SERVER_URL.replace('http://', '') + '/ws');

    websocket.onopen = function() {
        console.log('[WebSocket] ✓ Connected - ready for capture commands');
    };

    websocket.onmessage = function(event) {
        try {
            const message = JSON.parse(event.data);

            if (message.type === 'capture_result') {
                handleCaptureResult(message.data);
            }
        } catch (e) {
            console.error('[WebSocket] Parse error:', e);
        }
    };

    websocket.onerror = function(error) {
        console.error('[WebSocket] Error:', error);
    };

    websocket.onclose = function() {
        console.log('[WebSocket] Connection closed');
        if (capturing) {
            showAlert('Connection lost - please try again');
            stopCapture();
        }
    };
}

// ================================================
// CAPTURE PROCESS
// ================================================
beginBtn.addEventListener('click', async () => {
    beginBtn.disabled = true;
    await startCapture();
});

async function startCapture() {
    capturedPhotos = [];
    currentPositionIndex = 0;
    capturing = true;
    updateProgress();

    speak('Please follow the prompts');
    await delay(2000);

    for (let i = 0; i < POSITIONS.length; i++) {
        currentPositionIndex = i;
        const position = POSITIONS[i];

        showGuidance(position.text);
        speak(position.text);

        await delay(1000);

        // Send capture command to server
        await requestCapture(i);

        // Wait for server response (handled in handleCaptureResult)
        await delay(position.duration);

        hideGuidance();
    }

    capturing = false;
    hideGuidance();

    if (capturedPhotos.length >= REQUIRED_PHOTOS) {
        submitBtn.disabled = false;
        speak('Capture complete. Please press submit.');
    } else {
        showAlert('Failed to capture all photos. Please try again.');
        beginBtn.disabled = false;
    }
}

function requestCapture(index) {
    return new Promise((resolve) => {
        if (!websocket || websocket.readyState !== WebSocket.OPEN) {
            console.error('[CAPTURE] WebSocket not connected');
            resolve();
            return;
        }

        console.log(`[CAPTURE] Requesting capture ${index + 1}/${REQUIRED_PHOTOS}`);

        // Send capture command to server
        websocket.send(JSON.stringify({
            type: 'capture_frame',
            device_id: deviceId,
            frame_index: index
        }));

        // Resolve immediately - result will come via handleCaptureResult
        resolve();
    });
}

function handleCaptureResult(data) {
    console.log('[CAPTURE] Frame captured:', data.frame_index + 1);

    if (data.success && data.image) {
        capturedPhotos.push(data.image);
        updateProgress();
        console.log(`[CAPTURE] Progress: ${capturedPhotos.length}/${REQUIRED_PHOTOS}`);
    } else {
        console.error('[CAPTURE] Failed to capture frame', data.frame_index);
    }
}

function stopCapture() {
    capturing = false;
    hideGuidance();
    beginBtn.disabled = false;
    submitBtn.disabled = true;
}

function showGuidance(text) {
    guidanceIndicator.textContent = text;
    guidanceIndicator.classList.add('active');
}

function hideGuidance() {
    guidanceIndicator.classList.remove('active');
}

function updateProgress() {
    const progress = (capturedPhotos.length / REQUIRED_PHOTOS) * 100;
    progressFill.style.width = progress + '%';
}

// ================================================
// SUBMISSION
// ================================================
submitBtn.addEventListener('click', async () => {
    submitBtn.disabled = true;
    await submitRegistration();
});

async function submitRegistration() {
    const personName = personNameInput.value.trim();

    if (capturedPhotos.length < REQUIRED_PHOTOS) {
        showAlert(`Need ${REQUIRED_PHOTOS} photos, only have ${capturedPhotos.length}`);
        submitBtn.disabled = false;
        return;
    }

    try {
        console.log('[SUBMIT] Submitting registration for:', personName);

        // Separate training photos (first 6) from profile photo (7th)
        const trainingPhotos = capturedPhotos.slice(0, 6);
        const profilePhoto = capturedPhotos.length >= 7 ? capturedPhotos[6] : null;

        const response = await fetch(`${SERVER_URL}/api/devices/register-face`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Device-ID': deviceId,
                'X-Device-Token': deviceToken
            },
            body: JSON.stringify({
                device_id: deviceId,
                name: personName,
                photos: trainingPhotos,
                profile_photo: profilePhoto
            })
        });

        if (!response.ok) {
            // If device authentication failed, redirect
            if (response.status === 401 || response.status === 403) {
                console.log('[SUBMIT] Device authentication failed - redirecting');
                localStorage.removeItem('deviceToken');
                window.location.href = 'index.html';
                return;
            }
            throw new Error(`HTTP ${response.status}`);
        }

        const result = await response.json();

        if (result.success) {
            console.log('[SUBMIT] ✓ Registration successful');
            stopCamera();
            goToStep('success');
            speak('Successfully submitted');

            // Return to name entry after 3 seconds
            setTimeout(() => {
                resetForm();
                goToStep('name');
                // Re-establish WebRTC for next registration
            }, 3000);
        } else {
            showAlert('Registration failed: ' + (result.message || 'Unknown error'));
            submitBtn.disabled = false;
        }
    } catch (error) {
        console.error('[SUBMIT] Error:', error);
        showAlert('Error submitting registration. Please try again.');
        submitBtn.disabled = false;
    }
}

function resetForm() {
    personNameInput.value = '';
    capturedPhotos = [];
    currentPositionIndex = 0;
    capturing = false;
    updateProgress();
    submitBtn.disabled = true;
    beginBtn.disabled = false;
    alertContainer.innerHTML = '';
}

// ================================================
// CAMERA CONTROL
// ================================================
function stopCamera() {
    if (websocket) {
        websocket.close();
        websocket = null;
    }
    if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
    }
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        camera.srcObject = null;
        stream = null;
    }
}

// ================================================
// AUDIO
// ================================================
function speak(text) {
    if (!audioEnabled) return;

    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.9;
        utterance.pitch = 1;
        speechSynthesis.speak(utterance);
    }
}

audioToggle.addEventListener('click', () => {
    audioEnabled = !audioEnabled;
    audioToggle.classList.toggle('muted', !audioEnabled);
    audioToggle.textContent = audioEnabled ? '🔊' : '🔇';
});

// ================================================
// UTILITIES
// ================================================
function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function showAlert(message) {
    alertContainer.innerHTML = `<div class="alert">${message}</div>`;
    setTimeout(() => {
        alertContainer.innerHTML = '';
    }, 5000);
}

function cleanupWebRTC() {
    console.log('[WebRTC] Cleaning up connection...');

    // Clear any pending retry
    if (webrtcRetryTimeout) {
        clearTimeout(webrtcRetryTimeout);
        webrtcRetryTimeout = null;
    }

    // Close WebSocket
    if (websocket) {
        websocket.close();
        websocket = null;
    }

    // Close peer connection
    if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
    }

    // Note: We keep the stream alive for retry
    console.log('[WebRTC] Cleanup complete');
}

function retryWebRTC() {
    // Clear any existing retry timeout
    if (webrtcRetryTimeout) {
        clearTimeout(webrtcRetryTimeout);
    }

    // Clean up the failed connection
    cleanupWebRTC();

    // Retry after 1 second
    console.log('[WebRTC] Scheduling retry in 1 second...');
    webrtcRetryTimeout = setTimeout(async function() {
        console.log('[WebRTC] Retrying connection...');
        try {
            await startWebRTC();
        } catch (error) {
            console.error('[WebRTC] Retry failed:', error);
            // Will automatically retry again due to connection state change
        }
    }, 1000);
}

// Cleanup on unload
window.addEventListener('beforeunload', () => {
    if (heartbeatInterval) {
        clearInterval(heartbeatInterval);
    }
    if (webrtcRetryTimeout) {
        clearTimeout(webrtcRetryTimeout);
    }
    stopCamera();
});
