# WebRTC Test App - Exact Copy of Working Reference

This is an **exact copy** of the working IPTV reference, just renamed to WebRTCTest.

## Structure

```
sssp_app/
└── SSSP/                      ← Copy this folder to USB root
    ├── WebRTCTest.wgt        ← Exact copy of IPTVRTPPlayer.wgt
    ├── WebRTCTest.zip        ← Exact copy of IPTVRTPPlayer.zip
    └── sssp_config.xml       ← Updated widget name to WebRTCTest
```

## Installation

1. **Copy the SSSP folder to your USB root**
2. Insert USB into Samsung display
3. Navigate to: Menu → Settings → Support → Device Manager → USB
4. Install **WebRTCTest** app
5. Launch

## What This Is

This is the EXACT working IPTV app from your reference, with only the names changed:
- ✅ Same .wgt file (just renamed)
- ✅ Same .zip file (just renamed)
- ✅ sssp_config.xml updated with new name

**No code changes, no structure changes, just renamed files.**

If this doesn't install, then something else is wrong with the display or USB itself.

## Expected Result

Since this is the exact working reference, it should:
- ✅ Install successfully
- ✅ Launch successfully
- ⚠️ Show the IPTV app interface (not Hello World)

Once this works, we know the structure is correct and can then modify the contents of the .wgt file.

## Reference

Copied from: `C:\Users\Dave\Documents\Programming\Facial Recognition\SSSP_reference`
