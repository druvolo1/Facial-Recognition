#!/bin/bash

echo "Testing Festival TTS Installation"
echo "=================================="
echo ""

# Test 1: Check if Festival is installed
echo "Test 1: Checking if Festival is installed..."
if command -v festival &> /dev/null; then
    echo "✓ Festival is installed"
    festival --version
else
    echo "✗ Festival is NOT installed"
    echo "Install with: sudo apt-get install festival"
    exit 1
fi
echo ""

# Test 2: Check if text2wave is available
echo "Test 2: Checking if text2wave is available..."
if command -v text2wave &> /dev/null; then
    echo "✓ text2wave is available"
else
    echo "✗ text2wave is NOT available"
    exit 1
fi
echo ""

# Test 3: Generate a simple WAV file
echo "Test 3: Generating test audio file..."
echo "Hello, this is a test" > /tmp/test_festival.txt
text2wave /tmp/test_festival.txt -o /tmp/test_festival.wav

if [ -f /tmp/test_festival.wav ]; then
    size=$(stat -f%z /tmp/test_festival.wav 2>/dev/null || stat -c%s /tmp/test_festival.wav)
    echo "✓ Audio file created: /tmp/test_festival.wav ($size bytes)"

    # List available voices
    echo ""
    echo "Test 4: Testing different voices..."

    # Test default voice
    echo "Testing voice_kal_diphone (default male)..."
    text2wave /tmp/test_festival.txt -o /tmp/test_kal.wav -eval '(voice_kal_diphone)'
    if [ -f /tmp/test_kal.wav ] && [ -s /tmp/test_kal.wav ]; then
        echo "✓ voice_kal_diphone works"
    else
        echo "✗ voice_kal_diphone failed"
    fi

    # Clean up
    rm -f /tmp/test_festival.txt /tmp/test_festival.wav /tmp/test_kal.wav

    echo ""
    echo "=================================="
    echo "✓ Festival is working correctly!"
    echo "=================================="
else
    echo "✗ Audio file was NOT created"
    echo "Festival may not be working correctly"
    exit 1
fi
