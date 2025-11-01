#!/bin/bash

echo "========================================"
echo "Festival TTS Installation for Raspberry Pi"
echo "========================================"
echo ""

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "❌ This script is for Linux/Raspberry Pi only"
    exit 1
fi

echo "Step 1: Installing Festival TTS with male voice..."
sudo apt-get update
sudo apt-get install -y festival festvox-us-slt-hts festvox-us-bdl-hts

if ! command -v festival &> /dev/null; then
    echo "❌ Festival installation failed"
    exit 1
fi

echo "✓ Festival installed successfully"
echo ""

echo "Step 2: Installing Python dependencies..."
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Python dependencies installation failed"
    exit 1
fi

echo "✓ Python dependencies installed"
echo ""

echo "Step 3: Clearing old audio cache..."
rm -rf audio/*
mkdir -p audio
echo "✓ Audio cache cleared"
echo ""

echo "Step 4: Testing Festival..."
echo "Testing Festival TTS" | festival --tts

if [ $? -eq 0 ]; then
    echo "✓ Festival test successful"
else
    echo "⚠ Festival test had issues (audio might not be working)"
fi

echo ""
echo "========================================"
echo "✓ Installation Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Start the Flask server: python app.py"
echo "2. Open greeter: https://nrf.ruvolo.loseyourip.com/greet"
echo ""
echo "The avatar will now use Festival TTS (better quality than espeak)"
echo ""
