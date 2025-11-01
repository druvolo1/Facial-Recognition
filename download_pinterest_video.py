#!/usr/bin/env python3
"""
Download video from Pinterest URL using yt-dlp
"""
import subprocess
import sys

def download_pinterest_video(url, output_path="downloaded_video.mp4"):
    """
    Download a video from Pinterest using yt-dlp

    Args:
        url: Pinterest URL
        output_path: Where to save the video
    """
    try:
        print(f"Downloading video from: {url}")
        print(f"Saving to: {output_path}")

        # Use yt-dlp to download the video
        result = subprocess.run(
            [
                'yt-dlp',
                '-o', output_path,
                url
            ],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print(f"✓ Video downloaded successfully: {output_path}")
            return True
        else:
            print(f"✗ Error downloading video:")
            print(result.stderr)
            return False

    except FileNotFoundError:
        print("✗ yt-dlp not found. Install with: pip install yt-dlp")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    url = "https://www.pinterest.com/pin/800444533807321934/"

    # You can change the output filename here
    output = "pinterest_video.mp4"

    download_pinterest_video(url, output)
