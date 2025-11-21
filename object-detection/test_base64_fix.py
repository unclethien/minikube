#!/usr/bin/env python3
"""
Test script to verify base64 image decoding works correctly
"""

import cv2
import numpy as np
import base64
import requests
import io
from PIL import Image

# Server URL (change to your local or deployed URL)
SERVER_URL = "http://localhost:8000/detect/cluster-batch"

def create_test_image(width, height, color):
    """Create a test image with specific color"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = color  # Fill with color (BGR format)
    return img

def test_base64_encoding():
    """Test sending base64-encoded images like the cluster does"""

    print("Creating test images...")
    img_256 = create_test_image(256, 256, (255, 0, 0))  # Blue
    img_720 = create_test_image(1280, 720, (0, 255, 0))  # Green
    img_1080 = create_test_image(1920, 1080, (0, 0, 255))  # Red

    print("Encoding images to PNG...")
    _, encoded_256 = cv2.imencode('.png', img_256)
    _, encoded_720 = cv2.imencode('.png', img_720)
    _, encoded_1080 = cv2.imencode('.png', img_1080)

    print("Converting to base64 (mimicking cluster behavior)...")
    b64_256 = base64.b64encode(encoded_256.tobytes())
    b64_720 = base64.b64encode(encoded_720.tobytes())
    b64_1080 = base64.b64encode(encoded_1080.tobytes())

    print(f"Base64 lengths: 256p={len(b64_256)}, 720p={len(b64_720)}, 1080p={len(b64_1080)}")

    # Prepare files dict (mimicking cluster's request format)
    files = {
        '256.png': ('256.png', b64_256, 'image/png'),
        '720.png': ('720.png', b64_720, 'image/png'),
        '1080.png': ('1080.png', b64_1080, 'image/png')
    }

    # Add topic as form data (mimicking cluster)
    data = {'topic': 'test_video_frames'}

    print(f"\nSending POST request to {SERVER_URL}...")
    try:
        response = requests.post(SERVER_URL, files=files, data=data, timeout=30)

        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Body:")
        response_data = response.json() if response.headers.get('content-type') == 'application/json' else response.text
        print(response_data)

        if response.status_code == 200:
            print("\n✅ SUCCESS! Base64 decoding is working!")

            # Verify topic was extracted correctly
            if isinstance(response_data, dict):
                source_topic = response_data.get('source_topic')
                print(f"\n📋 Topic Verification:")
                print(f"   Expected: test_video_frames")
                print(f"   Received: {source_topic}")
                if source_topic == 'test_video_frames':
                    print("   ✅ Topic correctly extracted and passed through!")
                else:
                    print(f"   ⚠️  Topic mismatch! Got: {source_topic}")
        elif response.status_code == 400:
            print("\n❌ FAILED! Server returned 400 error. Check error details above.")
        else:
            print(f"\n⚠️  Unexpected status code: {response.status_code}")

    except requests.exceptions.ConnectionError:
        print(f"\n❌ Cannot connect to {SERVER_URL}")
        print("Make sure the server is running: python src/server.py")
    except Exception as e:
        print(f"\n❌ Error: {e}")

def test_binary_encoding():
    """Test sending raw binary images (standard format)"""

    print("\n" + "="*60)
    print("Testing with BINARY images (standard format)...")
    print("="*60)

    print("Creating test images...")
    img_256 = create_test_image(256, 256, (255, 0, 0))
    img_720 = create_test_image(1280, 720, (0, 255, 0))
    img_1080 = create_test_image(1920, 1080, (0, 0, 255))

    print("Encoding images to PNG...")
    _, encoded_256 = cv2.imencode('.png', img_256)
    _, encoded_720 = cv2.imencode('.png', img_720)
    _, encoded_1080 = cv2.imencode('.png', img_1080)

    # Send raw binary (standard format)
    files = {
        '256.png': ('256.png', encoded_256.tobytes(), 'image/png'),
        '720.png': ('720.png', encoded_720.tobytes(), 'image/png'),
        '1080.png': ('1080.png', encoded_1080.tobytes(), 'image/png')
    }

    data = {'topic': 'test_video_frames'}

    print(f"\nSending POST request to {SERVER_URL}...")
    try:
        response = requests.post(SERVER_URL, files=files, data=data, timeout=30)

        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Body:")
        response_data = response.json() if response.headers.get('content-type') == 'application/json' else response.text
        print(response_data)

        if response.status_code == 200:
            print("\n✅ SUCCESS! Binary decoding is working!")

            # Verify topic was extracted correctly
            if isinstance(response_data, dict):
                source_topic = response_data.get('source_topic')
                print(f"\n📋 Topic Verification:")
                print(f"   Expected: test_video_frames")
                print(f"   Received: {source_topic}")
                if source_topic == 'test_video_frames':
                    print("   ✅ Topic correctly extracted and passed through!")
                else:
                    print(f"   ⚠️  Topic mismatch! Got: {source_topic}")
        elif response.status_code == 400:
            print("\n❌ FAILED! Server returned 400 error. Check error details above.")
        else:
            print(f"\n⚠️  Unexpected status code: {response.status_code}")

    except requests.exceptions.ConnectionError:
        print(f"\n❌ Cannot connect to {SERVER_URL}")
        print("Make sure the server is running: python src/server.py")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == '__main__':
    print("="*60)
    print("Base64 Image Decoding Test")
    print("="*60)

    # Test base64 encoding (cluster format)
    print("\nTesting with BASE64 images (cluster format)...")
    print("="*60)
    test_base64_encoding()

    # Test binary encoding (standard format)
    test_binary_encoding()

    print("\n" + "="*60)
    print("Test complete!")
    print("="*60)
