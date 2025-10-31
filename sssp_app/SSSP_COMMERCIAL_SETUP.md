# SSSP 6.5 Commercial Display Setup Guide

## Camera Permissions on Commercial Displays

Commercial Samsung displays (SSSP 6.5) have a different permission model than consumer TVs.

## Method 1: Reset App Permissions on Display

### Via Display Settings:

1. Press **Home** button on remote (or long-press **INFO** button)
2. Navigate to **Settings** → **All Settings**
3. Go to **General** → **Reset**
4. Select **Reset App Permissions**
5. Find "Face Recognition Monitor" and reset its permissions
6. Relaunch the app - it will prompt for camera permission

### Alternative: Uninstall and Reinstall

1. Go to **Settings** → **Support** → **Device Care**
2. Select **Manage Storage**
3. Find "Face Recognition Monitor"
4. Select **Uninstall**
5. Reinstall the app from USB
6. On first launch, it will request camera permission

## Method 2: MagicInfo Server Configuration

If your display is managed by MagicInfo:

### Via MagicInfo Server:

1. Log into MagicInfo Server
2. Go to **Device** → **Device List**
3. Select your display
4. Click **Remote Management** → **Settings**
5. Navigate to **Security & Restrictions**
6. Find **App Permissions**
7. Enable camera for "Face Recognition Monitor"
8. Click **Apply** and wait for sync

### Via MagicInfo Express:

1. Open MagicInfo Express app
2. Connect to your display
3. Go to **Settings** → **Application Settings**
4. Find your app in the list
5. Enable **Camera** permission
6. Save and exit

## Method 3: Debug Mode Access

For advanced troubleshooting:

### Enable Developer Mode:

1. On remote, press: **Mute → 1 → 1 → 9 → Enter**
   (or **Mute → 1 → 8 → 2 → Power**)
2. This enables service menu
3. Navigate to **Developer Options**
4. Enable **USB Debugging**

### Check Permissions via ADB:

```bash
# Connect to display via network ADB
adb connect <DISPLAY_IP>:26101

# Check installed packages
adb shell pm list packages | grep FaceRec

# Check permissions for your app
adb shell dumpsys package com.yourcompany.FaceRecMonitor | grep permission

# Grant camera permission manually
adb shell pm grant com.yourcompany.FaceRecMonitor android.permission.CAMERA
```

## Method 4: Using Tizen Studio

### Remote Web Inspector:

1. Install Tizen Studio
2. Connect to display:
   ```bash
   sdb connect <DISPLAY_IP>:26101
   ```
3. Open Web Inspector:
   ```bash
   sdb capability
   sdb forward tcp:9090 tcp:9090
   ```
4. Open Chrome and navigate to: `http://localhost:9090`
5. Select your app from the list
6. Check console for permission errors

### Check Permission Status:

In the console, run:
```javascript
// Check if Tizen API is available
console.log('Tizen available:', typeof tizen !== 'undefined');

// Check PPM (Privacy Privilege Manager)
if (tizen.ppm) {
    console.log('Camera permission:', tizen.ppm.checkPermission('http://tizen.org/privilege/camera'));
    console.log('Media permission:', tizen.ppm.checkPermission('http://tizen.org/privilege/mediacapture'));
}
```

## Method 5: Manual Permission Grant (Commercial Admin)

### Via On-Screen Display (OSD):

1. Press **Menu** on the display (physical button, not remote)
2. Enter admin PIN (default often: 0000 or 1234)
3. Navigate to **Signage Setup** → **Security**
4. Go to **Application Permissions**
5. Find your app and enable Camera
6. Save and exit

### Via RS232C Serial Control:

If you have serial access:
```
# Enable camera for all apps (admin command)
0x01 0x02 0x03 0x04 0x05 0x06 (specific to model)
```

Consult your display's RS232C protocol manual.

## Method 6: Factory Reset App Data

As a last resort:

1. **Settings** → **Support** → **Self Diagnosis**
2. Select **Reset Smart Hub** or **Reset Apps**
3. This clears all app data and permissions
4. Reinstall your app
5. Grant permissions on first launch

## Verifying Camera Hardware

### Check USB Camera (if using external):

1. Connect USB camera to display
2. Go to **Settings** → **General** → **External Device Manager**
3. Camera should appear in **USB Device List**
4. Note the device ID (e.g., `/dev/video0`)

### Test Camera with Built-in App:

Some displays have a built-in camera test:
1. **Settings** → **Support** → **Device Care** → **Self Diagnosis**
2. Look for **Camera Test** option
3. If camera works here but not in your app, it's a permission issue

## Common SSSP 6.5 Issues

### Issue: "PPM API not available"

**Cause:** App not properly signed or running in wrong context

**Solution:**
- Ensure app is installed as WGT package, not just HTML file
- Check that config.xml has correct `<tizen:application>` element
- Verify package ID matches in config.xml

### Issue: Permission popup never appears

**Cause:** Permissions marked as "DENY" from previous run

**Solution:**
```bash
# Via ADB
adb shell pm reset-permissions com.yourcompany.FaceRecMonitor

# Or reinstall app completely
```

### Issue: "getUserMedia not supported"

**Cause:** Wrong WebView or browser version

**Solution:**
- Update display firmware to latest version
- Ensure SSSP 6.5 or higher
- Some older firmware versions have limited WebRTC support

## Checking Firmware Version

1. **Settings** → **Support** → **About This TV/Display**
2. Look for:
   - **Tizen Version**: Should be 6.5 or higher
   - **SSSP Version**: Should be 6.5 or higher
   - **Browser Version**: Should support WebRTC

Required versions:
- Tizen: 6.5+
- SSSP: 6.5+
- Chromium Engine: 85+

## Network Considerations

Even with camera working, ensure:

### Firewall Rules:
- Allow outbound HTTP/HTTPS from display
- Port 5000 open to your Flask server
- No proxy blocking WebRTC/camera streams

### Test Server Connectivity:
```javascript
// Add to your app for testing
fetch('http://garden1.local:5000/api/health-check')
    .then(r => r.json())
    .then(d => console.log('✓ Server reachable:', d))
    .catch(e => console.error('✗ Server unreachable:', e));
```

## Support Channels

### Samsung B2B Support:
- Phone: 1-866-SAM4BIZ (726-4249)
- Website: https://displaysolutions.samsung.com/support
- Provide: Model number, SSSP version, error description

### Remote Support:
Samsung can often remote-in to diagnose:
- Enable remote management in display settings
- Provide display IP and credentials to support

## Quick Diagnostic Checklist

Run through these steps:

- [ ] Display is SSSP 6.5 or higher
- [ ] USB camera connected and detected (if external)
- [ ] App installed as WGT package (not loose HTML files)
- [ ] App has been reset/reinstalled at least once
- [ ] Permission request popup appeared on first launch
- [ ] Camera permission granted (not denied)
- [ ] Network connectivity to Flask server confirmed
- [ ] Tizen console shows no errors (via Web Inspector)
- [ ] Simple camera test HTML works on display

## Expected Behavior

When working correctly:

1. **First Launch:** Permission popup appears asking for camera access
2. **User Grants:** Camera activates, video feed shows
3. **Console Shows:**
   ```
   [PERMISSIONS] Granted: http://tizen.org/privilege/camera
   [CAMERA] Camera started: 1280 x 720
   [DISPLAY] Registered display: display_xxx at Unknown Location
   ```
4. **Status:** Green indicator showing "Connected to server"
5. **Face Detection:** Bounding boxes appear over detected faces

## Last Resort: Alternative Installation

If all else fails, try installing as a web bookmark:

1. Open display's browser
2. Navigate to: `http://garden1.local:5000/static/sssp_app/index.html`
3. Bookmark the page
4. Set as homepage or auto-launch bookmark
5. This runs in browser context, may have different permissions

Note: This approach may have limitations compared to native WGT install.
