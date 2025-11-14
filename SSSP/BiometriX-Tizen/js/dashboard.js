// Configuration - Hard-coded for Tizen
const SERVER_URL = 'http://172.16.1.102:5000';
const HEARTBEAT_INTERVAL = 15000; // 15 seconds

// Get device information
const deviceId = localStorage.getItem('deviceId');
const deviceName = localStorage.getItem('deviceName');
const deviceType = localStorage.getItem('deviceType');
const deviceToken = localStorage.getItem('deviceToken');
const locationId = parseInt(localStorage.getItem('locationId'));

// Validate device data
if (!deviceId || !deviceName || !deviceToken || !locationId || deviceType !== 'location_dashboard') {
    console.log('[DASHBOARD] Missing or invalid device data - redirecting to registration');
    localStorage.clear();
    window.location.href = 'index.html';
}

// State variables
let websocket = null;
let detections = new Map(); // Map of person_name|device_id -> detection data
let presenceTimeoutMinutes = 2; // Default timeout, updated from server
let cleanupInterval = null;
let timestampUpdateInterval = null;
let heartbeatInterval = null;

// DOM elements
const wsStatus = document.getElementById('ws-status');
const wsStatusText = document.getElementById('ws-status-text');
const viewByAreaBtn = document.getElementById('view-by-area-btn');
const viewByDeviceBtn = document.getElementById('view-by-device-btn');
const viewByPersonBtn = document.getElementById('view-by-person-btn');
const viewByArea = document.getElementById('view-by-area');
const viewByDevice = document.getElementById('view-by-device');
const viewByPerson = document.getElementById('view-by-person');
const areasContainer = document.getElementById('areas-container');
const devicesContainer = document.getElementById('devices-container');
const peopleContainer = document.getElementById('people-container');

// Show device info
document.getElementById('device-info').textContent = `Device: ${deviceName} | Location ID: ${locationId}`;

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

function init() {
    console.log('[DASHBOARD] Initializing dashboard');
    console.log('[DASHBOARD] Device:', deviceName, '(' + deviceId + ')');
    console.log('[DASHBOARD] Location ID:', locationId);

    // Set up view switching - default to 'area'
    const currentView = localStorage.getItem('dashboardView') || 'area';
    setView(currentView);

    viewByAreaBtn.addEventListener('click', () => setView('area'));
    viewByDeviceBtn.addEventListener('click', () => setView('device'));
    viewByPersonBtn.addEventListener('click', () => setView('person'));

    // Connect to WebSocket
    connectWebSocket();

    // Start cleanup interval
    cleanupInterval = setInterval(cleanupOldDetections, 30000);

    // Start timestamp update interval
    timestampUpdateInterval = setInterval(updateAllTimestamps, 10000);

    // Start periodic heartbeat
    performHeartbeat();
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
            // Device not found (401) or not approved (403) - redirect to registration
            if (response.status === 401 || response.status === 403) {
                console.log('[HEARTBEAT] Device not found or not approved - redirecting to registration');
                localStorage.clear();
                window.location.href = 'index.html';
                return;
            }
            console.error('[HEARTBEAT] Failed:', response.status);
            return;
        }

        const data = await response.json();
        console.log('[HEARTBEAT] Success');

        // Update location name if provided
        if (data.location_name) {
            updateLocationDisplay(data.location_name);
        }

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

function updateLocationDisplay(locationName) {
    const deviceInfo = document.getElementById('device-info');
    if (deviceInfo) {
        deviceInfo.textContent = `Device: ${deviceName} | Location: ${locationName}`;
    }
}

// ================================================
// VIEW SWITCHING
// ================================================
function setView(view) {
    localStorage.setItem('dashboardView', view);

    // Remove active from all
    viewByAreaBtn.classList.remove('active');
    viewByDeviceBtn.classList.remove('active');
    viewByPersonBtn.classList.remove('active');
    viewByArea.classList.remove('active');
    viewByDevice.classList.remove('active');
    viewByPerson.classList.remove('active');

    // Activate selected
    if (view === 'area') {
        viewByAreaBtn.classList.add('active');
        viewByArea.classList.add('active');
        renderAreaView();
    } else if (view === 'device') {
        viewByDeviceBtn.classList.add('active');
        viewByDevice.classList.add('active');
        renderDeviceView();
    } else {
        viewByPersonBtn.classList.add('active');
        viewByPerson.classList.add('active');
        renderPersonView();
    }
}

function renderCurrentView() {
    const view = localStorage.getItem('dashboardView') || 'area';
    if (view === 'area') {
        renderAreaView();
    } else if (view === 'device') {
        renderDeviceView();
    } else {
        renderPersonView();
    }
}

// ================================================
// WEBSOCKET CONNECTION
// ================================================
function connectWebSocket() {
    console.log('[WebSocket] Connecting to dashboard feed...');

    const wsUrl = SERVER_URL.replace('https://', 'wss://').replace('http://', 'ws://');
    websocket = new WebSocket(`${wsUrl}/ws/dashboard/${locationId}`);

    websocket.onopen = function() {
        console.log('[WebSocket] ✓ Connected to dashboard feed');
        wsStatus.classList.remove('disconnected');
        wsStatusText.textContent = 'Connected';
    };

    websocket.onmessage = function(event) {
        try {
            const message = JSON.parse(event.data);
            console.log('[WebSocket] Message:', message.type);

            if (message.type === 'initial_data') {
                // Load initial detections
                console.log('[WebSocket] Received', message.detections.length, 'initial detections');
                message.detections.forEach(det => {
                    const key = `${det.person_name}|${det.device_id}`;
                    detections.set(key, det);
                });
                renderCurrentView();
            } else if (message.type === 'new_detections') {
                // Update with new detections
                console.log('[WebSocket] Received', message.detections.length, 'new detections');
                message.detections.forEach(det => {
                    const newKey = `${det.person_name}|${det.device_id}`;

                    // Remove any existing detections for this person on OTHER devices
                    const keysToRemove = [];
                    detections.forEach((existingDet, existingKey) => {
                        const existingPersonName = existingKey.split('|')[0];
                        const existingDeviceId = existingKey.split('|')[1];

                        if (existingPersonName === det.person_name && existingDeviceId !== det.device_id) {
                            console.log(`[WebSocket] ${det.person_name} moved from ${existingDet.device_name} to ${det.device_name}`);
                            keysToRemove.push(existingKey);
                        }
                    });

                    // Remove old detections
                    keysToRemove.forEach(key => detections.delete(key));

                    // Add new detection
                    detections.set(newKey, det);
                });
                renderCurrentView();
            }
        } catch (e) {
            console.error('[WebSocket] Parse error:', e);
        }
    };

    websocket.onerror = function(error) {
        console.error('[WebSocket] Error:', error);
        wsStatus.classList.add('disconnected');
        wsStatusText.textContent = 'Error';
    };

    websocket.onclose = function() {
        console.log('[WebSocket] Connection closed, reconnecting in 5s...');
        wsStatus.classList.add('disconnected');
        wsStatusText.textContent = 'Disconnected';
        setTimeout(connectWebSocket, 5000);
    };
}

// ================================================
// CLEANUP OLD DETECTIONS
// ================================================
function cleanupOldDetections() {
    const now = Date.now();
    const timeoutMs = presenceTimeoutMinutes * 60 * 1000;
    let removed = 0;

    console.log(`[CLEANUP] Running - timeout: ${presenceTimeoutMinutes} min`);

    detections.forEach((detection, compositeKey) => {
        const personName = compositeKey.split('|')[0];

        // Parse detection timestamp
        let dateString = detection.detected_at;
        if (dateString.includes('T') && !dateString.endsWith('Z') && !dateString.includes('+')) {
            dateString = dateString + 'Z';
        }

        const detectedAt = new Date(dateString).getTime();
        const age = now - detectedAt;

        if (age > timeoutMs) {
            console.log(`[CLEANUP] Removing ${personName} (too old)`);
            detections.delete(compositeKey);
            removed++;
        }
    });

    if (removed > 0) {
        console.log(`[CLEANUP] Removed ${removed} old detections`);
        renderCurrentView();
    }
}

// ================================================
// UPDATE TIMESTAMPS
// ================================================
function updateAllTimestamps() {
    const timestampElements = document.querySelectorAll('.timestamp');

    timestampElements.forEach(el => {
        const card = el.closest('.detection-card, .person-card');
        if (!card) return;

        const compositeKey = card.dataset.detectionKey;
        if (!compositeKey) return;

        const detection = detections.get(compositeKey);
        if (detection && detection.detected_at) {
            el.textContent = formatTimestamp(detection.detected_at);
        }
    });
}

// ================================================
// RENDERING
// ================================================
function renderDeviceView() {
    // Group detections by device
    const deviceGroups = new Map();

    for (const [compositeKey, detection] of detections.entries()) {
        const personName = compositeKey.split('|')[0];
        const deviceId = detection.device_id;

        if (!deviceGroups.has(deviceId)) {
            deviceGroups.set(deviceId, {
                deviceName: detection.device_name || deviceId.substring(0, 8),
                detections: []
            });
        }
        deviceGroups.get(deviceId).detections.push({ personName, ...detection });
    }

    // Render
    if (deviceGroups.size === 0) {
        devicesContainer.innerHTML = `
            <div class="empty-state">
                <h3>No Recent Detections</h3>
                <p>Waiting for people to be detected by scanners...</p>
            </div>
        `;
        return;
    }

    devicesContainer.innerHTML = '';

    for (const [deviceId, group] of deviceGroups.entries()) {
        const section = document.createElement('div');
        section.className = 'device-section';

        const header = document.createElement('div');
        header.innerHTML = `<h3>📱 Device: ${group.deviceName}</h3>`;
        section.appendChild(header);

        const grid = document.createElement('div');
        grid.className = 'detection-grid';

        group.detections.forEach(det => {
            const card = createDetectionCard(det);
            grid.appendChild(card);
        });

        section.appendChild(grid);
        devicesContainer.appendChild(section);
    }
}

function renderPersonView() {
    if (detections.size === 0) {
        peopleContainer.innerHTML = `
            <div class="empty-state">
                <h3>No Recent Detections</h3>
                <p>Waiting for people to be detected by scanners...</p>
            </div>
        `;
        return;
    }

    peopleContainer.innerHTML = '';

    // Group by person_name and show most recent detection per person
    const peopleMap = new Map();
    for (const [compositeKey, detection] of detections.entries()) {
        const personName = compositeKey.split('|')[0];

        if (!peopleMap.has(personName)) {
            peopleMap.set(personName, { personName, ...detection });
        } else {
            const existing = peopleMap.get(personName);
            if (new Date(detection.detected_at) > new Date(existing.detected_at)) {
                peopleMap.set(personName, { personName, ...detection });
            }
        }
    }

    for (const [personName, detection] of peopleMap.entries()) {
        const card = createPersonCard(personName, detection);
        peopleContainer.appendChild(card);
    }
}

function renderAreaView() {
    // Group detections by area
    const areaGroups = new Map();

    for (const [compositeKey, detection] of detections.entries()) {
        const personName = compositeKey.split('|')[0];

        // Get area name (null if device not assigned to area)
        const areaName = detection.area_name || 'Unassigned';

        if (!areaGroups.has(areaName)) {
            areaGroups.set(areaName, {
                areaName: areaName,
                detections: []
            });
        }
        areaGroups.get(areaName).detections.push({ personName, ...detection });
    }

    // Render
    if (areaGroups.size === 0) {
        areasContainer.innerHTML = `
            <div class="empty-state">
                <h3>No Recent Detections</h3>
                <p>Waiting for people to be detected by scanners...</p>
            </div>
        `;
        return;
    }

    areasContainer.innerHTML = '';

    // Sort areas alphabetically (Unassigned last)
    const sortedAreas = Array.from(areaGroups.entries()).sort((a, b) => {
        if (a[0] === 'Unassigned') return 1;
        if (b[0] === 'Unassigned') return -1;
        return a[0].localeCompare(b[0]);
    });

    for (const [areaName, group] of sortedAreas) {
        const section = document.createElement('div');
        section.className = 'device-section';

        const header = document.createElement('div');
        const icon = areaName === 'Unassigned' ? '❓' : '📍';
        header.innerHTML = `<h3>${icon} ${areaName}</h3>`;
        section.appendChild(header);

        const grid = document.createElement('div');
        grid.className = 'detection-grid';

        // Group by person within area - show most recent per person
        const peopleInArea = new Map();
        for (const det of group.detections) {
            const pName = det.personName;
            if (!peopleInArea.has(pName)) {
                peopleInArea.set(pName, det);
            } else {
                const existing = peopleInArea.get(pName);
                if (new Date(det.detected_at) > new Date(existing.detected_at)) {
                    peopleInArea.set(pName, det);
                }
            }
        }

        for (const detection of peopleInArea.values()) {
            const card = createDetectionCard(detection);
            grid.appendChild(card);
        }

        section.appendChild(grid);
        areasContainer.appendChild(section);
    }
}

function createDetectionCard(detection) {
    const card = document.createElement('div');
    card.className = 'detection-card';
    card.dataset.detectionKey = `${detection.personName}|${detection.device_id}`;

    // Profile photo placeholder
    const placeholder = document.createElement('div');
    placeholder.className = 'profile-photo-placeholder';
    placeholder.textContent = detection.personName.charAt(0).toUpperCase();
    card.appendChild(placeholder);

    const name = document.createElement('h4');
    name.textContent = detection.personName;
    card.appendChild(name);

    const confidence = document.createElement('div');
    confidence.className = 'confidence';
    confidence.textContent = `${(detection.confidence * 100).toFixed(1)}% confidence`;
    card.appendChild(confidence);

    const timestamp = document.createElement('div');
    timestamp.className = 'timestamp';
    timestamp.textContent = formatTimestamp(detection.detected_at);
    card.appendChild(timestamp);

    return card;
}

function createPersonCard(personName, detection) {
    const card = document.createElement('div');
    card.className = 'person-card';
    card.dataset.detectionKey = `${personName}|${detection.device_id}`;

    // Profile photo placeholder
    const placeholder = document.createElement('div');
    placeholder.className = 'profile-photo-placeholder';
    placeholder.textContent = personName.charAt(0).toUpperCase();
    card.appendChild(placeholder);

    const info = document.createElement('div');

    const name = document.createElement('div');
    name.className = 'person-name';
    name.textContent = personName;
    info.appendChild(name);

    const deviceName = document.createElement('div');
    deviceName.className = 'device-name';
    deviceName.textContent = `📱 ${detection.device_name || detection.device_id.substring(0, 8)}`;
    info.appendChild(deviceName);

    const confidence = document.createElement('div');
    confidence.className = 'confidence';
    confidence.textContent = `${(detection.confidence * 100).toFixed(1)}% confidence`;
    info.appendChild(confidence);

    const timestamp = document.createElement('div');
    timestamp.className = 'timestamp';
    timestamp.textContent = formatTimestamp(detection.detected_at);
    info.appendChild(timestamp);

    card.appendChild(info);

    return card;
}

function formatTimestamp(isoString) {
    // Add 'Z' for UTC if missing
    let dateString = isoString;
    if (dateString.includes('T') && !dateString.endsWith('Z') && !dateString.includes('+')) {
        dateString = dateString + 'Z';
    }

    const date = new Date(dateString);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000); // seconds

    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} hr ago`;
    return date.toLocaleString();
}

// Cleanup on unload
window.addEventListener('beforeunload', () => {
    if (heartbeatInterval) clearInterval(heartbeatInterval);
    if (websocket) websocket.close();
    if (cleanupInterval) clearInterval(cleanupInterval);
    if (timestampUpdateInterval) clearInterval(timestampUpdateInterval);
});
