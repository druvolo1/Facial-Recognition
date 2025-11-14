// CENTRAL AGGREGATION SERVER
// Collects data from multiple BiometriX displays and triangulates device positions

var http = require('http');

// Store data from all displays
var displays = {};  // { displayId: { name, x, y, lastUpdate, devices } }
var triangulatedDevices = {};  // { deviceAddress: { x, y, confidence, seenBy } }

// Configuration
var config = {
    port: 4000,
    updateInterval: 3000  // Recalculate positions every 3 seconds
};

console.log('===== CENTRAL TRILATERATION SERVER STARTING =====');

// Start HTTP server
var server = http.createServer(function(req, res) {
    var url = req.url;

    // CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
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

    // Route: GET / - Main viewer
    if (url === '/' || url === '/index.html') {
        serveViewer(res);
        return;
    }

    // Route: GET /map-data - Get triangulated positions
    if (url === '/map-data' && req.method === 'GET') {
        res.writeHead(200, {'Content-Type': 'application/json'});
        res.end(JSON.stringify({
            displays: displays,
            devices: triangulatedDevices,
            timestamp: new Date().toISOString()
        }));
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
                    lastUpdate: displays[id].lastUpdate
                };
            })
        }, null, 2));
        return;
    }

    // 404
    res.writeHead(404, {'Content-Type': 'text/plain'});
    res.end('Not Found');
});

server.listen(config.port, '0.0.0.0', function() {
    console.log('✅ Central Server running on port', config.port);
    console.log('✅ Displays should POST to: http://10.20.10.192:4000/report');
    console.log('✅ View map at: http://10.20.10.192:4000/');
});

// Handle data from a display
function handleDisplayReport(data) {
    var displayId = data.displayId;

    displays[displayId] = {
        name: data.displayName || 'Display ' + displayId,
        x: data.position.x,
        y: data.position.y,
        devices: data.devices || [],
        lastUpdate: new Date().toISOString()
    };

    console.log('📡 Report from', displays[displayId].name, '- Position:', data.position.x + ',' + data.position.y, '- Devices:', data.devices.length);

    // Trigger triangulation
    triangulateDevices();
}

// Convert RSSI to distance estimate (meters)
function rssiToDistance(rssi, txPower) {
    // txPower = RSSI at 1 meter (typically -59 for BLE)
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
    var deviceReadings = {};  // { address: [{displayId, x, y, rssi, distance}] }

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
            // Only one display sees it - just show near that display
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
            // Two displays - use midpoint weighted by signal strength
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
            // Three or more displays - use full trilateration
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

    console.log('📍 Triangulated', Object.keys(triangulatedDevices).length, 'devices');
}

function trilaterateFromTwo(readings) {
    var r1 = readings[0];
    var r2 = readings[1];

    // Weight by inverse distance
    var w1 = 1 / (r1.distance + 0.1);
    var w2 = 1 / (r2.distance + 0.1);
    var totalWeight = w1 + w2;

    return {
        x: (r1.x * w1 + r2.x * w2) / totalWeight,
        y: (r1.y * w1 + r2.y * w2) / totalWeight
    };
}

function trilaterateFromMultiple(readings) {
    // Least squares trilateration
    var n = readings.length;

    // Use weighted centroid based on signal strength
    var sumX = 0, sumY = 0, sumW = 0;

    readings.forEach(function(r) {
        var weight = 1 / (r.distance + 0.1);  // Closer = more weight
        sumX += r.x * weight;
        sumY += r.y * weight;
        sumW += weight;
    });

    return {
        x: sumX / sumW,
        y: sumY / sumW
    };
}

function serveViewer(res) {
    var html = `<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>BiometriX - Multi-Display Position Map</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .container {
            max-width: 1600px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 {
            color: #667eea;
            font-size: 48px;
            margin: 0 0 10px 0;
        }
        .subtitle {
            color: #999;
            font-size: 18px;
            margin-bottom: 30px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }
        .stat-value {
            font-size: 48px;
            font-weight: bold;
            margin: 10px 0;
        }
        .stat-label {
            font-size: 14px;
            opacity: 0.9;
            text-transform: uppercase;
        }
        .map-container {
            background: #1a1a2e;
            border-radius: 12px;
            padding: 20px;
            margin: 30px 0;
        }
        .map-title {
            color: white;
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 20px;
            text-align: center;
        }
        #positionMap {
            display: block;
            margin: 0 auto;
            background: #0f0f1e;
            border: 2px solid #667eea;
        }
        .legend {
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-top: 20px;
            flex-wrap: wrap;
        }
        .legend-item {
            color: white;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .legend-icon {
            width: 20px;
            height: 20px;
        }
        .device-details {
            margin-top: 30px;
        }
        .device-card {
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🗺️ BiometriX Multi-Display Position Map</h1>
        <div class="subtitle">Triangulated device positions from multiple displays</div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-label">Active Displays</div>
                <div class="stat-value" id="displayCount">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Devices Found</div>
                <div class="stat-value" id="deviceCount">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">High Confidence</div>
                <div class="stat-value" id="highConfidence">0</div>
            </div>
        </div>

        <div class="map-container">
            <div class="map-title">Floor Plan Position Map</div>
            <canvas id="positionMap" width="1200" height="800"></canvas>
            <div class="legend">
                <div class="legend-item">
                    <div class="legend-icon" style="background: #00bcd4; border-radius: 4px;"></div>
                    <span>Display/TV</span>
                </div>
                <div class="legend-item">
                    <div class="legend-icon" style="background: #00ff41; border-radius: 50%;"></div>
                    <span>High Confidence (3+ displays)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-icon" style="background: #ffeb3b; border-radius: 50%;"></div>
                    <span>Medium Confidence (2 displays)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-icon" style="background: #f44336; border-radius: 50%;"></div>
                    <span>Low Confidence (1 display)</span>
                </div>
            </div>
        </div>

        <div id="deviceDetails" class="device-details"></div>
    </div>

    <script>
        var canvas = document.getElementById('positionMap');
        var ctx = canvas.getContext('2d');

        function drawMap(data) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Draw grid
            ctx.strokeStyle = 'rgba(100, 200, 255, 0.1)';
            ctx.lineWidth = 1;
            for (var x = 0; x < canvas.width; x += 50) {
                ctx.beginPath();
                ctx.moveTo(x, 0);
                ctx.lineTo(x, canvas.height);
                ctx.stroke();
            }
            for (var y = 0; y < canvas.height; y += 50) {
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(canvas.width, y);
                ctx.stroke();
            }

            // Draw displays
            Object.keys(data.displays).forEach(function(id) {
                var display = data.displays[id];
                var x = display.x;
                var y = display.y;

                // Display rectangle
                ctx.fillStyle = '#00bcd4';
                ctx.fillRect(x - 25, y - 15, 50, 30);
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 2;
                ctx.strokeRect(x - 25, y - 15, 50, 30);

                // Display label
                ctx.fillStyle = '#fff';
                ctx.font = 'bold 12px Arial';
                ctx.textAlign = 'center';
                ctx.fillText(display.name, x, y + 5);

                // Coverage radius
                ctx.beginPath();
                ctx.arc(x, y, 100, 0, 2 * Math.PI);
                ctx.strokeStyle = 'rgba(0, 188, 212, 0.2)';
                ctx.lineWidth = 1;
                ctx.stroke();
            });

            // Draw triangulated devices
            Object.keys(data.devices).forEach(function(address) {
                var device = data.devices[address];
                var x = device.x;
                var y = device.y;

                // Color by confidence
                var color;
                if (device.confidence === 'high') color = '#00ff41';
                else if (device.confidence === 'medium') color = '#ffeb3b';
                else color = '#f44336';

                // Device dot
                ctx.beginPath();
                ctx.arc(x, y, 10, 0, 2 * Math.PI);
                ctx.fillStyle = color;
                ctx.fill();
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 2;
                ctx.stroke();

                // Device label
                ctx.fillStyle = '#fff';
                ctx.font = '11px Arial';
                ctx.textAlign = 'center';
                ctx.fillText(device.name.substring(0, 12), x, y - 15);

                // Confidence indicator
                ctx.font = '9px Arial';
                ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
                ctx.fillText(device.seenBy + ' TVs', x, y + 25);

                // Draw lines to displays that see it
                device.readings.forEach(function(reading) {
                    var display = data.displays[reading.displayId];
                    if (display) {
                        ctx.beginPath();
                        ctx.moveTo(x, y);
                        ctx.lineTo(display.x, display.y);
                        ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
                        ctx.lineWidth = 1;
                        ctx.stroke();
                    }
                });
            });

            ctx.textAlign = 'left';
        }

        function updateData() {
            fetch('/map-data')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('displayCount').textContent = Object.keys(data.displays).length;
                    document.getElementById('deviceCount').textContent = Object.keys(data.devices).length;

                    var highConf = Object.values(data.devices).filter(d => d.confidence === 'high').length;
                    document.getElementById('highConfidence').textContent = highConf;

                    drawMap(data);

                    // Device details
                    var detailsHtml = '<h2 style="color: #667eea;">Device Details</h2>';
                    Object.values(data.devices).forEach(function(device) {
                        detailsHtml += '<div class="device-card">';
                        detailsHtml += '<strong>' + device.name + '</strong> (' + device.address + ')<br>';
                        detailsHtml += 'Position: (' + device.x.toFixed(0) + ', ' + device.y.toFixed(0) + ')<br>';
                        detailsHtml += 'Confidence: ' + device.confidence + ' (seen by ' + device.seenBy + ' displays)<br>';
                        detailsHtml += 'Readings:<br>';
                        device.readings.forEach(function(r) {
                            detailsHtml += '&nbsp;&nbsp;- ' + r.displayName + ': ' + r.rssi + ' dBm (~' + r.distance.toFixed(1) + 'm)<br>';
                        });
                        detailsHtml += '</div>';
                    });
                    document.getElementById('deviceDetails').innerHTML = detailsHtml;
                })
                .catch(err => console.error('Error:', err));
        }

        updateData();
        setInterval(updateData, 3000);
    </script>
</body>
</html>`;

    res.writeHead(200, {'Content-Type': 'text/html'});
    res.end(html);
}
