// Configuration - Hard-coded for now
const SERVER_URL = 'http://172.16.1.102:5000';
const POLLING_INTERVAL = 5000;
const MAX_RETRY_ATTEMPTS = 5;
const RETRY_DELAY = 5000;

let deviceId = null;
let deviceToken = null;
let registrationCode = null;
let pollInterval = null;
let retryAttempts = 0;
let retryInterval = null;
let expirationTimerInterval = null;

// Initialize function
var init = function () {
    console.log('========================================');
    console.log('Facial Recognition Device - Initializing');
    console.log('========================================');

    // add eventListener for keydown
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

    // Start device initialization
    initDevice();
};

// window.onload can work without <body onload="">
window.onload = init;

// Initialize device with retry logic
async function initDevice() {
    try {
        // Update loading message
        if (retryAttempts > 0) {
            document.querySelector('#loading-screen p').textContent =
                `Connecting to server... (Attempt ${retryAttempts + 1}/${MAX_RETRY_ATTEMPTS})`;
        }

        // Get or generate device ID using fingerprinting
        deviceId = localStorage.getItem('deviceId');
        if (!deviceId) {
            // Generate device ID from browser fingerprint
            try {
                deviceId = await generateDeviceFingerprint();
                console.log('[FINGERPRINT] Generated device ID:', deviceId);
            } catch (error) {
                console.warn('[FINGERPRINT] Fingerprinting failed, using fallback UUID:', error);
                deviceId = generateUUID();
            }
            localStorage.setItem('deviceId', deviceId);
        } else {
            console.log('[DEVICE] Using existing device ID:', deviceId);
        }

        // Register device with server
        const response = await fetch(`${SERVER_URL}/api/devices/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ device_id: deviceId })
        });

        if (!response.ok) {
            throw new Error('Failed to register device');
        }

        const data = await response.json();
        registrationCode = data.registration_code;

        console.log('[DEVICE] Registration response:', data);

        // Success! Clear any retry intervals and reset counter
        if (retryInterval) {
            clearInterval(retryInterval);
            retryInterval = null;
        }
        retryAttempts = 0;

        // Check if already approved
        if (data.is_approved) {
            console.log('[DEVICE] Device is already approved');
            console.log('[DEVICE] Need to fetch full status with token...');

            // The /register endpoint doesn't return device_token
            // We need to call /status endpoint to get complete device info
            try {
                const statusResponse = await fetch(`${SERVER_URL}/api/devices/status/${deviceId}`);

                if (!statusResponse.ok) {
                    throw new Error('Failed to fetch device status');
                }

                const statusData = await statusResponse.json();
                console.log('[DEVICE] Status data:', JSON.stringify(statusData));

                // Validate configuration
                console.log('[DEVICE] Validating fields:');
                console.log('  - device_name:', statusData.device_name || 'MISSING');
                console.log('  - device_type:', statusData.device_type || 'MISSING');
                console.log('  - device_token:', statusData.device_token ? 'Present' : 'MISSING');
                console.log('  - location_id:', statusData.location_id || 'MISSING');

                if (!statusData.device_name || !statusData.device_type || !statusData.device_token) {
                    console.error('[DEVICE] Missing required fields!');
                    console.error('[DEVICE] device_name:', !!statusData.device_name);
                    console.error('[DEVICE] device_type:', !!statusData.device_type);
                    console.error('[DEVICE] device_token:', !!statusData.device_token);

                    // Start polling to wait for complete configuration
                    console.log('[DEVICE] Starting polling for complete configuration...');
                    showRegistrationScreen(data);
                    startPolling();
                    return;
                }

                // Store device token
                deviceToken = statusData.device_token;
                localStorage.setItem('deviceToken', deviceToken);
                console.log('[TOKEN] Device token stored');

                // Send credentials to Node server
                sendCredentialsToNode();

                // Load device interface
                loadDeviceInterface(statusData);

            } catch (statusError) {
                console.error('[DEVICE] Error fetching status:', statusError);
                // Fall back to polling
                showRegistrationScreen(data);
                startPolling();
            }
        } else {
            console.log('[DEVICE] Device pending approval');

            // Show registration screen
            showRegistrationScreen(data);

            // Start polling for approval
            startPolling();
        }
    } catch (error) {
        console.error('[DEVICE] Error initializing:', error);
        retryAttempts++;

        if (retryAttempts < MAX_RETRY_ATTEMPTS) {
            console.log(`Retry attempt ${retryAttempts}/${MAX_RETRY_ATTEMPTS} in ${RETRY_DELAY/1000} seconds...`);
            setTimeout(initDevice, RETRY_DELAY);
        } else {
            showError('Failed to connect to server. Retrying automatically every 5 seconds...');
            startBackgroundRetry();
        }
    }
}

// Start background retry after showing error
function startBackgroundRetry() {
    if (!retryInterval) {
        retryInterval = setInterval(async () => {
            console.log('[RETRY] Background retry attempt...');
            const savedAttempts = retryAttempts;
            retryAttempts = 0;

            try {
                await initDevice();
            } catch (error) {
                retryAttempts = savedAttempts;
            }
        }, RETRY_DELAY);
    }
}

// Generate device fingerprint
async function generateDeviceFingerprint() {
    const components = [];

    // Screen characteristics
    components.push(screen.width);
    components.push(screen.height);
    components.push(screen.colorDepth);
    components.push(screen.pixelDepth);

    // Browser/Platform info
    components.push(navigator.userAgent);
    components.push(navigator.language);
    components.push(navigator.platform);
    components.push(navigator.hardwareConcurrency || 'unknown');
    components.push(navigator.maxTouchPoints || 0);

    // Timezone
    components.push(Intl.DateTimeFormat().resolvedOptions().timeZone);

    // Canvas fingerprint
    try {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        ctx.textBaseline = 'top';
        ctx.font = '14px Arial';
        ctx.fillText('Device Fingerprint', 2, 2);
        components.push(canvas.toDataURL());
    } catch (e) {
        components.push('canvas-error');
    }

    // WebGL fingerprint
    try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (gl) {
            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            if (debugInfo) {
                components.push(gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL));
                components.push(gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL));
            }
        }
    } catch (e) {
        components.push('webgl-error');
    }

    // Create fingerprint string
    const fingerprintString = components.join('|');

    // Hash the fingerprint
    const hash = await hashString(fingerprintString);

    // Format as UUID
    return `${hash.substr(0, 8)}-${hash.substr(8, 4)}-${hash.substr(12, 4)}-${hash.substr(16, 4)}-${hash.substr(20, 12)}`;
}

// Hash string using SubtleCrypto
async function hashString(str) {
    const encoder = new TextEncoder();
    const data = encoder.encode(str);
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    return hashHex;
}

// Fallback UUID generator
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function showRegistrationScreen(deviceData) {
    document.getElementById('loading-screen').style.display = 'none';
    document.getElementById('registration-screen').style.display = 'block';
    document.getElementById('registration-code').textContent = registrationCode;
    document.getElementById('device-info').innerHTML = `Device ID: ${deviceId}`;

    // Start expiration countdown
    if (deviceData && deviceData.registration_expires_in_seconds) {
        startExpirationTimer(deviceData.registration_expires_in_seconds);
    }
}

function startExpirationTimer(expiresInSeconds) {
    if (expirationTimerInterval) {
        clearInterval(expirationTimerInterval);
    }

    let remainingSeconds = expiresInSeconds;

    function updateTimer() {
        if (remainingSeconds <= 0) {
            console.log('[EXPIRATION] Registration code expired - reloading');
            clearInterval(expirationTimerInterval);
            clearDeviceData();
            window.location.reload();
            return;
        }

        const minutes = Math.floor(remainingSeconds / 60);
        const seconds = remainingSeconds % 60;
        const timeString = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;

        document.getElementById('timer-display').textContent = timeString;

        const timerDiv = document.getElementById('expiration-timer');
        if (remainingSeconds < 120) {
            timerDiv.style.background = '#f8d7da';
            timerDiv.style.color = '#721c24';
        }

        remainingSeconds--;
    }

    updateTimer();
    expirationTimerInterval = setInterval(updateTimer, 1000);
}

function showError(message) {
    document.getElementById('loading-screen').style.display = 'none';
    document.getElementById('registration-screen').style.display = 'none';
    document.getElementById('error-screen').style.display = 'block';
    document.getElementById('error-message').textContent = message;
}

// Poll server for approval status
function startPolling() {
    pollInterval = setInterval(checkStatus, POLLING_INTERVAL);
}

async function checkStatus() {
    try {
        const response = await fetch(`${SERVER_URL}/api/devices/status/${deviceId}`);

        if (!response.ok) {
            if (response.status === 404) {
                console.log('[DEVICE] Device deleted - clearing and re-registering');
                clearInterval(pollInterval);
                clearDeviceData();
                window.location.reload();
                return;
            }
            throw new Error('Failed to check status');
        }

        const data = await response.json();

        // Update expiration timer
        if (!data.is_approved && data.registration_expires_in_seconds !== undefined) {
            startExpirationTimer(data.registration_expires_in_seconds);
        }

        if (data.is_approved) {
            console.log('[DEVICE] Device approved!');
            console.log('[DEVICE] Received data:', JSON.stringify(data));

            // Validate configuration
            console.log('[DEVICE] Validating fields:');
            console.log('  - device_name:', data.device_name || 'MISSING');
            console.log('  - device_type:', data.device_type || 'MISSING');
            console.log('  - device_token:', data.device_token ? 'Present' : 'MISSING');
            console.log('  - location_id:', data.location_id || 'MISSING');
            console.log('  - codeproject_endpoint:', data.codeproject_endpoint || 'Not set (will use server mode)');

            // Required fields for all devices
            if (!data.device_name || !data.device_type || !data.device_token) {
                console.error('[DEVICE] Missing required fields!');
                console.error('[DEVICE] device_name:', !!data.device_name);
                console.error('[DEVICE] device_type:', !!data.device_type);
                console.error('[DEVICE] device_token:', !!data.device_token);

                console.error('[DEVICE] Configuration incomplete - continuing to poll...');
                // Continue polling - maybe the admin hasn't finished configuration yet
                return;
            }

            // Store device token
            deviceToken = data.device_token;
            localStorage.setItem('deviceToken', deviceToken);
            console.log('[TOKEN] Device token received and stored');

            // Send credentials to Node server
            sendCredentialsToNode();

            // Device approved! Load appropriate interface
            clearInterval(pollInterval);
            if (expirationTimerInterval) clearInterval(expirationTimerInterval);
            loadDeviceInterface(data);
        }
    } catch (error) {
        console.error('[DEVICE] Error checking status:', error);
    }
}

function loadDeviceInterface(deviceData) {
    // Store device configuration
    localStorage.setItem('deviceName', deviceData.device_name);
    localStorage.setItem('deviceType', deviceData.device_type);
    localStorage.setItem('locationId', deviceData.location_id);
    localStorage.setItem('codeprojectEndpoint', deviceData.codeproject_endpoint || '');

    console.log('[DEVICE] Loading interface for:', deviceData.device_type);

    // Redirect to appropriate interface
    if (deviceData.device_type === 'registration_kiosk') {
        window.location.href = 'kiosk.html';
    } else if (deviceData.device_type === 'people_scanner') {
        window.location.href = 'scanner.html';
    } else if (deviceData.device_type === 'location_dashboard') {
        window.location.href = 'dashboard.html';
    } else if (deviceData.device_type === 'content_display') {
        window.location.href = 'content_display.html';
    } else {
        showError('Unknown device type. Please contact administrator.');
    }
}

async function sendCredentialsToNode() {
    try {
        console.log('[NODE] Sending credentials to Node server...');

        const response = await fetch('http://localhost:3000/local/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                deviceId: deviceId,
                deviceToken: deviceToken
            })
        });

        if (response.ok) {
            const result = await response.json();
            console.log('[NODE] Credentials sent successfully:', result.message);
        } else {
            console.error('[NODE] Failed to send credentials:', response.status);
        }
    } catch (error) {
        console.error('[NODE] Error sending credentials to Node server:', error);
        // Non-critical error - don't block the registration flow
    }
}

function clearDeviceData() {
    localStorage.removeItem('deviceId');
    localStorage.removeItem('deviceToken');
    localStorage.removeItem('deviceName');
    localStorage.removeItem('deviceType');
    localStorage.removeItem('locationId');
    localStorage.removeItem('codeprojectEndpoint');
}
