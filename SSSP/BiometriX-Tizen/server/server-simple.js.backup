// SIMPLE BACKGROUND SERVICE FOR BLUETOOTH DATA
// Uses ONLY built-in Node.js modules

var messageManager = (function () {
    var localMsgPort;
    var remoteMsgPort;
    var listenerId;

    // Built-in Node.js modules only
    var http = require('http');
    var url = require('url');
    var crypto = require('crypto');

    // Server data
    var serverStartTime = Date.now();

    // WebSocket clients and WebRTC connections
    var wsClients = [];
    var pendingOffers = {};

    function init() {
        console.log('===== WEBRTC DVR SERVICE STARTING =====');

        // STEP 1: Initialize Message Port FIRST
        var messagePortName = 'WEBRTC_DVR_COMMUNICATION';
        var calleeAppId = 'Cl037gx83e.WebRtcServerDVR';

        console.log('Initializing Message Port...');

        try {
            localMsgPort = tizen.messageport.requestLocalMessagePort(messagePortName);
            console.log('[OK] Local message port created');

            listenerId = localMsgPort.addMessagePortListener(onMessageReceived);
            console.log('[OK] Message port listener added');

            remoteMsgPort = tizen.messageport.requestRemoteMessagePort(calleeAppId, messagePortName);
            console.log('[OK] Remote message port requested');

            // Wait 200ms for port to be fully registered
            setTimeout(function() {
                sendCommand('started');
                console.log('[OK] Started command sent to foreground');
            }, 200);

        } catch(e) {
            console.error('[ERROR] CRITICAL: Message Port failed:', e.message);
            return;
        }

        // STEP 2: Start HTTP server with WebSocket support
        try {
            console.log('Starting HTTP server...');

            var server = http.createServer(function(req, res) {
                handleRequest(req, res);
            });

            // WebSocket upgrade handling
            server.on('upgrade', function(request, socket, head) {
                console.log('[WebSocket] Upgrade request received');
                handleWebSocketUpgrade(request, socket, head);
            });

            server.listen(3000, '0.0.0.0', function() {
                console.log('[OK] HTTP Server running on port 3000');
                console.log('[OK] WebSocket Server ready on ws://[TV_IP]:3000/ws');
                console.log('[OK] Access: http://[TV_IP]:3000/');
            });

            server.on('error', function(err) {
                console.error('[ERROR] HTTP Server error:', err.message);
            });

        } catch(e) {
            console.error('[ERROR] Failed to start HTTP server:', e.message);
        }

        console.log('===== SERVICE INIT COMPLETE =====');
    }

    function handleRequest(req, res) {
        var reqUrl = req.url;

        console.log('HTTP Request:', req.method, reqUrl);

        // CORS headers
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

        if (req.method === 'OPTIONS') {
            res.writeHead(200);
            res.end();
            return;
        }

        // Route: GET /
        if (reqUrl === '/' || reqUrl === '/index.html') {
            serveViewer(res);
            return;
        }

        // Route: GET /status
        if (reqUrl === '/status' && req.method === 'GET') {
            var status = {
                status: 'running',
                port: 3000,
                uptime: Math.floor((Date.now() - serverStartTime) / 1000),
                message: 'WebRTC DVR Server is running',
                wsConnections: wsClients.length
            };

            res.writeHead(200, {'Content-Type': 'application/json'});
            res.end(JSON.stringify(status, null, 2));
            return;
        }

        // 404 Not Found
        res.writeHead(404, {'Content-Type': 'text/plain'});
        res.end('Not Found');
    }

    function serveViewer(res) {
        var html = '<!DOCTYPE html>' +
            '<html>' +
            '<head>' +
            '<meta charset="utf-8">' +
            '<title>WebRTC DVR Server - Live View</title>' +
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">' +
            '<style>' +
            '* { margin: 0; padding: 0; box-sizing: border-box; }' +
            'body {' +
            '  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;' +
            '  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);' +
            '  color: #fff;' +
            '  min-height: 100vh;' +
            '  padding: 20px;' +
            '}' +
            '.container {' +
            '  max-width: 1200px;' +
            '  margin: 0 auto;' +
            '  background: rgba(255,255,255,0.15);' +
            '  backdrop-filter: blur(10px);' +
            '  border-radius: 20px;' +
            '  padding: 40px;' +
            '  box-shadow: 0 10px 40px rgba(0,0,0,0.3);' +
            '}' +
            'h1 { font-size: 3em; margin-bottom: 20px; text-align: center; }' +
            '.video-container {' +
            '  background: #000;' +
            '  border-radius: 15px;' +
            '  padding: 10px;' +
            '  margin: 30px auto;' +
            '  box-shadow: 0 10px 40px rgba(0,0,0,0.5);' +
            '  max-width: 800px;' +
            '}' +
            '#liveImage {' +
            '  width: 100%;' +
            '  height: auto;' +
            '  border-radius: 10px;' +
            '  display: block;' +
            '}' +
            '.placeholder {' +
            '  text-align: center;' +
            '  padding: 100px 20px;' +
            '  color: rgba(255,255,255,0.7);' +
            '}' +
            '.stats {' +
            '  display: grid;' +
            '  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));' +
            '  gap: 15px;' +
            '  margin-top: 30px;' +
            '}' +
            '.stat {' +
            '  padding: 20px;' +
            '  background: rgba(255,255,255,0.2);' +
            '  border-radius: 12px;' +
            '  text-align: center;' +
            '}' +
            '.stat-label { font-size: 0.9em; opacity: 0.8; margin-bottom: 8px; }' +
            '.stat-value { font-size: 2em; font-weight: bold; }' +
            '.ws-status { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-left: 8px; }' +
            '.ws-status.connected { background: #44ff44; }' +
            '.ws-status.disconnected { background: #ff4444; }' +
            '</style>' +
            '</head>' +
            '<body>' +
            '<div class="container">' +
            '<h1>WebRTC DVR Server - Live View</h1>' +
            '<div class="video-container">' +
            '<img id="liveImage" style="display:none;" alt="Live Camera Feed">' +
            '<div id="placeholder" class="placeholder">' +
            '<div style="font-size: 60px;">📹</div>' +
            '<h2>Waiting for Camera Frames...</h2>' +
            '<p>Connect from the Tizen display to start streaming</p>' +
            '</div>' +
            '</div>' +
            '<div class="stats">' +
            '<div class="stat">' +
            '<div class="stat-label">Server Status</div>' +
            '<div class="stat-value" id="serverStatus">Active</div>' +
            '</div>' +
            '<div class="stat">' +
            '<div class="stat-label">WebSocket <span class="ws-status" id="wsIndicator"></span></div>' +
            '<div class="stat-value" id="wsStatus">Connecting...</div>' +
            '</div>' +
            '<div class="stat">' +
            '<div class="stat-label">Frames Received</div>' +
            '<div class="stat-value" id="frameCount">0</div>' +
            '</div>' +
            '<div class="stat">' +
            '<div class="stat-label">Last Update</div>' +
            '<div class="stat-value" id="lastUpdate" style="font-size: 1.2em;">Never</div>' +
            '</div>' +
            '</div>' +
            '</div>' +
            '<script>' +
            'var ws = null;' +
            'var frameCount = 0;' +
            'var liveImage = document.getElementById("liveImage");' +
            'var placeholder = document.getElementById("placeholder");' +
            'var frameCountEl = document.getElementById("frameCount");' +
            'var lastUpdateEl = document.getElementById("lastUpdate");' +
            'var wsStatusEl = document.getElementById("wsStatus");' +
            'var wsIndicator = document.getElementById("wsIndicator");' +
            '' +
            'function connectWebSocket() {' +
            '  console.log("Connecting to WebSocket...");' +
            '  ws = new WebSocket("ws://" + window.location.host + "/ws");' +
            '' +
            '  ws.onopen = function() {' +
            '    console.log("WebSocket connected");' +
            '    wsStatusEl.textContent = "Connected";' +
            '    wsIndicator.className = "ws-status connected";' +
            '  };' +
            '' +
            '  ws.onmessage = function(event) {' +
            '    try {' +
            '      var message = JSON.parse(event.data);' +
            '      if (message.type === "frame" && message.data) {' +
            '        frameCount++;' +
            '        liveImage.src = message.data;' +
            '        liveImage.style.display = "block";' +
            '        placeholder.style.display = "none";' +
            '        frameCountEl.textContent = frameCount;' +
            '        var now = new Date();' +
            '        lastUpdateEl.textContent = now.toLocaleTimeString();' +
            '        console.log("Frame", frameCount, "received");' +
            '      }' +
            '    } catch(e) {' +
            '      console.error("Failed to parse message:", e);' +
            '    }' +
            '  };' +
            '' +
            '  ws.onerror = function(error) {' +
            '    console.error("WebSocket error:", error);' +
            '    wsStatusEl.textContent = "Error";' +
            '    wsIndicator.className = "ws-status disconnected";' +
            '  };' +
            '' +
            '  ws.onclose = function() {' +
            '    console.log("WebSocket closed, reconnecting...");' +
            '    wsStatusEl.textContent = "Reconnecting...";' +
            '    wsIndicator.className = "ws-status disconnected";' +
            '    setTimeout(connectWebSocket, 3000);' +
            '  };' +
            '}' +
            '' +
            'connectWebSocket();' +
            '' +
            'fetch("/status")' +
            '  .then(res => res.json())' +
            '  .then(data => {' +
            '    document.getElementById("serverStatus").textContent = data.status.toUpperCase();' +
            '  })' +
            '  .catch(err => console.error(err));' +
            '</script>' +
            '</body>' +
            '</html>';

        res.writeHead(200, {'Content-Type': 'text/html'});
        res.end(html);
    }

    // ===== WebSocket Functions =====

    function handleWebSocketUpgrade(request, socket, head) {
        var key = request.headers['sec-websocket-key'];
        if (!key) {
            socket.end('HTTP/1.1 400 Bad Request\r\n\r\n');
            return;
        }

        var acceptKey = crypto
            .createHash('sha1')
            .update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11')
            .digest('base64');

        var headers = [
            'HTTP/1.1 101 Switching Protocols',
            'Upgrade: websocket',
            'Connection: Upgrade',
            'Sec-WebSocket-Accept: ' + acceptKey,
            ''
        ];

        socket.write(headers.join('\r\n') + '\r\n');

        var client = {
            socket: socket,
            buffer: Buffer.alloc(0)
        };

        wsClients.push(client);
        console.log('[WebSocket] Client connected. Total clients:', wsClients.length);

        socket.on('data', function(data) {
            handleWebSocketData(client, data);
        });

        socket.on('close', function() {
            var index = wsClients.indexOf(client);
            if (index > -1) {
                wsClients.splice(index, 1);
            }
            console.log('[WebSocket] Client disconnected. Total clients:', wsClients.length);
        });

        socket.on('error', function(err) {
            console.error('[WebSocket] Socket error:', err.message);
        });
    }

    function handleWebSocketData(client, data) {
        client.buffer = Buffer.concat([client.buffer, data]);

        while (client.buffer.length >= 2) {
            var firstByte = client.buffer[0];
            var secondByte = client.buffer[1];

            var isFin = (firstByte & 0x80) !== 0;
            var opcode = firstByte & 0x0F;
            var isMasked = (secondByte & 0x80) !== 0;
            var payloadLen = secondByte & 0x7F;

            var offset = 2;

            if (payloadLen === 126) {
                if (client.buffer.length < offset + 2) return;
                payloadLen = client.buffer.readUInt16BE(offset);
                offset += 2;
            } else if (payloadLen === 127) {
                if (client.buffer.length < offset + 8) return;
                payloadLen = client.buffer.readUInt32BE(offset + 4);
                offset += 8;
            }

            var maskingKey = null;
            if (isMasked) {
                if (client.buffer.length < offset + 4) return;
                maskingKey = client.buffer.slice(offset, offset + 4);
                offset += 4;
            }

            if (client.buffer.length < offset + payloadLen) return;

            var payload = client.buffer.slice(offset, offset + payloadLen);
            client.buffer = client.buffer.slice(offset + payloadLen);

            if (isMasked && maskingKey) {
                for (var i = 0; i < payload.length; i++) {
                    payload[i] ^= maskingKey[i % 4];
                }
            }

            if (opcode === 0x1) { // Text frame
                try {
                    var message = JSON.parse(payload.toString('utf8'));
                    handleWebSocketMessage(client, message);
                } catch(e) {
                    console.error('[WebSocket] Failed to parse message:', e.message);
                }
            } else if (opcode === 0x8) { // Close frame
                client.socket.end();
                return;
            } else if (opcode === 0x9) { // Ping frame
                sendWebSocketFrame(client, payload, 0xA); // Pong
            }
        }
    }

    function sendWebSocketFrame(client, data, opcode) {
        var payload = typeof data === 'string' ? Buffer.from(data, 'utf8') : data;
        var length = payload.length;

        var frame;
        var offset;

        if (length < 126) {
            frame = Buffer.alloc(2 + length);
            frame[0] = 0x80 | (opcode || 0x1);
            frame[1] = length;
            offset = 2;
        } else if (length < 65536) {
            frame = Buffer.alloc(4 + length);
            frame[0] = 0x80 | (opcode || 0x1);
            frame[1] = 126;
            frame.writeUInt16BE(length, 2);
            offset = 4;
        } else {
            frame = Buffer.alloc(10 + length);
            frame[0] = 0x80 | (opcode || 0x1);
            frame[1] = 127;
            frame.writeUInt32BE(0, 2);
            frame.writeUInt32BE(length, 6);
            offset = 10;
        }

        payload.copy(frame, offset);

        try {
            client.socket.write(frame);
        } catch(e) {
            console.error('[WebSocket] Failed to send frame:', e.message);
        }
    }

    function handleWebSocketMessage(client, message) {
        console.log('[WebSocket] Received message type:', message.type);

        if (message.type === 'frame') {
            // Received a frame from the client
            handleFrameData(message.data);
        } else if (message.type === 'recognition_result') {
            // Recognition results from processing
            broadcastToForeground(message);
        } else {
            console.log('[WebSocket] Unknown message type:', message.type);
        }
    }

    function broadcastToForeground(message) {
        // Send recognition results to foreground app via message port
        if (remoteMsgPort && message.faces) {
            try {
                remoteMsgPort.sendMessage([
                    {key: 'Command', value: 'recognition_result'},
                    {key: 'Data', value: JSON.stringify(message.faces)}
                ]);
                console.log('[OK] Recognition results sent to foreground');
            } catch(e) {
                console.error('[ERROR] Failed to send recognition results:', e.message);
            }
        }
    }

    function handleFrameData(frameData) {
        console.log('[Frame] Received frame data, size:', frameData.length);

        // Broadcast frame to all WebSocket viewers immediately
        wsClients.forEach(function(client) {
            sendWebSocketFrame(client, JSON.stringify({
                type: 'frame',
                data: frameData,
                timestamp: Date.now()
            }));
        });
        console.log('[Frame] Broadcasted to', wsClients.length, 'viewer(s)');

        // Send frame to facial recognition server
        var http = require('http');
        var postData = JSON.stringify({
            display_id: 'lobby_display_01',
            location: 'Front Lobby',
            image: frameData
        });

        var options = {
            hostname: '172.16.1.150',
            port: 5000,
            path: '/api/displays/recognize',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(postData)
            }
        };

        var req = http.request(options, function(res) {
            var responseData = '';

            res.on('data', function(chunk) {
                responseData += chunk;
            });

            res.on('end', function() {
                try {
                    var result = JSON.parse(responseData);
                    console.log('[Recognition] Success:', result.success, 'Faces:', result.faces ? result.faces.length : 0);

                    if (result.success && result.faces && result.faces.length > 0) {
                        // Send results back to all WebSocket clients
                        wsClients.forEach(function(client) {
                            sendWebSocketFrame(client, JSON.stringify({
                                type: 'recognition_result',
                                faces: result.faces
                            }));
                        });

                        // Also send to foreground app
                        broadcastToForeground(result);
                    }
                } catch(e) {
                    console.error('[Recognition] Failed to parse response:', e.message);
                }
            });
        });

        req.on('error', function(err) {
            console.error('[Recognition] Request error:', err.message);
        });

        req.write(postData);
        req.end();
    }

    // ===== Message Port Functions =====

    function sendCommand(msg) {
        console.log('sendCommand:', msg);
        if (remoteMsgPort) {
            try {
                remoteMsgPort.sendMessage([{key: 'Command', value: msg}]);
                console.log('[OK] Command sent:', msg);
            } catch(e) {
                console.error('[ERROR] Send command failed:', e.message);
            }
        }
    }

    function onMessageReceived(data) {
        if (!data || data.length === 0) return;

        var messageKey = data[0].key;

        console.log('Message received:', messageKey);

        switch (messageKey) {
            case 'test':
                console.log('Test message received');
                break;

            case 'terminate':
                console.log('Terminate command received');
                if (localMsgPort && listenerId) {
                    localMsgPort.removeMessagePortListener(listenerId);
                }
                tizen.application.getCurrentApplication().exit();
                break;

            default:
                console.log('Unknown message:', messageKey);
        }
    }

    return {
        init: init,
        sendCommand: sendCommand
    };
})();

// Tizen background service exports
module.exports.onStart = function () {
    console.log('=== onStart called ===');
    messageManager.init();
};

module.exports.onRequest = function () {
    console.log('=== onRequest called ===');
};

module.exports.onExit = function () {
    console.log('=== onExit called ===');
    messageManager.sendCommand('terminated');
};
