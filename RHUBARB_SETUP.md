# Rhubarb Lip Sync Setup Instructions

## Download and Install Rhubarb Lip-Sync

1. Download the latest Windows release from:
   https://github.com/DanielSWolf/rhubarb-lip-sync/releases

2. Download `Rhubarb-Lip-Sync-1.13.0-Windows.zip` (or latest version)

3. Extract the ZIP file to:
   `C:\Program Files\rhubarb-lip-sync\`

4. Add to system PATH:
   - Open "Environment Variables" in Windows
   - Edit "Path" system variable
   - Add: `C:\Program Files\rhubarb-lip-sync`
   - Click OK

5. Test installation by opening Command Prompt and running:
   ```
   rhubarb --version
   ```

## Install Python Dependencies

Run in your project directory:
```
pip install pyttsx3
```

## How It Works

- Rhubarb analyzes audio files and generates mouth shape (viseme) data
- The Flask server generates speech audio using pyttsx3
- Rhubarb processes the audio to create a timeline of mouth shapes
- The frontend animates the avatar's mouth based on this timeline
- 100% free and open source, no API keys needed!
