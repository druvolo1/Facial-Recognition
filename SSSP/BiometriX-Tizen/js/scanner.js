// Configuration - Hard-coded for Tizen
const SERVER_URL = 'http://172.16.1.102:5000';
const MAX_RECENT_SCANS = 10;
const HEARTBEAT_INTERVAL = 15000; // 15 seconds

// Get device information
const deviceId = localStorage.getItem('deviceId');
const deviceName = localStorage.getItem('deviceName');
const deviceType = localStorage.getItem('deviceType');
const deviceToken = localStorage.getItem('deviceToken');

// Validate device data
if (!deviceId || !deviceName || !deviceToken || deviceType !== 'people_scanner') {
    console.log('[SCANNER] Missing or invalid device data - redirecting to registration');
    localStorage.clear();
    window.location.href = 'index.html';
}

// DOM elements
const video = document.getElementById('camera');
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const statusBadge = document.getElementById('status-badge');

const cameraStatus = document.getElementById('cameraStatus');
const webrtcStatus = document.getElementById('webrtcStatus');
const recognitionStatus = document.getElementById('recognitionStatus');
const relayName = document.getElementById('relayName');
const relayUrl = document.getElementById('relayUrl');
const faceCount = document.getElementById('faceCount');
const lastCheck = document.getElementById('lastCheck');
const currentFacesList = document.getElementById('current-faces-list');
const recentScansList = document.getElementById('recent-scans-list');

// State variables
let stream = null;
let peerConnection = null;
let websocket = null;
let recentScans = [];
let webrtcRetryTimeout = null;
let heartbeatInterval = null;
let personNameCache = {}; // Cache userid -> person name mapping
let currentRelayUrl = null;
let currentRelayName = null;

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
    console.log('[SCANNER] Initializing scanner interface');
    console.log('[SCANNER] Device:', deviceName, '(' + deviceId + ')');

    try {
        // Fetch device configuration and relay info via heartbeat
        await performHeartbeat();

        // Start periodic heartbeat
        heartbeatInterval = setInterval(performHeartbeat, HEARTBEAT_INTERVAL);
    } catch (error) {
        console.error('[SCANNER] Initialization failed:', error);
        updateStatusBadge('Error: ' + error.message, false);
    }
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
        console.log('[HEARTBEAT] Received config:', data);

        // Check if device type changed - redirect to appropriate interface
        if (data.device_type && data.device_type !== deviceType) {
            console.log('[HEARTBEAT] Device type changed from', deviceType, 'to', data.device_type);
            console.log('[HEARTBEAT] Redirecting to appropriate interface...');

            // Update localStorage
            localStorage.setItem('deviceType', data.device_type);
            localStorage.setItem('deviceName', data.device_name || deviceName);

            // Redirect to appropriate interface
            if (data.device_type === 'registration_kiosk') {
                window.location.href = 'kiosk.html';
            } else if (data.device_type === 'people_scanner') {
                window.location.href = 'scanner.html';
            } else if (data.device_type === 'location_dashboard') {
                window.location.href = 'dashboard.html';
            }
            return;
        }

        // Check if relay has changed
        const newRelayUrl = data.webrtc_relay_url;
        const newRelayName = data.webrtc_relay_name;

        if (newRelayUrl !== currentRelayUrl || newRelayName !== currentRelayName) {
            console.log('[HEARTBEAT] Relay changed:', { old: currentRelayUrl, new: newRelayUrl });

            // Update relay info
            currentRelayUrl = newRelayUrl;
            currentRelayName = newRelayName;

            // Update display
            if (newRelayName) {
                relayName.textContent = newRelayName;
                relayUrl.textContent = newRelayUrl || 'Not configured';
            } else {
                relayName.textContent = 'Not configured';
                relayUrl.textContent = 'Not configured';
            }

            // Stop existing WebRTC if running
            if (peerConnection || websocket) {
                console.log('[HEARTBEAT] Stopping existing WebRTC connection...');
                cleanupWebRTC();
            }

            // Start WebRTC with new relay (or skip if no relay)
            if (newRelayUrl) {
                console.log('[HEARTBEAT] Starting WebRTC with relay:', newRelayUrl);
                await startWebRTC();
            } else {
                console.log('[HEARTBEAT] No relay configured - WebRTC disabled');
                updateStatusBadge('No WebRTC relay configured', false);
                webrtcStatus.textContent = 'No relay';
                webrtcStatus.classList.remove('active');
                webrtcStatus.classList.add('inactive');
            }
        }

    } catch (error) {
        console.error('[HEARTBEAT] Error:', error);
    }
}

async function startWebRTC() {
    console.log('========================================');
    console.log('[WebRTC] Starting WebRTC connection');
    console.log('[WebRTC] Relay:', currentRelayUrl);
    console.log('========================================');

    if (!currentRelayUrl) {
        console.error('[WebRTC] No relay URL configured');
        updateStatusBadge('No WebRTC relay configured', false);
        return;
    }

    try {
        updateStatusBadge('Requesting camera access...', true);

        // Request camera access with higher resolution for better recognition
        const constraints = {
            video: {
                width: { ideal: 1280 },
                height: { ideal: 720 }
            },
            audio: false
        };

        console.log('[Camera] Requesting camera access...');
        stream = await navigator.mediaDevices.getUserMedia(constraints);
        console.log('[Camera] ✓ Camera access granted');

        // Display video stream (Option B - native video element)
        video.srcObject = stream;

        // Wait for video to load to set canvas size
        video.onloadedmetadata = () => {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            console.log('[Camera] Video dimensions:', video.videoWidth, 'x', video.videoHeight);
        };

        cameraStatus.textContent = 'Active';
        cameraStatus.classList.remove('inactive');
        cameraStatus.classList.add('active');

        updateStatusBadge('Establishing WebRTC connection...', true);

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

            // Set high bitrate for better quality facial recognition
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
                webrtcStatus.textContent = 'Connected';
                webrtcStatus.classList.remove('inactive');
                webrtcStatus.classList.add('active');
                updateStatusBadge('Recognition active', true, true);

                recognitionStatus.innerHTML = '<span class="recognition-active">ACTIVE</span>';
                recognitionStatus.classList.remove('inactive');
                recognitionStatus.classList.add('active');
            } else if (peerConnection.connectionState === 'failed' ||
                       peerConnection.connectionState === 'disconnected' ||
                       peerConnection.connectionState === 'closed') {
                console.warn('[WebRTC] Connection lost - will retry in 1 second...');
                webrtcStatus.textContent = 'Reconnecting...';
                webrtcStatus.classList.remove('active');
                webrtcStatus.classList.add('inactive');
                updateStatusBadge('Reconnecting...', true);
                retryWebRTC();
            }
        };

        // Create and send offer
        await createAndSendOffer();

        // Connect WebSocket for receiving recognition results
        connectWebSocket();

    } catch (error) {
        console.error('[WebRTC] Failed to start:', error);
        cameraStatus.textContent = 'Retrying...';
        cameraStatus.classList.add('inactive');
        updateStatusBadge('Connection failed - retrying in 1 second...', true);

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
        const response = await fetch(`${currentRelayUrl}/webrtc/offer`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Device-ID': deviceId,
                'X-Device-Token': deviceToken
            },
            body: JSON.stringify({
                sdp: peerConnection.localDescription.sdp,
                type: peerConnection.localDescription.type,
                device_id: deviceId  // Include device ID in offer
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

        webrtcStatus.textContent = 'Connected';
        webrtcStatus.classList.remove('inactive');
        webrtcStatus.classList.add('active');

    } catch (error) {
        console.error('[WebRTC] Signaling error:', error);
        throw error;
    }
}

function connectWebSocket() {
    console.log('[WebSocket] Connecting to:', currentRelayUrl + '/ws');

    const wsUrl = currentRelayUrl.replace('http://', 'ws://').replace('https://', 'wss://') + '/ws';
    websocket = new WebSocket(wsUrl);

    websocket.onopen = function() {
        console.log('[WebSocket] ✓ Connected');
    };

    websocket.onmessage = function(event) {
        try {
            const message = JSON.parse(event.data);

            if (message.type === 'recognition') {
                handleRecognitionResult(message.data);
            }
        } catch (e) {
            console.error('[WebSocket] Parse error:', e);
        }
    };

    websocket.onerror = function(error) {
        console.error('[WebSocket] Error:', error);
    };

    websocket.onclose = function() {
        console.log('[WebSocket] Connection closed, reconnecting in 3s...');
        recognitionStatus.textContent = 'Reconnecting...';
        recognitionStatus.classList.remove('active');
        recognitionStatus.classList.add('inactive');
        setTimeout(connectWebSocket, 3000);
    };
}

function formatUserIdAsName(userid) {
    // Convert "dave_ruvolo" or "dave-ruvolo" to "Dave Ruvolo"
    return userid
        .split(/[_-]/)
        .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
        .join(' ');
}

async function getPersonName(userid) {
    // Check cache first
    if (personNameCache[userid]) {
        return personNameCache[userid];
    }

    // If unknown, return as-is
    if (userid === 'unknown') {
        return 'Unknown Person';
    }

    // Try to fetch from backend
    try {
        const response = await fetch(`${SERVER_URL}/api/people/${encodeURIComponent(userid)}`, {
            headers: {
                'X-Device-ID': deviceId,
                'X-Device-Token': deviceToken
            }
        });

        if (response.ok) {
            const data = await response.json();
            const personName = data.name || formatUserIdAsName(userid);
            personNameCache[userid] = personName;
            console.log(`[Recognition] ✓ Mapped ${userid} -> ${personName}`);
            return personName;
        } else {
            // API doesn't exist or returned error - format the userid
            const formattedName = formatUserIdAsName(userid);
            personNameCache[userid] = formattedName;
            console.log(`[Recognition] API unavailable, formatted ${userid} -> ${formattedName}`);
            return formattedName;
        }
    } catch (error) {
        // Network error or API doesn't exist - format the userid
        const formattedName = formatUserIdAsName(userid);
        personNameCache[userid] = formattedName;
        console.log(`[Recognition] API error, formatted ${userid} -> ${formattedName}`);
        return formattedName;
    }
}

async function handleRecognitionResult(data) {
    console.log('[Recognition] Result received:', data);

    if (!data || !data.success) {
        console.log('[Recognition] No faces detected or error');
        // Clear bounding boxes and face list
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        currentFacesList.innerHTML = '<div class="no-faces">No faces detected in frame</div>';
        faceCount.textContent = '0';
        return;
    }

    const faces = data.faces || [];

    // If faces array is empty, clear display
    if (faces.length === 0) {
        console.log('[Recognition] No faces in frame');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        currentFacesList.innerHTML = '<div class="no-faces">No faces detected in frame</div>';
        faceCount.textContent = '0';
        return;
    }

    // Update last check time
    const now = new Date();
    lastCheck.textContent = now.toLocaleTimeString();

    // Update face count
    faceCount.textContent = faces.length;

    console.log('[Recognition] Faces detected:', faces.length);
    if (faces.length > 0) {
        faces.forEach((face, i) => {
            const displayName = face.person_name || face.userid;
            console.log(`[Recognition]  ${i + 1}. ${displayName} (${(face.confidence * 100).toFixed(1)}%)`);
        });
    }

    // Enrich faces with names if not already provided by server
    const facesWithNames = await Promise.all(faces.map(async (face) => {
        // If server already provided person_name, use it
        if (face.person_name) {
            return { ...face, personName: face.person_name };
        }
        // Otherwise fetch it
        const personName = await getPersonName(face.userid);
        return { ...face, personName };
    }));

    // Display current frame faces
    displayCurrentFaces(facesWithNames);

    // Draw bounding boxes on canvas overlay
    drawBoundingBoxes(facesWithNames);

    // Add recognized faces to recent scans
    facesWithNames.forEach(face => {
        if (face.userid !== 'unknown') {
            addToRecentScans(face.personName, face.confidence);
        }
    });

    // Send detections to server so dashboards can see them
    await reportDetectionsToServer(facesWithNames);
}

async function reportDetectionsToServer(faces) {
    try {
        // Only report recognized faces (not unknown)
        const recognizedFaces = faces.filter(face => {
            const userid = face.userid;
            // Filter out unknown faces (various forms)
            return userid &&
                   userid !== 'unknown' &&
                   userid.toLowerCase() !== 'unknown' &&
                   !userid.toLowerCase().includes('unknown');
        });

        if (recognizedFaces.length === 0) {
            console.log('[Report] No recognized faces to report (all unknown)');
            return; // Nothing to report
        }

        console.log(`[Report] Sending ${recognizedFaces.length} recognized faces to server (filtered out ${faces.length - recognizedFaces.length} unknown)`);

        const response = await fetch(`${SERVER_URL}/api/devices/log-scan`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Device-ID': deviceId,
                'X-Device-Token': deviceToken
            },
            body: JSON.stringify({
                detections: recognizedFaces.map(face => ({
                    person_name: face.userid,  // Send person_id (UUID) in person_name field
                    confidence: face.confidence
                }))
            })
        });

        if (response.ok) {
            console.log('[Report] ✓ Detections reported to server');
        } else {
            console.error('[Report] Failed to report detections:', response.status);
        }
    } catch (error) {
        console.error('[Report] Error reporting detections:', error);
    }
}

function displayCurrentFaces(faces) {
    if (faces.length === 0) {
        currentFacesList.innerHTML = '<div class="no-faces">No faces detected in frame</div>';
        return;
    }

    currentFacesList.innerHTML = '';

    faces.forEach((face, index) => {
        const faceCard = document.createElement('div');
        faceCard.className = 'face-card';

        const confidencePercent = (face.confidence * 100).toFixed(1);
        const userName = face.personName || face.userid || 'Unknown Person';

        faceCard.innerHTML = `
            <div class="face-info">
                <h4>${userName}</h4>
                <p>Face #${index + 1}</p>
            </div>
            <div class="confidence-badge">${confidencePercent}%</div>
        `;

        currentFacesList.appendChild(faceCard);
    });
}

function drawBoundingBoxes(faces) {
    // Clear previous drawings
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    faces.forEach((face) => {
        const x = face.x_min;
        const y = face.y_min;
        const width = face.x_max - face.x_min;
        const height = face.y_max - face.y_min;

        // Determine color - green for known faces, red for unknown
        const boxColor = face.userid !== 'unknown' ? '#48bb78' : '#ff4444';

        // Draw rectangle
        ctx.strokeStyle = boxColor;
        ctx.lineWidth = 3;
        ctx.strokeRect(x, y, width, height);

        // Draw label background
        const label = face.personName || face.userid || 'Unknown';
        const confidence = (face.confidence * 100).toFixed(0) + '%';
        const labelText = `${label} (${confidence})`;

        ctx.font = '16px Arial';
        const textWidth = ctx.measureText(labelText).width;

        ctx.fillStyle = boxColor;
        ctx.fillRect(x, y - 25, textWidth + 10, 25);

        // Draw label text
        ctx.fillStyle = 'white';
        ctx.fillText(labelText, x + 5, y - 7);
    });
}

function addToRecentScans(name, confidence) {
    const scan = {
        name: name,
        confidence: confidence,
        match: confidence >= 0.6,  // Default threshold
        time: new Date()
    };

    recentScans.unshift(scan);
    if (recentScans.length > MAX_RECENT_SCANS) {
        recentScans.pop();
    }

    displayRecentScans();
}

function displayRecentScans() {
    if (recentScans.length === 0) {
        recentScansList.innerHTML = '<div class="no-faces">No scans yet</div>';
        return;
    }

    recentScansList.innerHTML = recentScans.map(scan => `
        <div class="scan-item ${scan.match ? 'match' : 'no-match'}">
            <div class="scan-name">${scan.name}</div>
            <div class="scan-confidence">Confidence: ${(scan.confidence * 100).toFixed(1)}%</div>
            <div class="scan-time">${scan.time.toLocaleTimeString()}</div>
        </div>
    `).join('');
}

function updateStatusBadge(text, isLoading, isActive = false) {
    const badge = statusBadge;

    if (isActive) {
        badge.className = 'status-badge active';
        badge.innerHTML = `
            <span>✓ ${text}</span>
        `;
    } else if (isLoading) {
        badge.className = 'status-badge';
        badge.innerHTML = `
            <div class="spinner"></div>
            <span>${text}</span>
        `;
    } else {
        badge.className = 'status-badge';
        badge.innerHTML = `
            <span>⚠️ ${text}</span>
        `;
    }
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
    if (websocket) {
        websocket.close();
    }
    if (peerConnection) {
        peerConnection.close();
    }
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
    }
});
