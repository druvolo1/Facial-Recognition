# Piper TTS Setup for Raspberry Pi

## What is Piper TTS?
Piper is a fast, local neural text-to-speech system that's optimized for Raspberry Pi. It produces natural-sounding voices and runs entirely offline after the initial model download.

## Installation Steps

### 1. Install Piper TTS
```bash
cd ~/Facial-Recognition
pip install -r requirements.txt
```

This will install:
- `piper-tts==1.2.0` - The TTS engine optimized for ARM64/Raspberry Pi

### 2. Clear Old Audio Cache
Remove any cached audio from previous TTS engines:
```bash
rm -rf audio/*
```

### 3. First Run - Model Download
When you first use the greeter, Piper will automatically download the voice model:
- Voice: `en_US-lessac-medium` (US Male voice)
- Size: ~50MB
- Location: `~/.local/share/piper-voices/`

This is a **one-time download**. After that, it runs 100% offline.

### 4. Test the Greeter
1. Start your Flask server:
   ```bash
   python app.py
   ```

2. Open the greeter page:
   ```
   https://nrf.ruvolo.loseyourip.com/greet
   ```

3. The avatar should greet you with a natural-sounding male voice!

## Voice Quality
Piper TTS provides:
- ✅ **Neural voice quality** - Much better than espeak
- ✅ **Optimized for Raspberry Pi** - Fast on ARM64
- ✅ **No cloud API** - 100% offline
- ✅ **No Rust compiler needed** - Pure Python
- ✅ **Natural-sounding male voice**

## Available Voice Options
You can change the voice in `app.py` line 524:

```python
# Current: US Male (medium quality, ~50MB)
voice_name = "en_US-lessac-medium"

# Other options:
# voice_name = "en_US-ryan-high"       # High quality US male (~100MB)
# voice_name = "en_GB-alan-medium"     # British male voice (~50MB)
# voice_name = "en_US-joe-medium"      # Another US male option (~50MB)
```

## Troubleshooting

### If installation fails:
```bash
pip install --upgrade pip
pip install piper-tts==1.2.0
```

### If voice model doesn't download:
The model downloads automatically on first use. Check your internet connection and try again.

### To manually download voice models:
```bash
# Create directory
mkdir -p ~/.local/share/piper-voices

# Download will happen automatically on first TTS request
```

## Why Piper Instead of Coqui?
- **Coqui TTS** requires Rust compiler (not available on ARM64)
- **Piper TTS** is pure Python and optimized for Raspberry Pi
- **Same quality** - Both use neural networks for natural voices
- **Faster** - Piper is specifically optimized for embedded devices

## Performance on Raspberry Pi 4B
- First generation (with download): ~10-15 seconds
- Subsequent generations (cached model): ~1-2 seconds
- Audio is cached, so repeated greetings are instant
