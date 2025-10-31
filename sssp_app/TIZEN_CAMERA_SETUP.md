# Tizen Camera Setup Guide

## Camera Access Denied - Troubleshooting Steps

### 1. Check Camera Permissions on Samsung Display

Samsung Tizen displays require explicit permission for camera access:

#### Via Display Settings:
1. Press **MENU** button on the remote
2. Navigate to **System** → **Security**
3. Find **Privacy & Permissions** or **App Permissions**
4. Locate your Face Recognition Monitor app
5. Enable **Camera** permission
6. Restart the application

#### Alternative Path (Model-Dependent):
- **Settings** → **General** → **Privacy** → **Camera Access**
- Enable camera for installed HTML5 apps

### 2. Verify Camera Hardware

#### USB Camera:
1. Connect USB camera to display's USB port
2. Go to **Settings** → **General** → **External Device Manager**
3. Verify camera is detected in the device list
4. Some displays show camera under **USB Device** settings

#### Built-in Camera:
- Check if display model has built-in camera
- Verify camera is not physically blocked/covered
- Some models have camera enable/disable switch

### 3. Application Signing Requirements

For certain privileges, Tizen apps may need to be signed:

#### Check if Signing is Needed:
- Public privileges (like internet): No signature required
- Partner privileges (like camera): May require signature on some models

#### To Sign Your App (Tizen Studio Method):

1. **Install Tizen Studio**
   ```bash
   # Download from: https://developer.tizen.org/development/tizen-studio/download
   ```

2. **Create Author Certificate**
   ```bash
   tizen certificate -a MyAuthor -p mypassword
   ```

3. **Create Distributor Certificate**
   - For testing: Use default Tizen distributor certificate
   - For production: Request from Samsung B2B partnership

4. **Sign the Package**
   ```bash
   tizen package -t wgt -s <certificate-profile> -- /path/to/app
   ```

### 4. Alternative: Self-Signing for Testing

Create a simple self-signed package:

#### Using OpenSSL (if supported by your display):
```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365

# Package app with signature
# (Specific commands depend on Tizen Studio tools)
```

### 5. Check Browser Console (If Accessible)

Some Samsung displays allow debugging:

#### Enable Developer Mode:
1. Press **MENU** → **System** → **General** → **Device Manager**
2. Look for **Developer Options** or **Debug Mode**
3. Enable **USB Debugging** or **Network Debugging**

#### Access Console:
- Connect via Chrome Remote Debugging if supported
- Or use Tizen Studio's Web Inspector

#### Check for Errors:
Look for specific error messages:
- `NotAllowedError` = Permission denied
- `NotFoundError` = No camera detected
- `NotReadableError` = Camera already in use
- `NotSupportedError` = Camera API not available

### 6. Verify config.xml is Correct

Ensure your packaged app includes:

```xml
<!-- Required privileges -->
<tizen:privilege name="http://tizen.org/privilege/camera"/>
<tizen:privilege name="http://tizen.org/privilege/mediacapture"/>

<!-- Required features -->
<feature name="http://tizen.org/feature/camera"/>
<feature name="http://tizen.org/feature/media.video_stream"/>
```

### 7. Test with Minimal Example

Create a test version with just camera access:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Camera Test</title>
</head>
<body>
    <h1>Camera Test</h1>
    <video id="video" autoplay width="640" height="480"></video>
    <div id="status"></div>

    <script>
        async function testCamera() {
            const status = document.getElementById('status');
            const video = document.getElementById('video');

            try {
                status.textContent = 'Requesting camera...';
                const stream = await navigator.mediaDevices.getUserMedia({ video: true });
                video.srcObject = stream;
                status.textContent = 'SUCCESS: Camera working!';
            } catch (error) {
                status.textContent = 'ERROR: ' + error.name + ' - ' + error.message;
                console.error('Camera error:', error);
            }
        }

        window.addEventListener('load', testCamera);
    </script>
</body>
</html>
```

Save as `camera_test.html` and test on display.

### 8. Samsung-Specific Considerations

#### Model-Specific Issues:
- **QM/QH Series**: Usually support USB cameras well
- **QBR/QMR Series**: May need firmware update for camera support
- **Older Models (< 2018)**: Limited camera API support

#### Firmware Requirements:
- Check current firmware version
- Update to latest firmware if camera issues persist
- Some camera features require Tizen 3.0+

#### SSSP Version:
- SSSP 6.0+ recommended for full camera support
- SSSP 5.0 may have limited camera capabilities

### 9. Network/Server Requirements

Even though not camera-related, ensure:
- Display can reach your Flask server
- Port 5000 is not blocked by firewall
- Server IP is correct in `SERVER_URL`

Test server connectivity:
```javascript
// Add to init() function for debugging
fetch(SERVER_URL + '/api/health-check')
    .then(r => r.json())
    .then(d => console.log('Server OK:', d))
    .catch(e => console.error('Server error:', e));
```

### 10. Contact Samsung Support

If all else fails:
- Contact Samsung Business Support
- Provide display model number
- Ask about camera API compatibility
- May need partner-level API access for some models

### Quick Checklist

- [ ] Camera permissions enabled in display settings
- [ ] USB camera connected and detected (if using external camera)
- [ ] App includes camera privileges in config.xml
- [ ] App is properly signed (if required)
- [ ] Display firmware is up to date
- [ ] SSSP version supports camera access
- [ ] Test with minimal camera test app
- [ ] Check browser console for specific errors
- [ ] Verify hardware camera works with other apps

### Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `NotAllowedError` | Permission denied | Enable camera permission in display settings |
| `NotFoundError` | No camera detected | Connect USB camera or check built-in camera |
| `NotReadableError` | Camera in use | Close other apps using camera |
| `NotSupportedError` | API not available | Update firmware or try different display model |
| `SecurityError` | CSP violation | Check CSP settings in config.xml |

### Additional Resources

- Samsung Developer Portal: https://developer.samsung.com/smarttv
- Tizen Web Device API: https://docs.tizen.org/application/web/api/latest/device_api/mobile/index.html
- Samsung B2B Support: Contact your Samsung representative

### Success Indicators

When camera is working correctly, you should see:
1. Status indicator turns green
2. Live video feed appears
3. Console shows: `[CAMERA] Camera started: 1280 x 720` (or similar)
4. No error messages in status bar
