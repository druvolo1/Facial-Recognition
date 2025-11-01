var currentURL;
var b2brtpplay;
var rtpPlayer;
var keyTest;

//Initialize function
var init = function () {
    // TODO:: Do your initialization job
    log('init() called');

    var config = {
        url: '',
        player: document.getElementById('av-player'),
        controls: document.querySelector('.video-controls'),
        resolutionWidth: 1920,
        logger: log //Function used for logging
    };

    if (!currentURL) {
        document.getElementById('currentURL').innerHTML = 'NONE';
    }

    try {

        //b2brtpplay = window.b2bapis.b2brtpplay;
        rtpPlayer = new RTPPlayer(config);
        registerKeys();
        registerKeyHandler();
        registerMouseEvents();
    } catch (e) {
        // TODO: handle exception
        log('Error' + e);
    }

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            // Something you want to do when hide or exit.
            if (rtpPlayer) {
                rtpPlayer.unsetListener();
                rtpPlayer.stop();
            }
        } else {
            // Something you want to do when resume.
        }
    });
};

/**
 * Register keys used in this application
 */
function registerKeys() {
    var usedKeys = [
        'MediaPause',
        'MediaPlay',
        'MediaPlayPause',
        'MediaFastForward',
        'MediaRewind',
        'MediaStop',
        '0',
        '1',
        '2',
        '3'
    ];

    usedKeys.forEach(
        function (keyName) {
            tizen.tvinputdevice.registerKey(keyName);
        }
    );
}
function pausePlay() {
    if (currentURL || currentURL != '') {
        if (rtpPlayer.getState() !== 'IDLE') {
            rtpPlayer.stop();
        }
        rtpPlayer.playChannel(currentURL);
    } else {
        log('Empty URL, please type a valid URL');

    }
}

function myClick() {
    document.getElementById('btn-load-url').click();
    pausePlay();
}

/**
 * Handle input from remote
 */
function registerKeyHandler() {
    document.addEventListener('keydown', function (e) {
        //console.log(e);
        keyTest = e;
        switch (e.keyCode) {
            case 13:    // Enter
                rtpPlayer.toggleFullscreen();
                break;
            case 10252: // MediaPlayPause
            case 415:   // MediaPlay
            case 19:    // MediaPause
                myClick();
                break;
            case 413:   // MediaStop
                rtpPlayer.stop();
                break;
            case 417:   // MediaFastForward
                break;
            case 412:   // MediaRewind
                break;
            case 48: //Key 0
                log();
                break;
            case 49: //Key 1
            	rtpPlayer.playChannel('udp://@239.255.0.1:5001');
                break;
            case 50: //Key 2
            	rtpPlayer.playChannel('udp://@239.255.0.2:5001');
                break;
            case 51: //Key 3
            	rtpPlayer.playChannel('udp://@239.255.0.3:5001');
                break;
            case 52: //Key 4
            	rtpPlayer.playChannel('udp://@239.255.0.4:5001');
                break;
             
            case 10009: // Return
                closeApp();
                break;
            default:
            //log("Unhandled key");
        }
    });
}
function closeApp() {
    if (rtpPlayer.getState() !== 'IDLE') {
        rtpPlayer.stop();

    }
    window.location.href = "../index.html";
}
function registerMouseEvents() {
    document.querySelector('.video-controls .play').addEventListener(
        'click',
        function () {
            if (currentURL) {
                if (rtpPlayer.getState() !== 'IDLE') {
                    rtpPlayer.stop();

                }
                rtpPlayer.playChannel(currentURL);
            }
            else {
                log('Check the URL');
            }
        }
    );
    document.querySelector('.video-controls .stop').addEventListener(
        'click',
        function () {
            rtpPlayer.stop();
        }
    );
    document.querySelector('.video-controls .fullscreen').addEventListener(
        'click',
        rtpPlayer.toggleFullscreen
    );
    document.getElementById('btn-load-url').addEventListener(
        'click',
        function () {
            document.getElementById('stream-url').blur;
            var temp = document.getElementById('stream-url').value;
            if (temp != null || temp != '') {

                currentURL = temp;
                console.log(currentURL);
                //config.url = currentURL;
                document.getElementById('currentURL').innerHTML = currentURL;



            }
        }
    );

}

/**
 * Display application version
 */
function displayVersion() {
    var el = document.createElement('div');
    el.id = 'version';
    el.innerHTML = 'ver: ' + tizen.application.getAppInfo().version;
    document.body.appendChild(el);
}

//Logger function
function log(msg) {
    var logsEl = document.getElementById('logs');

    if (msg) {
        // Update logs
        console.log('[B2BrtpPlayer]: ' + msg);
        logsEl.innerHTML += msg + '<br />';
    } else {
        // Clear logs
        logsEl.innerHTML = '';
    }

    logsEl.scrollTop = logsEl.scrollHeight;
}

function redireccionar() {
    window.location = "../index.html";
}
//window.onload can work without <body onload="">
window.onload = init;