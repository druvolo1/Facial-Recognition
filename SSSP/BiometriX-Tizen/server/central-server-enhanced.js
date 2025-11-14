// ENHANCED CENTRAL AGGREGATION SERVER
// Visual display positioning and real-time triangulation
// Run this on your central computer (10.20.10.192)

var http = require('http');
var fs = require('fs');
var path = require('path');

// Store data from all displays
var displays = {};  // { displayId: { name, x, y, lastUpdate, devices, configured } }
var displayPositions = {};  // Persistent positions { displayId: { x, y, name } }
var triangulatedDevices = {};  // { deviceAddress: { x, y, confidence, seenBy } }

// Configuration
var config = {
    port: 4000,
    updateInterval: 3000,
    positionsFile: path.join(__dirname, 'display-positions.json'),
    floorPlanFile: path.join(__dirname, 'floorplan-image.dat'),
    scaleFile: path.join(__dirname, 'scale-config.json')
};

// Floor plan and scale
var floorPlanData = null;
var scaleConfig = null;

console.log('===== ENHANCED CENTRAL TRILATERATION SERVER STARTING =====');

// Load saved display positions
function loadDisplayPositions() {
    try {
        if (fs.existsSync(config.positionsFile)) {
            var data = fs.readFileSync(config.positionsFile, 'utf8');
            displayPositions = JSON.parse(data);
            console.log('✅ Loaded', Object.keys(displayPositions).length, 'display positions');
        }
    } catch(e) {
        console.error('Error loading positions:', e.message);
        displayPositions = {};
    }
}

// Save display positions
function saveDisplayPositions() {
    try {
        fs.writeFileSync(config.positionsFile, JSON.stringify(displayPositions, null, 2));
        console.log('💾 Saved display positions');
    } catch(e) {
        console.error('Error saving positions:', e.message);
    }
}

loadDisplayPositions();

// Load scale configuration
function loadScale() {
    try {
        if (fs.existsSync(config.scaleFile)) {
            var data = fs.readFileSync(config.scaleFile, 'utf8');
            scaleConfig = JSON.parse(data);
            console.log('✅ Loaded scale configuration');
        }
    } catch(e) {
        console.error('Error loading scale:', e.message);
        scaleConfig = null;
    }
}

// Save scale configuration
function saveScale() {
    try {
        fs.writeFileSync(config.scaleFile, JSON.stringify(scaleConfig, null, 2));
        console.log('💾 Saved scale configuration');
    } catch(e) {
        console.error('Error saving scale:', e.message);
    }
}

loadScale();

// Start HTTP server
var server = http.createServer(function(req, res) {
    var url = req.url;

    // CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        res.writeHead(200);
        res.end();
        return;
    }

    // Route: POST /report - Display reports its data
    if (url === '/report' && req.method === 'POST') {
        var body = '';
        req.on('data', function(chunk) {
            body += chunk.toString();
        });
        req.on('end', function() {
            try {
                var data = JSON.parse(body);
                handleDisplayReport(data);
                res.writeHead(200, {'Content-Type': 'application/json'});
                res.end(JSON.stringify({status: 'ok', received: true}));
            } catch(e) {
                console.error('Error parsing report:', e);
                res.writeHead(400, {'Content-Type': 'application/json'});
                res.end(JSON.stringify({status: 'error', message: e.message}));
            }
        });
        return;
    }

    // Route: GET / - Management UI
    if (url === '/' || url === '/index.html') {
        serveManagementUI(res);
        return;
    }

    // Route: GET /data - Get all data (displays + triangulated devices)
    if (url === '/data' && req.method === 'GET') {
        res.writeHead(200, {'Content-Type': 'application/json'});
        res.end(JSON.stringify({
            displays: displays,
            devices: triangulatedDevices,
            timestamp: new Date().toISOString()
        }));
        return;
    }

    // Route: PUT /display/:id/position - Update display position manually
    if (url.startsWith('/display/') && url.includes('/position') && req.method === 'PUT') {
        var displayId = url.split('/')[2];
        var body = '';
        req.on('data', function(chunk) {
            body += chunk.toString();
        });
        req.on('end', function() {
            try {
                var position = JSON.parse(body);
                updateDisplayPosition(displayId, position.x, position.y, position.name);
                res.writeHead(200, {'Content-Type': 'application/json'});
                res.end(JSON.stringify({status: 'ok'}));
            } catch(e) {
                res.writeHead(400, {'Content-Type': 'application/json'});
                res.end(JSON.stringify({status: 'error', message: e.message}));
            }
        });
        return;
    }

    // Route: PUT /display/:id/rename - Rename display
    if (url.startsWith('/display/') && url.includes('/rename') && req.method === 'PUT') {
        var displayId = url.split('/')[2];
        var body = '';
        req.on('data', function(chunk) {
            body += chunk.toString();
        });
        req.on('end', function() {
            try {
                var data = JSON.parse(body);
                renameDisplay(displayId, data.name);
                res.writeHead(200, {'Content-Type': 'application/json'});
                res.end(JSON.stringify({status: 'ok', displayId: displayId, newName: data.name}));
            } catch(e) {
                res.writeHead(400, {'Content-Type': 'application/json'});
                res.end(JSON.stringify({status: 'error', message: e.message}));
            }
        });
        return;
    }

    // Route: DELETE /display/:id - Delete display
    if (url.startsWith('/display/') && !url.includes('/position') && !url.includes('/rename') && req.method === 'DELETE') {
        var displayId = url.split('/')[2];
        try {
            deleteDisplay(displayId);
            res.writeHead(200, {'Content-Type': 'application/json'});
            res.end(JSON.stringify({status: 'ok', displayId: displayId, message: 'Display deleted'}));
        } catch(e) {
            res.writeHead(400, {'Content-Type': 'application/json'});
            res.end(JSON.stringify({status: 'error', message: e.message}));
        }
        return;
    }

    // Route: GET /status
    if (url === '/status' && req.method === 'GET') {
        res.writeHead(200, {'Content-Type': 'application/json'});
        res.end(JSON.stringify({
            status: 'running',
            displayCount: Object.keys(displays).length,
            deviceCount: Object.keys(triangulatedDevices).length,
            displays: Object.keys(displays).map(function(id) {
                return {
                    id: id,
                    name: displays[id].name,
                    position: {x: displays[id].x, y: displays[id].y},
                    configured: displays[id].configured,
                    lastUpdate: displays[id].lastUpdate
                };
            })
        }, null, 2));
        return;
    }

    // Route: POST /upload-floorplan - Upload floor plan image
    if (url === '/upload-floorplan' && req.method === 'POST') {
        var chunks = [];
        req.on('data', function(chunk) {
            chunks.push(chunk);
        });
        req.on('end', function() {
            try {
                var buffer = Buffer.concat(chunks);

                // Parse multipart form data (simple boundary parser)
                var boundaryMatch = req.headers['content-type'].match(/boundary=(.+)$/);
                if (!boundaryMatch) {
                    res.writeHead(400, {'Content-Type': 'application/json'});
                    res.end(JSON.stringify({status: 'error', message: 'No boundary found'}));
                    return;
                }

                var boundary = '--' + boundaryMatch[1];
                var boundaryBuffer = Buffer.from(boundary);

                // Find the start and end of the file data
                var start = buffer.indexOf(boundaryBuffer);
                if (start === -1) {
                    res.writeHead(400, {'Content-Type': 'application/json'});
                    res.end(JSON.stringify({status: 'error', message: 'Boundary not found in data'}));
                    return;
                }

                // Find the double CRLF that separates headers from data
                var headerSep = Buffer.from([13, 10, 13, 10]); // \r\n\r\n
                var dataStart = buffer.indexOf(headerSep, start);
                if (dataStart === -1) {
                    res.writeHead(400, {'Content-Type': 'application/json'});
                    res.end(JSON.stringify({status: 'error', message: 'Header separator not found'}));
                    return;
                }
                dataStart += 4; // Skip the separator

                // Find the next boundary (end of file data)
                var dataEnd = buffer.indexOf(boundaryBuffer, dataStart);
                if (dataEnd === -1) {
                    res.writeHead(400, {'Content-Type': 'application/json'});
                    res.end(JSON.stringify({status: 'error', message: 'End boundary not found'}));
                    return;
                }

                // Remove trailing CRLF before the boundary
                while (dataEnd > dataStart && (buffer[dataEnd - 1] === 10 || buffer[dataEnd - 1] === 13)) {
                    dataEnd--;
                }

                // Extract the file data
                var fileBuffer = buffer.slice(dataStart, dataEnd);
                fs.writeFileSync(config.floorPlanFile, fileBuffer);
                console.log('✅ Floor plan uploaded, size:', fileBuffer.length, 'bytes');

                res.writeHead(200, {'Content-Type': 'application/json'});
                res.end(JSON.stringify({status: 'ok', size: fileBuffer.length}));
            } catch(e) {
                console.error('Error uploading floor plan:', e);
                res.writeHead(500, {'Content-Type': 'application/json'});
                res.end(JSON.stringify({status: 'error', message: e.message}));
            }
        });
        return;
    }

    // Route: GET /floorplan - Serve floor plan image
    if (url.startsWith('/floorplan') && req.method === 'GET') {
        try {
            if (fs.existsSync(config.floorPlanFile)) {
                var fileData = fs.readFileSync(config.floorPlanFile);
                res.writeHead(200, {'Content-Type': 'image/png'});
                res.end(fileData);
            } else {
                res.writeHead(404, {'Content-Type': 'application/json'});
                res.end(JSON.stringify({status: 'error', message: 'No floor plan uploaded'}));
            }
        } catch(e) {
            res.writeHead(500, {'Content-Type': 'application/json'});
            res.end(JSON.stringify({status: 'error', message: e.message}));
        }
        return;
    }

    // Route: POST /scale - Save scale configuration
    if (url === '/scale' && req.method === 'POST') {
        var body = '';
        req.on('data', function(chunk) {
            body += chunk.toString();
        });
        req.on('end', function() {
            try {
                scaleConfig = JSON.parse(body);
                saveScale();
                res.writeHead(200, {'Content-Type': 'application/json'});
                res.end(JSON.stringify({status: 'ok', scale: scaleConfig}));
            } catch(e) {
                res.writeHead(400, {'Content-Type': 'application/json'});
                res.end(JSON.stringify({status: 'error', message: e.message}));
            }
        });
        return;
    }

    // Route: GET /scale - Get scale configuration
    if (url === '/scale' && req.method === 'GET') {
        res.writeHead(200, {'Content-Type': 'application/json'});
        res.end(JSON.stringify({
            scale: scaleConfig,
            hasFloorplan: fs.existsSync(config.floorPlanFile)
        }));
        return;
    }

    // 404
    res.writeHead(404, {'Content-Type': 'text/plain'});
    res.end('Not Found');
});

server.listen(config.port, '0.0.0.0', function() {
    console.log('✅ Enhanced Central Server running on port', config.port);
    console.log('✅ Management UI: http://10.20.10.192:4000/');
    console.log('✅ Displays will auto-register when they connect');
});

// Handle data from a display
function handleDisplayReport(data) {
    var displayId = data.displayId;

    // Check if we have a saved position for this display
    var savedPosition = displayPositions[displayId];
    var displayX = savedPosition ? savedPosition.x : 100;  // Default position
    var displayY = savedPosition ? savedPosition.y : 100;
    var displayName = savedPosition ? savedPosition.name : (data.displayName || displayId);

    displays[displayId] = {
        id: displayId,
        name: displayName,
        x: displayX,
        y: displayY,
        devices: data.devices || [],
        lastUpdate: new Date().toISOString(),
        configured: savedPosition ? true : false
    };

    console.log('📡 Report from', displayName, '- Position:', displayX + ',' + displayY, '- Devices:', data.devices.length, '- Configured:', displays[displayId].configured ? '✅' : '⚠️ Needs positioning');

    // Trigger triangulation
    triangulateDevices();
}

// Update display position from UI
function updateDisplayPosition(displayId, x, y, name) {
    displayPositions[displayId] = { x: x, y: y, name: name };
    saveDisplayPositions();

    // Update live display data if it exists
    if (displays[displayId]) {
        displays[displayId].x = x;
        displays[displayId].y = y;
        displays[displayId].name = name;
        displays[displayId].configured = true;
        console.log('📍 Updated position for', name, ':', x, ',', y);
        triangulateDevices();
    }
}

// Rename display
function renameDisplay(displayId, newName) {
    // Update saved position with new name
    if (displayPositions[displayId]) {
        displayPositions[displayId].name = newName;
    } else {
        // If no position saved yet, create entry with default position
        displayPositions[displayId] = {
            x: displays[displayId] ? displays[displayId].x : 100,
            y: displays[displayId] ? displays[displayId].y : 100,
            name: newName
        };
    }
    saveDisplayPositions();

    // Update live display data if it exists
    if (displays[displayId]) {
        displays[displayId].name = newName;
        console.log('✏️ Renamed display', displayId, 'to:', newName);
    }
}

// Delete display
function deleteDisplay(displayId) {
    var displayName = displays[displayId] ? displays[displayId].name : displayId;

    // Remove from live displays
    if (displays[displayId]) {
        delete displays[displayId];
        console.log('🗑️ Removed live display:', displayName, '(' + displayId + ')');
    }

    // Remove from saved positions
    if (displayPositions[displayId]) {
        delete displayPositions[displayId];
        saveDisplayPositions();
        console.log('🗑️ Removed saved position for:', displayName);
    }

    // Recalculate triangulation without this display
    triangulateDevices();

    console.log('✅ Display deleted:', displayName, '(' + displayId + ')');
}

// Convert RSSI to distance estimate (meters)
function rssiToDistance(rssi, txPower) {
    if (!txPower) txPower = -59;
    if (rssi === 0) return -1;

    var ratio = rssi / txPower;
    if (ratio < 1.0) {
        return Math.pow(ratio, 10);
    } else {
        var distance = 0.89976 * Math.pow(ratio, 7.7095) + 0.111;
        return distance;
    }
}

// Trilateration algorithm
function triangulateDevices() {
    triangulatedDevices = {};

    // Group devices by address across all displays
    var deviceReadings = {};

    Object.keys(displays).forEach(function(displayId) {
        var display = displays[displayId];

        display.devices.forEach(function(device) {
            if (!deviceReadings[device.address]) {
                deviceReadings[device.address] = [];
            }

            var distance = rssiToDistance(device.rssi);

            deviceReadings[device.address].push({
                displayId: displayId,
                displayName: display.name,
                x: display.x,
                y: display.y,
                rssi: device.rssi,
                distance: distance,
                name: device.name
            });
        });
    });

    // Calculate position for each device
    Object.keys(deviceReadings).forEach(function(address) {
        var readings = deviceReadings[address];

        if (readings.length < 2) {
            var reading = readings[0];
            triangulatedDevices[address] = {
                name: reading.name,
                address: address,
                x: reading.x,
                y: reading.y,
                confidence: 'low',
                seenBy: 1,
                readings: readings
            };
        } else if (readings.length === 2) {
            var pos = trilaterateFromTwo(readings);
            triangulatedDevices[address] = {
                name: readings[0].name,
                address: address,
                x: pos.x,
                y: pos.y,
                confidence: 'medium',
                seenBy: 2,
                readings: readings
            };
        } else {
            var pos = trilaterateFromMultiple(readings);
            triangulatedDevices[address] = {
                name: readings[0].name,
                address: address,
                x: pos.x,
                y: pos.y,
                confidence: 'high',
                seenBy: readings.length,
                readings: readings
            };
        }
    });

    if (Object.keys(triangulatedDevices).length > 0) {
        console.log('📍 Triangulated', Object.keys(triangulatedDevices).length, 'devices');
    }
}

function trilaterateFromTwo(readings) {
    var r1 = readings[0];
    var r2 = readings[1];

    var w1 = 1 / (r1.distance + 0.1);
    var w2 = 1 / (r2.distance + 0.1);
    var totalWeight = w1 + w2;

    return {
        x: (r1.x * w1 + r2.x * w2) / totalWeight,
        y: (r1.y * w1 + r2.y * w2) / totalWeight
    };
}

function trilaterateFromMultiple(readings) {
    var sumX = 0, sumY = 0, sumW = 0;

    readings.forEach(function(r) {
        var weight = 1 / (r.distance + 0.1);
        sumX += r.x * weight;
        sumY += r.y * weight;
        sumW += weight;
    });

    return {
        x: sumX / sumW,
        y: sumY / sumW
    };
}

function serveManagementUI(res) {
    var html = `<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>BiometriX - Central Management Console</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f0f1e;
            color: white;
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }
        .header h1 {
            font-size: 32px;
            margin-bottom: 5px;
        }
        .header p {
            opacity: 0.9;
            font-size: 14px;
        }
        .container {
            display: flex;
            height: calc(100vh - 100px);
        }
        .sidebar {
            width: 350px;
            background: #1a1a2e;
            padding: 20px;
            overflow-y: auto;
            border-right: 2px solid #667eea;
        }
        .sidebar h2 {
            color: #667eea;
            margin-bottom: 15px;
            font-size: 20px;
        }
        .display-item {
            background: #2a2a3e;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 8px;
            cursor: move;
            border: 2px solid transparent;
            transition: all 0.2s;
        }
        .display-item:hover {
            border-color: #667eea;
            transform: translateX(5px);
        }
        .display-item.configured {
            border-left: 4px solid #28a745;
        }
        .display-item.unconfigured {
            border-left: 4px solid #ffc107;
        }
        .display-name {
            font-weight: bold;
            font-size: 16px;
            margin-bottom: 5px;
        }
        .display-info {
            font-size: 12px;
            color: #aaa;
        }
        .status-badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            margin-top: 5px;
        }
        .status-configured {
            background: #28a745;
            color: white;
        }
        .status-unconfigured {
            background: #ffc107;
            color: #000;
        }
        .map-area {
            flex: 1;
            position: relative;
            background: #0f0f1e;
        }
        .map-controls {
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(26, 26, 46, 0.95);
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #667eea;
            z-index: 100;
        }
        .stats {
            display: grid;
            gap: 10px;
        }
        .stat {
            font-size: 14px;
        }
        .stat-value {
            font-weight: bold;
            color: #00ff41;
        }
        #floorPlan {
            width: 100%;
            height: 100%;
            background:
                repeating-linear-gradient(0deg, transparent, transparent 49px, #333 49px, #333 50px),
                repeating-linear-gradient(90deg, transparent, transparent 49px, #333 49px, #333 50px);
            background-size: 50px 50px;
        }
        .display-marker {
            position: absolute;
            width: 60px;
            height: 40px;
            background: #00bcd4;
            border: 3px solid white;
            border-radius: 4px;
            cursor: move;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 10px;
            font-weight: bold;
            color: white;
            text-align: center;
            padding: 2px;
            user-select: none;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            z-index: 10;
        }
        .display-marker:hover {
            transform: scale(1.1);
            box-shadow: 0 6px 16px rgba(0,0,0,0.7);
        }
        .display-marker.dragging {
            opacity: 0.7;
            z-index: 1000;
        }
        .device-marker {
            position: absolute;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            border: 2px solid white;
            cursor: pointer;
            box-shadow: 0 2px 8px rgba(0,0,0,0.5);
            z-index: 5;
        }
        .device-marker.high {
            background: #00ff41;
        }
        .device-marker.medium {
            background: #ffeb3b;
        }
        .device-marker.low {
            background: #f44336;
        }
        .device-label {
            position: absolute;
            top: -25px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.8);
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            white-space: nowrap;
            pointer-events: none;
        }
        .coverage-circle {
            position: absolute;
            border: 1px solid rgba(0, 188, 212, 0.3);
            border-radius: 50%;
            background: radial-gradient(circle, rgba(0, 188, 212, 0.05), transparent);
            pointer-events: none;
        }
        .instructions {
            background: #2a2a3e;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            font-size: 13px;
            line-height: 1.6;
        }
        .instructions strong {
            color: #667eea;
        }
        .floor-plan-controls {
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(26, 26, 46, 0.95);
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #667eea;
            z-index: 100;
            max-width: 300px;
        }
        .upload-btn, .calibrate-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            margin: 5px 0;
            width: 100%;
            display: block;
        }
        .upload-btn:hover, .calibrate-btn:hover {
            background: #5568d3;
        }
        .scale-info {
            font-size: 12px;
            color: #aaa;
            margin-top: 10px;
            padding: 8px;
            background: rgba(0,0,0,0.3);
            border-radius: 4px;
        }
        .calibration-line {
            position: absolute;
            background: #00ff41;
            height: 3px;
            transform-origin: left center;
            pointer-events: none;
            z-index: 1000;
        }
        .calibration-point {
            position: absolute;
            width: 10px;
            height: 10px;
            background: #00ff41;
            border: 2px solid white;
            border-radius: 50%;
            transform: translate(-50%, -50%);
            pointer-events: none;
            z-index: 1001;
        }
        #floorPlan.calibrating {
            cursor: crosshair;
        }
        #floorPlanImage {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: contain;
            opacity: 0.7;
            pointer-events: none;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🗺️ BiometriX Central Management Console</h1>
        <p>Drag and drop displays to position them on the floor plan • Real-time device triangulation</p>
    </div>

    <div class="container">
        <div class="sidebar">
            <div class="instructions">
                <strong>How to use:</strong><br>
                1. TV displays will appear here automatically when they connect<br>
                2. Drag each display from this list onto the floor plan<br>
                3. Position represents physical location in your space<br>
                4. Devices will be triangulated automatically
            </div>

            <h2>📺 Connected Displays (<span id="displayCount">0</span>)</h2>
            <div id="displayList"></div>

            <h2 style="margin-top: 20px;">📱 Detected Devices (<span id="deviceCount">0</span>)</h2>
            <div id="deviceListSidebar"></div>
        </div>

        <div class="map-area">
            <div class="floor-plan-controls">
                <h3 style="margin-bottom: 10px; font-size: 14px; color: #667eea;">Floor Plan</h3>
                <input type="file" id="floorPlanUpload" accept="image/*,.pdf" style="display: none;">
                <button class="upload-btn" onclick="document.getElementById('floorPlanUpload').click()">📁 Upload Floor Plan</button>

                <div style="margin: 8px 0;">
                    <label style="font-size: 11px; color: #aaa; display: block; margin-bottom: 3px;">Measurement Unit:</label>
                    <select id="unitSelect" style="width: 100%; padding: 6px; background: #2a2a3e; color: white; border: 1px solid #667eea; border-radius: 4px; font-size: 12px;">
                        <option value="meters">Meters (m)</option>
                        <option value="feet">Feet (ft)</option>
                        <option value="inches">Inches (in)</option>
                        <option value="centimeters">Centimeters (cm)</option>
                    </select>
                </div>

                <button class="calibrate-btn" id="calibrateBtn">📏 Set Scale</button>
                <div class="scale-info" id="scaleInfo">
                    <div>No scale set</div>
                    <div style="font-size: 10px; margin-top: 5px;">Upload a floor plan and click "Set Scale" to calibrate</div>
                </div>
            </div>
            <div class="map-controls">
                <div class="stats">
                    <div class="stat">Active Displays: <span class="stat-value" id="activeDisplays">0</span></div>
                    <div class="stat">Configured: <span class="stat-value" id="configuredDisplays">0</span></div>
                    <div class="stat">Total Devices: <span class="stat-value" id="totalDevices">0</span></div>
                    <div class="stat">High Confidence: <span class="stat-value" id="highConfidence">0</span></div>
                </div>
            </div>
            <div id="floorPlan">
                <img id="floorPlanImage" style="display: none;">
            </div>
        </div>
    </div>

    <script>
        var floorPlan = document.getElementById('floorPlan');
        var draggedDisplay = null;
        var displayMarkers = {};  // Track DOM elements for displays

        // Floor plan and scale variables
        var floorPlanImage = document.getElementById('floorPlanImage');
        var scale = null;  // { pixelsPerMeter: 50, realWorldLength: 10, unit: 'meters' }
        var isCalibrating = false;
        var calibrationPoints = [];

        // Unit conversion to meters
        var unitConversions = {
            meters: 1,
            feet: 0.3048,
            inches: 0.0254,
            centimeters: 0.01
        };

        var unitLabels = {
            meters: 'm',
            feet: 'ft',
            inches: 'in',
            centimeters: 'cm'
        };

        function updateUI() {
            fetch('/data')
                .then(res => res.json())
                .then(data => {
                    updateSidebar(data);
                    updateFloorPlan(data);
                    updateStats(data);
                })
                .catch(err => console.error('Error:', err));
        }

        function updateSidebar(data) {
            var displayList = document.getElementById('displayList');
            var html = '';

            Object.keys(data.displays).forEach(function(id) {
                var display = data.displays[id];
                var configured = display.configured ? 'configured' : 'unconfigured';
                var statusClass = display.configured ? 'status-configured' : 'status-unconfigured';
                var statusText = display.configured ? '✓ Positioned' : '⚠ Drag to map';

                html += '<div class="display-item ' + configured + '" draggable="true" data-id="' + id + '">';
                html += '<div class="display-name">' + display.name;
                html += ' <button class="rename-btn" data-display-id="' + id + '" style="background: #667eea; color: white; border: none; padding: 3px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; margin-left: 5px;">✏️ Rename</button>';
                html += ' <button class="delete-btn" data-display-id="' + id + '" style="background: #dc3545; color: white; border: none; padding: 3px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; margin-left: 3px;">🗑️ Delete</button>';
                html += '</div>';
                html += '<div class="display-info">MAC: ' + id + '</div>';
                html += '<div class="display-info">Position: (' + Math.round(display.x) + ', ' + Math.round(display.y) + ')</div>';
                html += '<div class="display-info">Devices: ' + display.devices.length + '</div>';
                html += '<span class="status-badge ' + statusClass + '">' + statusText + '</span>';
                html += '</div>';
            });

            displayList.innerHTML = html || '<p style="color: #666;">No displays connected yet...</p>';

            // Add drag handlers
            document.querySelectorAll('.display-item').forEach(function(item) {
                item.addEventListener('dragstart', handleDragStart);
            });

            // Add button event listeners
            document.querySelectorAll('.rename-btn').forEach(function(btn) {
                btn.addEventListener('click', function(e) {
                    e.stopPropagation();
                    renameDisplay(this.getAttribute('data-display-id'));
                });
            });

            document.querySelectorAll('.delete-btn').forEach(function(btn) {
                btn.addEventListener('click', function(e) {
                    e.stopPropagation();
                    deleteDisplay(this.getAttribute('data-display-id'));
                });
            });

            document.getElementById('displayCount').textContent = Object.keys(data.displays).length;

            // Device list in sidebar
            var deviceListSidebar = document.getElementById('deviceListSidebar');
            var deviceHtml = '';
            Object.values(data.devices).forEach(function(device) {
                var color = device.confidence === 'high' ? '#00ff41' : device.confidence === 'medium' ? '#ffeb3b' : '#f44336';
                deviceHtml += '<div style="background: #2a2a3e; padding: 10px; margin-bottom: 8px; border-radius: 6px; border-left: 3px solid ' + color + ';">';
                deviceHtml += '<div style="font-size: 13px; font-weight: bold;">' + device.name + '</div>';
                deviceHtml += '<div style="font-size: 11px; color: #aaa;">Seen by ' + device.seenBy + ' display(s)</div>';
                deviceHtml += '</div>';
            });
            deviceListSidebar.innerHTML = deviceHtml || '<p style="color: #666; font-size: 12px;">No devices detected...</p>';
        }

        function updateFloorPlan(data) {
            // Update or create display markers
            Object.keys(data.displays).forEach(function(id) {
                var display = data.displays[id];

                if (!displayMarkers[id]) {
                    // Create new marker
                    var marker = document.createElement('div');
                    marker.className = 'display-marker';
                    marker.dataset.id = id;
                    marker.textContent = display.name;
                    marker.style.left = display.x + 'px';
                    marker.style.top = display.y + 'px';

                    marker.addEventListener('mousedown', startDragMarker);

                    floorPlan.appendChild(marker);
                    displayMarkers[id] = marker;

                    // Add coverage circle
                    var circle = document.createElement('div');
                    circle.className = 'coverage-circle';
                    circle.style.width = '200px';
                    circle.style.height = '200px';
                    circle.style.left = (display.x - 100) + 'px';
                    circle.style.top = (display.y - 100) + 'px';
                    floorPlan.appendChild(circle);
                    displayMarkers[id + '_circle'] = circle;
                } else {
                    // Update existing marker
                    var marker = displayMarkers[id];
                    marker.textContent = display.name;
                    if (!marker.classList.contains('dragging')) {
                        marker.style.left = display.x + 'px';
                        marker.style.top = display.y + 'px';

                        // Update coverage circle
                        var circle = displayMarkers[id + '_circle'];
                        if (circle) {
                            circle.style.left = (display.x - 100) + 'px';
                            circle.style.top = (display.y - 100) + 'px';
                        }
                    }
                }
            });

            // Remove old device markers
            document.querySelectorAll('.device-marker').forEach(function(el) {
                el.remove();
            });

            // Draw device markers
            Object.keys(data.devices).forEach(function(address) {
                var device = data.devices[address];

                var marker = document.createElement('div');
                marker.className = 'device-marker ' + device.confidence;
                marker.style.left = device.x + 'px';
                marker.style.top = device.y + 'px';
                marker.title = device.name + ' (' + device.seenBy + ' displays)';

                var label = document.createElement('div');
                label.className = 'device-label';
                label.textContent = device.name.substring(0, 15);
                marker.appendChild(label);

                floorPlan.appendChild(marker);
            });

            document.getElementById('deviceCount').textContent = Object.keys(data.devices).length;
        }

        function updateStats(data) {
            document.getElementById('activeDisplays').textContent = Object.keys(data.displays).length;

            var configured = Object.values(data.displays).filter(function(d) { return d.configured; }).length;
            document.getElementById('configuredDisplays').textContent = configured;

            document.getElementById('totalDevices').textContent = Object.keys(data.devices).length;

            var highConf = Object.values(data.devices).filter(function(d) { return d.confidence === 'high'; }).length;
            document.getElementById('highConfidence').textContent = highConf;
        }

        function handleDragStart(e) {
            draggedDisplay = {
                id: e.target.dataset.id,
                name: e.target.querySelector('.display-name').textContent
            };
            e.dataTransfer.effectAllowed = 'move';
        }

        // Floor plan drop handling
        floorPlan.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
        });

        floorPlan.addEventListener('drop', function(e) {
            e.preventDefault();
            if (!draggedDisplay) return;

            var rect = floorPlan.getBoundingClientRect();
            var x = e.clientX - rect.left;
            var y = e.clientY - rect.top;

            updateDisplayPosition(draggedDisplay.id, x, y, draggedDisplay.name);
            draggedDisplay = null;
        });

        // Marker dragging
        var draggingMarker = null;
        var dragOffset = { x: 0, y: 0 };

        function startDragMarker(e) {
            draggingMarker = e.target;
            var rect = draggingMarker.getBoundingClientRect();
            dragOffset.x = e.clientX - rect.left;
            dragOffset.y = e.clientY - rect.top;
            draggingMarker.classList.add('dragging');

            document.addEventListener('mousemove', dragMarker);
            document.addEventListener('mouseup', stopDragMarker);
            e.preventDefault();
        }

        function dragMarker(e) {
            if (!draggingMarker) return;
            var rect = floorPlan.getBoundingClientRect();
            var x = e.clientX - rect.left - dragOffset.x;
            var y = e.clientY - rect.top - dragOffset.y;

            draggingMarker.style.left = x + 'px';
            draggingMarker.style.top = y + 'px';

            // Update coverage circle
            var circle = displayMarkers[draggingMarker.dataset.id + '_circle'];
            if (circle) {
                circle.style.left = (x - 100) + 'px';
                circle.style.top = (y - 100) + 'px';
            }
        }

        function stopDragMarker(e) {
            if (!draggingMarker) return;

            var rect = floorPlan.getBoundingClientRect();
            var x = e.clientX - rect.left - dragOffset.x;
            var y = e.clientY - rect.top - dragOffset.y;

            var displayId = draggingMarker.dataset.id;
            var displayName = draggingMarker.textContent;

            updateDisplayPosition(displayId, x, y, displayName);

            draggingMarker.classList.remove('dragging');
            draggingMarker = null;

            document.removeEventListener('mousemove', dragMarker);
            document.removeEventListener('mouseup', stopDragMarker);
        }

        function updateDisplayPosition(id, x, y, name) {
            fetch('/display/' + id + '/position', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ x: x, y: y, name: name })
            })
            .then(res => res.json())
            .then(data => {
                console.log('Updated position for', name);
                setTimeout(updateUI, 100);
            })
            .catch(err => console.error('Error updating position:', err));
        }

        // Rename display
        function renameDisplay(id) {
            // Get current name from the marker
            var currentName = displayMarkers[id] ? displayMarkers[id].textContent : id;
            var newName = prompt('Enter new name for display:', currentName);
            if (newName && newName.trim() && newName !== currentName) {
                fetch('/display/' + id + '/rename', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: newName.trim() })
                })
                .then(res => res.json())
                .then(data => {
                    console.log('Renamed display', id, 'to:', newName);
                    setTimeout(updateUI, 100);
                })
                .catch(err => console.error('Error renaming display:', err));
            }
        }

        // Delete display
        function deleteDisplay(id) {
            // Get display name from the marker
            var displayName = displayMarkers[id] ? displayMarkers[id].textContent : id;
            var confirmMsg = 'Are you sure you want to delete "' + displayName + '" (' + id + ')?\\n\\n';
            confirmMsg += 'This will:\\n';
            confirmMsg += '- Remove the display from the map\\n';
            confirmMsg += '- Delete saved position\\n';
            confirmMsg += '- Remove from triangulation\\n\\n';
            confirmMsg += 'The display will re-appear if the TV reconnects.';
            if (confirm(confirmMsg)) {
                fetch('/display/' + id, {
                    method: 'DELETE'
                })
                .then(res => res.json())
                .then(data => {
                    console.log('Deleted display', id);

                    // Remove marker from floor plan
                    if (displayMarkers[id]) {
                        displayMarkers[id].remove();
                        delete displayMarkers[id];
                    }
                    if (displayMarkers[id + '_circle']) {
                        displayMarkers[id + '_circle'].remove();
                        delete displayMarkers[id + '_circle'];
                    }

                    setTimeout(updateUI, 100);
                })
                .catch(err => console.error('Error deleting display:', err));
            }
        }

        // Floor plan upload handler
        document.getElementById('floorPlanUpload').addEventListener('change', function(e) {
            var file = e.target.files[0];
            if (!file) return;

            var formData = new FormData();
            formData.append('floorplan', file);

            fetch('/upload-floorplan', {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                console.log('Floor plan uploaded:', data);
                floorPlanImage.src = '/floorplan?' + Date.now();
                floorPlanImage.style.display = 'block';
                alert('Floor plan uploaded! Now click "Set Scale" to calibrate the measurements.');
            })
            .catch(err => console.error('Error uploading floor plan:', err));
        });

        // Scale calibration
        document.getElementById('calibrateBtn').addEventListener('click', function() {
            if (!floorPlanImage.src || floorPlanImage.style.display === 'none') {
                alert('Please upload a floor plan first!');
                return;
            }

            if (!isCalibrating) {
                startCalibration();
            } else {
                cancelCalibration();
            }
        });

        function startCalibration() {
            isCalibrating = true;
            calibrationPoints = [];
            floorPlan.classList.add('calibrating');
            document.getElementById('calibrateBtn').textContent = '❌ Cancel';
            document.getElementById('calibrateBtn').style.background = '#dc3545';

            var selectedUnit = document.getElementById('unitSelect').value;
            var unitLabel = unitLabels[selectedUnit];
            alert('Click two points on the floor plan to set a reference distance.\\n\\nExample: Click the start and end of a wall you know the length of.\\n\\nYou will enter the distance in ' + selectedUnit + ' (' + unitLabel + ').');
        }

        function cancelCalibration() {
            isCalibrating = false;
            calibrationPoints = [];
            floorPlan.classList.remove('calibrating');
            document.getElementById('calibrateBtn').textContent = '📏 Set Scale';
            document.getElementById('calibrateBtn').style.background = '#667eea';

            // Remove calibration visuals
            document.querySelectorAll('.calibration-line, .calibration-point').forEach(function(el) {
                el.remove();
            });
        }

        // Handle clicks for calibration
        floorPlan.addEventListener('click', function(e) {
            if (!isCalibrating) return;

            var rect = floorPlan.getBoundingClientRect();
            var x = e.clientX - rect.left;
            var y = e.clientY - rect.top;

            calibrationPoints.push({ x: x, y: y });

            // Draw point
            var point = document.createElement('div');
            point.className = 'calibration-point';
            point.style.left = x + 'px';
            point.style.top = y + 'px';
            floorPlan.appendChild(point);

            if (calibrationPoints.length === 2) {
                // Draw line
                var p1 = calibrationPoints[0];
                var p2 = calibrationPoints[1];
                var length = Math.sqrt(Math.pow(p2.x - p1.x, 2) + Math.pow(p2.y - p1.y, 2));
                var angle = Math.atan2(p2.y - p1.y, p2.x - p1.x) * 180 / Math.PI;

                var line = document.createElement('div');
                line.className = 'calibration-line';
                line.style.left = p1.x + 'px';
                line.style.top = p1.y + 'px';
                line.style.width = length + 'px';
                line.style.transform = 'rotate(' + angle + 'deg)';
                floorPlan.appendChild(line);

                // Get selected unit
                var selectedUnit = document.getElementById('unitSelect').value;
                var unitLabel = unitLabels[selectedUnit];

                // Ask for real-world distance
                var realDistance = prompt('Enter the real-world distance between these two points (in ' + selectedUnit + '):');
                if (realDistance && !isNaN(parseFloat(realDistance))) {
                    realDistance = parseFloat(realDistance);

                    // Convert to meters for internal calculations
                    var distanceInMeters = realDistance * unitConversions[selectedUnit];

                    scale = {
                        pixelsPerMeter: length / distanceInMeters,
                        pixelLength: length,
                        realWorldLength: realDistance,
                        unit: selectedUnit
                    };

                    // Save scale to server
                    fetch('/scale', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(scale)
                    })
                    .then(res => res.json())
                    .then(data => {
                        console.log('Scale saved:', data);
                        updateScaleInfo();
                        cancelCalibration();
                        alert('Scale calibrated!\\n\\n1 meter = ' + scale.pixelsPerMeter.toFixed(1) + ' pixels\\n1 ' + unitLabel + ' = ' + (scale.pixelsPerMeter * unitConversions[selectedUnit]).toFixed(1) + ' pixels');
                    })
                    .catch(err => console.error('Error saving scale:', err));
                } else {
                    alert('Invalid distance. Please try again.');
                    cancelCalibration();
                }
            }
        });

        function updateScaleInfo() {
            var scaleInfo = document.getElementById('scaleInfo');
            if (scale) {
                var unit = scale.unit || 'meters';
                var unitLabel = unitLabels[unit];
                var pixelsPerUnit = scale.pixelsPerMeter * unitConversions[unit];

                scaleInfo.innerHTML = '<div style="color: #00ff41;">✓ Scale calibrated</div>' +
                    '<div style="font-size: 11px; margin-top: 5px;">' +
                    scale.realWorldLength.toFixed(2) + ' ' + unitLabel + ' = ' + scale.pixelLength.toFixed(0) + ' pixels</div>' +
                    '<div style="font-size: 10px; color: #888;">1 ' + unitLabel + ' = ' + pixelsPerUnit.toFixed(1) + ' pixels</div>';

                // Set the dropdown to match the saved unit
                document.getElementById('unitSelect').value = unit;
            } else {
                scaleInfo.innerHTML = '<div>No scale set</div>' +
                    '<div style="font-size: 10px; margin-top: 5px;">Upload a floor plan and click "Set Scale" to calibrate</div>';
            }
        }

        // Load scale on startup
        fetch('/scale')
            .then(res => res.json())
            .then(data => {
                if (data.scale) {
                    scale = data.scale;
                    updateScaleInfo();
                }
                if (data.hasFloorplan) {
                    floorPlanImage.src = '/floorplan?' + Date.now();
                    floorPlanImage.style.display = 'block';
                }
            })
            .catch(err => console.log('No saved scale or floor plan'));

        // Auto-refresh
        updateUI();
        setInterval(updateUI, 2000);
    </script>
</body>
</html>`;

    res.writeHead(200, {'Content-Type': 'text/html'});
    res.end(html);
}
