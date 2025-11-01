# Festival TTS Setup for Raspberry Pi

## What is Festival TTS?
Festival is a mature, open-source text-to-speech system designed for Linux. It produces significantly better quality than espeak and runs 100% offline.

## Why Festival Instead of Piper/Coqui?
- **Coqui TTS** - Requires Rust compiler (not available on ARM64 Raspberry Pi)
- **Piper TTS** - Complex installation requiring binary downloads
- **Festival TTS** - Simple `apt-get install`, sounds much better than espeak ✅

## Installation Steps

### 1. Install Festival TTS
```bash
sudo apt-get update
sudo apt-get install festival festvox-us-slt-hts
```

This installs:
- `festival` - The TTS engine
- `festvox-us-slt-hts` - High-quality male voice package

### 2. Install Python Dependencies
```bash
cd ~/Facial-Recognition
pip install -r requirements.txt
```

### 3. Clear Old Audio Cache
Remove any cached audio from previous TTS engines:
```bash
rm -rf audio/*
```

### 4. Test Festival (Optional)
Test Festival from command line:
```bash
echo "Hello, this is a test of Festival text to speech" | festival --tts
```

Or generate a WAV file:
```bash
echo "Testing Festival TTS" | text2wave -o test.wav
aplay test.wav
```

### 5. Test the Greeter
1. Start your Flask server:
   ```bash
   python app.py
   ```

2. Open the greeter page:
   ```
   https://nrf.ruvolo.loseyourip.com/greet
   ```

3. The avatar should greet you with a better-sounding male voice!

## Voice Quality
Festival TTS provides:
- ✅ **Better than espeak** - More natural pronunciation
- ✅ **100% offline** - No cloud API needed
- ✅ **Easy installation** - Single apt-get command
- ✅ **No Rust compiler needed** - Pure C++
- ✅ **Male voice** - Uses CMU RMS voice (male)
- ✅ **Free and open source**

## Available Voice Options
Festival comes with different voices. The current setup uses `voice_cmu_us_rms_cg` (male voice).

To change voices, edit `app.py` line 519:

```python
# Current: US Male RMS voice
'-eval', '(voice_cmu_us_rms_cg)'

# Other options (if installed):
# '-eval', '(voice_cmu_us_slt_arctic_hts)'  # Female voice (if festvox-us-slt-hts installed)
# '-eval', '(voice_cmu_us_awb_arctic_hts)'  # Another male option
```

### Installing Additional Voices
```bash
# Female voice
sudo apt-get install festvox-us-slt-hts

# Other male voices
sudo apt-get install festvox-us-awb-hts
sudo apt-get install festvox-kallpc16k

# To see all available voice packages:
apt-cache search festvox
```

## Troubleshooting

### If Festival is not found:
```bash
# Install Festival
sudo apt-get update
sudo apt-get install festival festvox-us-slt-hts

# Verify installation
which festival
which text2wave
```

### If voice quality is poor:
Install the HTS (High-Quality Synthesis) voice:
```bash
sudo apt-get install festvox-us-slt-hts
```

### Check Festival version:
```bash
festival --version
```

### Test audio output:
```bash
# Test festival directly
echo "Test" | festival --tts

# If no sound, check ALSA:
aplay -l  # List audio devices
```

## Performance on Raspberry Pi 4B
- Audio generation: ~2-3 seconds for typical greeting
- Subsequent generations with same text: Instant (cached)
- No internet required after installation
- Very low CPU usage

## Voice Comparison
- **espeak**: Very robotic, synthetic ❌
- **Festival**: Natural pronunciation, better intonation ✅
- **Piper/Coqui**: Neural quality (but hard to install on ARM64) ⚠️
- **Cloud TTS**: Best quality but costs money ❌

Festival provides the best balance of quality, ease of installation, and reliability for Raspberry Pi!
