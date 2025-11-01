# Google Cloud Text-to-Speech Setup

Get a **deep male voice** for your avatar! Free tier includes 1 million characters/month.

## Quick Setup (5 minutes)

### Step 1: Create Google Cloud Account
1. Go to https://console.cloud.google.com
2. Sign in with your Google account
3. Accept the terms and create a new project (e.g., "Avatar-TTS")

### Step 2: Enable Text-to-Speech API
1. In the Google Cloud Console, go to **APIs & Services > Library**
2. Search for "Text-to-Speech API"
3. Click on it and click **ENABLE**

### Step 3: Create Service Account & Key
1. Go to **APIs & Services > Credentials**
2. Click **CREATE CREDENTIALS > Service Account**
3. Enter a name (e.g., "avatar-tts-service")
4. Click **CREATE AND CONTINUE**
5. Skip the optional steps, click **DONE**
6. Click on the service account you just created
7. Go to **KEYS** tab
8. Click **ADD KEY > Create new key**
9. Choose **JSON** format
10. Click **CREATE** - a JSON file will download

### Step 4: Configure on Raspberry Pi

Upload the JSON key file to your Pi:

```bash
# Create a directory for credentials
mkdir -p ~/credentials

# Upload the JSON file (do this from your computer via SCP or copy-paste)
# Example: scp ~/Downloads/avatar-tts-xxxxx.json dave@garden1:~/credentials/google-tts-key.json
```

Then set the environment variable in your shell:

```bash
# Add to ~/.bashrc so it persists
echo 'export GOOGLE_APPLICATION_CREDENTIALS="$HOME/credentials/google-tts-key.json"' >> ~/.bashrc

# Load it now
source ~/.bashrc

# Verify it's set
echo $GOOGLE_APPLICATION_CREDENTIALS
```

### Step 5: Install Python Package

```bash
cd ~/Facial-Recognition
pip install -r requirements.txt
```

### Step 6: Restart Flask Server

```bash
python app.py
```

You should see in the console:
```
[TTS] Using Google Cloud Text-to-Speech (Deep Male Voice)
[TTS] ✓ Google Cloud TTS audio generated (Deep Male Voice)
```

## Testing

Clear the audio cache and test:

```bash
rm -rf ~/Facial-Recognition/audio/*
```

Then go to `/greet` and trigger a greeting. You'll hear the **deep male voice**!

## Voice Options

Edit `app.py` line 522 to change voices:

- `en-US-Neural2-D` - **Deep male US voice** (current, sounds like narrator)
- `en-GB-Neural2-D` - Deep male British voice
- `en-GB-Neural2-B` - Male British voice (standard)
- `en-US-Studio-M` - Male US cinematic/studio voice

## Pricing

**FREE TIER**: 1 million characters/month
- Average greeting: ~20 characters
- That's **50,000 greetings per month** for FREE!
- You won't hit the limit

## Troubleshooting

If it's not working:
1. Check the environment variable: `echo $GOOGLE_APPLICATION_CREDENTIALS`
2. Check the JSON file exists: `ls -la ~/credentials/google-tts-key.json`
3. Check Flask console for error messages
4. It will automatically fall back to gTTS if Google Cloud fails
