/**
 * .: BRAVO - SRT :.
 * @class RTPPlayer
 * @description This class contains the methods for RTP/UDP IPTV player for Tizen 2.4 (B2B Smart Signage);
 * 				using b2brtpplay API.
 * @version 0.10
 * @author Juan Cortes, juan.cortes@samsung.com, 2017
 *
 */

/**
 * Player object constructor.
 *
 * @param   {Object} config - Playback and player configuration.
 * @returns {Object}
 */
function RTPPlayer(config) {
	/**
	 * Logger function to display logs
	 * @type {function}
	 * */
    var log = config.logger;

    /**
     * HTML controls div
     * @type {Object}
     */
    var controls = config.controls;
    
    /**
     * HTML rtp-player element
     * @type {Object}
     */
    var player = config.player;

    /**
     * Fullscreen flag
     * @type {Boolean}
     */
    var isFullscreen = false;

    /**
     * Default resolution Number (1920 by default)
     * @type {Int}
     */
    var defaultResolutionWidth = 1920;

    /**
     * Resolution width
     * @type {Int}
     */
    var resolutionWidth = config.resolutionWidth;

    /**
     * Rectangle area, if defined on the config object it set the Player in a custom position.
     * @type {Object}
     */
    var rectArea = {
        x: ((config.x) ? config.x : 10),
        y: ((config.y) ? config.y : 220),
        w: ((config.w) ? config.w : 854),
        h: ((config.h) ? config.h : 480)
    };

    /**
     * Player coordinates (hardcoded position x = 10, y = 220, width = 854, height = 480)
     *
     * @type {Object}
     */
    var playerCoords = {
        x: Math.floor(rectArea.x * resolutionWidth / defaultResolutionWidth),
        y: Math.floor( rectArea.y * resolutionWidth / defaultResolutionWidth),
        width: Math.floor( rectArea.w * resolutionWidth / defaultResolutionWidth),
        height: Math.floor( rectArea.h * resolutionWidth / defaultResolutionWidth)
    };
    /**
     * Get the current status of the player
     * @type {Boolean}
     * */
    var isPlaying = false;
    
    return {
        /**
         * Function to initialize the playback.
         * @param {String} url - content url, if there is no value then take url from config
         */
        playChannel: function(url) {

            //Create listener object.
            var b2brtpplayCallback = function(eventName, param) {
                //code for handling Middleware event
                log("[setEventListener] eventName: " + eventName + " | param: " + param);
                if (eventName == "RTP_PLAYER_EVENTS" && param == "4") {
                    log("Weak or no Signal");
                    setTimeout(this.stop(),2000);
                } else if (eventName == "RTP_PLAYER_EVENTS" && param == "12") {
                    log("RTP event: " + param);
                } else {
                    log('Event: [' + eventName + '] param: [' + param + ']');
                }
            };

            //OnSuccess callback PLAY CHANNEL
            var onSuccess = function() {
                log("[playChannel] success ");
                
                //Change the state of the player
                isPlaying = true;
            };

            //OnError callback PLAY CHANNEL
            var onError = function(error) {
                log("[playChannel] code :" + error.code + " error name: " + error.name + "  message " + error.message);
            };

            //OnSuccess callback for DisplayRect call
            var onSuccessDisplayRect = function() {
                log("[DisplayRect] success ");
            };

            //OnError callback for DisplayRect call
            var onErrorDisplayRect = function(error) {
                log("[DisplayRect] code :" + error.code + " error name: " + error.name + "  message " + error.message);
            };
            //If no URL defined will take from config object.
            if (!url) {
                url = config.url;
            }

            //Current URL
            log('RTP player open: ' + url);
            log(playerCoords);
            try {
                //Set listener call
                window.b2bapis.b2brtpplay.setEventListener(b2brtpplayCallback);

                //Set display Rect call
                //window.b2bapis.b2brtpplay.setDisplayRect(
                //    playerCoords.x,
                //    playerCoords.y,
                //    playerCoords.width,
                //    playerCoords.height,
                //    onSuccessDisplayRect,
                //    onErrorDisplayRect
                //);
                
                //Play channel call
                window.b2bapis.b2brtpplay.playChannel(url, onSuccess, onError);

            } catch (e) {
                log(e);
            }
        },

        /**
         * Function to stop current playback.
         */
        stop: function() {
            var onSuccess = function() {
                log("[stopChannel] success ");
                
                //Change the state to false
                isPlaying = false;
            };
            var onError = function(error) {

                log("[stopChannel] code :" + error.code + " error name: " + error.name + "  message " + error.message);
            };

            log("[stopChannel]");
            window.b2bapis.b2brtpplay.stopChannel(onSuccess, onError);

            //switch back from fullscreen to window if stream finished playing
            if (isFullscreen === true) {
                this.toggleFullscreen();
            }
        },
        unsetListener : function(){
        	log("[UnsetListener]");
        	window.b2bapis.b2brtpplay.unsetEventListener();
        },
        /**
         * Switch between full screen mode and normal windowed mode.
         */
        toggleFullscreen: function() {
            //OnSuccess callback for DisplayRect call
            var onSuccessDisplayRect = function() {
                log("[DisplayRect toggle] success ");
            };

            //OnError callback for DisplayRect call
            var onErrorDisplayRect = function(error) {
                log("[DisplayRect toggle] code :" + error.code + " error name: " + error.name + "  message " + error.message);
            };
            if (isFullscreen === false) {

                window.b2bapis.b2brtpplay.setDisplayRect(0, 0, 1920, 1080, onSuccessDisplayRect, onErrorDisplayRect);
                
                player.classList.add('fullscreenMode');
                
                controls.classList.add('fullscreenMode');
                
                isFullscreen = true;
                
            } else {
                log('Fullscreen off');
                try {
                    //Set display Rect call
                    window.b2bapis.b2brtpplay.setDisplayRect(
                        playerCoords.x,
                        playerCoords.y,
                        playerCoords.width,
                        playerCoords.height,
                        onSuccessDisplayRect,
                        onErrorDisplayRect
                    );
                } catch (e) {
                    log(e);
                }
                player.classList.remove('fullscreenMode');
                controls.classList.remove('fullscreenMode');
                isFullscreen = false;
            }
        },
        
        /**
         * Function to get status of the Player
         * */
        getState: function() {
        	return isPlaying ? 'PLAYING' : 'IDLE';
        }

    };
}