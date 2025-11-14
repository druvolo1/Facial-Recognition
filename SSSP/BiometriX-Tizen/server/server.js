var messageManager = (function () {
    var localMsgPort;
    var remoteMsgPort;
    var listenerId;
    var bodyParser = null;
    var portServer = 3000;

    var express = null;
    var app = null;
    var server = null;
    var io = null;
    var cors = null;

    // Store the latest frame for streaming
    var latestFrame = null;
    var connectedClients = 0;

    function init() {
        console.log('===== BACKGROUND SERVICE INIT STARTING =====');

        // *** PRIORITY 1: Initialize Message Port FIRST (before anything else) ***
        // This ensures foreground app knows service is alive even if Node modules fail
        var messagePortName = 'BIOMETRIX_STREAM_COMMUNICATION';
        var calleeAppId = 'PM9QIwqaCE.BiometriX';

        console.log('Initializing Message Port...');
        console.log('Port Name:', messagePortName);
        console.log('Callee App ID:', calleeAppId);

        try {
            // Create local message port first
            localMsgPort = tizen.messageport.requestLocalMessagePort(messagePortName);
            console.log('Local message port created');

            listenerId = localMsgPort.addMessagePortListener(onMessageReceived);
            console.log('Message port listener added');

            // Request remote message port to foreground app
            remoteMsgPort = tizen.messageport.requestRemoteMessagePort(
                calleeAppId,
                messagePortName
            );
            console.log('Remote message port requested');

            // *** IMMEDIATELY send started command ***
            sendCommand('started');
            console.log('Started command sent');
        } catch(e) {
            console.error('CRITICAL: Message Port init failed:', e);
            console.error('Error name:', e.name);
            console.error('Error message:', e.message);
            // Don't continue if Message Port fails
            return;
        }

        // *** PRIORITY 2: Initialize Node.js modules (can fail safely now) ***
        try {
            console.log('Loading Node.js modules...');

            express = require('express');
            cors = require('cors');
            app = express();
            server = require('http').Server(app);
            io = require('socket.io')(server);
            fs = require('fs');
            path = require('path');
            bodyParser = require('body-parser');

            console.log('Node modules loaded successfully');
            sendMessage('Server modules loaded');
        } catch(e) {
            console.error('ERROR: Failed to load Node modules:', e);
            sendMessage('ERROR: Node modules failed - ' + e.message);
            // Continue anyway - at least Message Port works
            return;
        }

        // *** PRIORITY 3: Configure Express server ***
        try {
            console.log('Configuring Express server...');

            // Configure CORS - Allow all origins
            app.use(cors({
                origin: '*',
                methods: ['GET', 'POST'],
                credentials: true
            }));

            var jsonParser = bodyParser.json({ limit: '50mb' });
            var urlencodedParser = bodyParser.urlencoded({ extended: false, limit: '50mb' });

            app.use(jsonParser);
            app.use(urlencodedParser);

            // Serve the viewer page
            app.get('/', function(req, res) {
                res.sendFile(path.join(__dirname, 'viewer.html'));
            });

            // API endpoint to get stream status
            app.get('/status', function(req, res) {
                res.json({
                    status: 'running',
                    connectedClients: connectedClients,
                    hasFrame: latestFrame !== null,
                    frameSize: latestFrame ? latestFrame.length : 0,
                    timestamp: Date.now()
                });
            });

            console.log('Express routes configured');
        } catch(e) {
            console.error('ERROR: Express configuration failed:', e);
            sendMessage('ERROR: Express config failed - ' + e.message);
            return;
        }

        // *** PRIORITY 4: Initialize Socket.IO ***
        try {
            console.log('Setting up Socket.IO...');

            io.on('connection', function(socket) {
                connectedClients++;
                console.log('Client connected. Total clients:', connectedClients);
                sendMessage('Client connected. Total: ' + connectedClients);

                // Send the latest frame immediately if available
                if (latestFrame) {
                    socket.emit('frame', latestFrame);
                }

                socket.on('disconnect', function() {
                    connectedClients--;
                    console.log('Client disconnected. Total clients:', connectedClients);
                    sendMessage('Client disconnected. Total: ' + connectedClients);
                });

                socket.on('error', function(err) {
                    console.error('Socket error:', err);
                });
            });

            console.log('Socket.IO configured');
        } catch(e) {
            console.error('ERROR: Socket.IO setup failed:', e);
            sendMessage('ERROR: Socket.IO failed - ' + e.message);
            return;
        }

        // *** PRIORITY 5: Start HTTP server ***
        try {
            console.log('Starting HTTP server on port', portServer);

            server.listen(portServer, '0.0.0.0', function() {
                console.log('✅ BiometriX Stream Server running on port', portServer);
                console.log('✅ Access viewer at http://[TV_IP]:3000/');
                console.log('✅ Node version:', process.version);
                sendMessage('Stream server started on port ' + portServer);
            });
        } catch(e) {
            console.error('ERROR: HTTP server start failed:', e);
            sendMessage('ERROR: Server start failed - ' + e.message);
            return;
        }

        console.log('===== BACKGROUND SERVICE INIT COMPLETE =====');
    }

    function sendCommand(msg) {
        // Send command to foreground app
        console.log('sendCommand called with:', msg);
        if (remoteMsgPort) {
            var messageData = {
                key: 'Command',
                value: msg
            };
            try {
                remoteMsgPort.sendMessage([messageData]);
                console.log('Command sent successfully:', msg);
            } catch(e) {
                console.error('Error sending command:', e);
                console.error('Error details:', e.name, e.message);
            }
        } else {
            console.error('remoteMsgPort is null, cannot send command');
        }
    }

    function sendMessage(msg) {
        // Send logs to foreground application
        if (remoteMsgPort) {
            var messageData = {
                key: 'LOG',
                value: '[' + Date.now() + '] ' + msg
            };
            try {
                remoteMsgPort.sendMessage([messageData]);
            } catch(e) {
                console.error('Error sending message:', e);
            }
        }
    }

    function close() {
        if (localMsgPort && listenerId) {
            localMsgPort.removeMessagePortListener(listenerId);
        }
        if (server) {
            server.close();
        }
    }

    function onMessageReceived(data) {
        if (!data || data.length === 0) return;

        var messageKey = data[0].key;

        // Only log non-frame messages to avoid spam
        if (messageKey !== 'frame') {
            console.log('Message received:', messageKey);
            sendMessage('BG service received: ' + messageKey);
        }

        switch (messageKey) {
            case 'frame':
                // Receive frame data from foreground via message port
                latestFrame = data[0].value;

                // Broadcast to all connected Socket.IO clients
                if (connectedClients > 0) {
                    io.emit('frame', latestFrame);
                }

                // Log first frame only
                if (!latestFrame || latestFrame.length === 0) {
                    console.log('First frame received, size:', data[0].value ? data[0].value.length : 0, 'bytes');
                }
                break;

            case 'test':
                sendMessage('Test message received successfully!');
                break;

            case 'getStatus':
                sendMessage('Status - Clients: ' + connectedClients + ', HasFrame: ' + (latestFrame !== null));
                break;

            case 'terminate':
                sendMessage('Terminating background service...');
                close();
                tizen.application.getCurrentApplication().exit();
                break;

            default:
                sendMessage('Unknown command: ' + messageKey);
        }
    }

    return {
        init: init,
        sendMessage: sendMessage,
        sendCommand: sendCommand
    };
})();

// Required exports for Tizen background service
module.exports.onStart = function () {
    console.log('Background service starting...');
    messageManager.init();
};

module.exports.onRequest = function () {
    console.log('Background service onRequest called');
    var reqAppControl = tizen.application.getCurrentApplication().getRequestedAppControl();

    if (reqAppControl && reqAppControl.appControl.operation == "http://tizen.org/appcontrol/operation/pick") {
        var data = reqAppControl.appControl.data;
        if (data && data[0] && data[0].value[0] == 'BiometriX') {
            console.log('Request from BiometriX app');
        }
    }
};

module.exports.onExit = function () {
    console.log('Background service exiting...');
    messageManager.sendCommand('terminated');
};
