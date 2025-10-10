#!/usr/bin/env python3
"""
Test client for Object Detection Server
Tests the /detect endpoint with sample images
"""

import requests
import json
import sys
from pathlib import Path

def test_detection(server_url, image_path):
    """
    Test the object detection endpoint
    
    Args:
        server_url: Base URL of the server (e.g., http://localhost:8000)
        image_path: Path to the test image
    """
    endpoint = f"{server_url}/detect"
    
    print(f"Testing Object Detection Server at {server_url}")
    print(f"Image: {image_path}")
    print("-" * 60)
    
    # Check if image exists
    if not Path(image_path).exists():
        print(f"Error: Image file '{image_path}' not found!")
        return
    
    # Prepare the file for upload
    with open(image_path, 'rb') as f:
        files = {'image': f}
        
        try:
            # Send POST request
            print("Sending request...")
            response = requests.post(endpoint, files=files, timeout=30)
            
            # Check response status
            if response.status_code == 200:
                result = response.json()
                print(f"✓ Success!")
                print(f"Detection count: {result['detection_count']}")
                print(f"Image dimensions: {result['image_dimensions']['width']}x{result['image_dimensions']['height']}")
                print("\nDetected objects:")
                
                for i, det in enumerate(result['detections'], 1):
                    print(f"  {i}. {det['class']} (confidence: {det['confidence']:.2%})")
                    bbox = det['bbox']
                    print(f"     BBox: [{bbox['x1']:.1f}, {bbox['y1']:.1f}, {bbox['x2']:.1f}, {bbox['y2']:.1f}]")
                
                print(f"\nModel: {result['model_info']['model']}")
                print(f"Timestamp: {result['timestamp']}")
                
                # Optionally save annotated image
                if 'annotated_image' in result:
                    import base64
                    img_data = base64.b64decode(result['annotated_image'])
                    output_path = Path(image_path).stem + "_annotated.jpg"
                    with open(output_path, 'wb') as out_f:
                        out_f.write(img_data)
                    print(f"\n✓ Annotated image saved to: {output_path}")
                
            else:
                print(f"✗ Error: {response.status_code}")
                print(response.text)
                
        except requests.exceptions.RequestException as e:
            print(f"✗ Request failed: {e}")

def test_health(server_url):
    """Test the health check endpoint"""
    endpoint = f"{server_url}/health"
    
    print(f"Testing health endpoint: {endpoint}")
    
    try:
        response = requests.get(endpoint, timeout=10)
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Server is healthy!")
            print(f"  Status: {result['status']}")
            print(f"  Model: {result['model']}")
            print(f"  Timestamp: {result['timestamp']}")
        else:
            print(f"✗ Health check failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"✗ Health check failed: {e}")

def test_info(server_url):
    """Test the model info endpoint"""
    endpoint = f"{server_url}/info"
    
    print(f"Testing info endpoint: {endpoint}")
    
    try:
        response = requests.get(endpoint, timeout=10)
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Model Information:")
            print(f"  Model: {result['model']}")
            print(f"  Number of classes: {result['num_classes']}")
            print(f"  Configuration: {result['configuration']}")
        else:
            print(f"✗ Info request failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"✗ Info request failed: {e}")

if __name__ == "__main__":
    # Default server URL
    server_url = "http://localhost:8000"
    
    # Check command line arguments
    if len(sys.argv) > 1:
        server_url = sys.argv[1]
    
    print("=" * 60)
    print("Object Detection Server Test Client")
    print("=" * 60)
    print()
    
    # Test health endpoint
    test_health(server_url)
    print()
    
    # Test info endpoint
    test_info(server_url)
    print()
    
    # Test detection with image if provided
    if len(sys.argv) > 2:
        image_path = sys.argv[2]
        test_detection(server_url, image_path)
    else:
        print("Usage for detection test:")
        print(f"  python test_client.py [server_url] <image_path>")
        print(f"  Example: python test_client.py http://localhost:8000 test_image.jpg")


