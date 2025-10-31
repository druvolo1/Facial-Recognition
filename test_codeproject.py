"""
Simple test script to verify CodeProject.AI connectivity and endpoints
"""
import requests
import time

CODEPROJECT_HOST = "172.16.1.150"
CODEPROJECT_PORT = 32168
CODEPROJECT_BASE_URL = f"http://{CODEPROJECT_HOST}:{CODEPROJECT_PORT}/v1"


def test_list_faces():
    """Test the list faces endpoint"""
    print(f"\n{'='*60}")
    print(f"TEST 1: List Registered Faces")
    print(f"{'='*60}")

    url = f"{CODEPROJECT_BASE_URL}/vision/face/list"
    print(f"URL: {url}")

    try:
        start = time.time()
        response = requests.get(url, timeout=10)
        elapsed = time.time() - start

        print(f"Status Code: {response.status_code}")
        print(f"Response Time: {elapsed:.2f}s")
        print(f"Response Body:")
        print(response.json())

        if response.status_code == 200:
            print(f"\n✓ SUCCESS")
            return True
        else:
            print(f"\n✗ FAILED")
            return False

    except requests.exceptions.Timeout:
        print(f"✗ TIMEOUT - Server did not respond within 10 seconds")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"✗ CONNECTION ERROR: {e}")
        return False
    except Exception as e:
        print(f"✗ ERROR: {e}")
        return False


def test_register_endpoint():
    """Test the register endpoint with a dummy request"""
    print(f"\n{'='*60}")
    print(f"TEST 2: Register Endpoint (empty request)")
    print(f"{'='*60}")

    url = f"{CODEPROJECT_BASE_URL}/vision/face/register"
    print(f"URL: {url}")
    print(f"NOTE: Testing with empty request to see how endpoint responds")
    print(f"Timeout: 30 seconds")

    try:
        start = time.time()
        # Send empty request just to test connectivity
        response = requests.post(url, timeout=30)
        elapsed = time.time() - start

        print(f"Status Code: {response.status_code}")
        print(f"Response Time: {elapsed:.2f}s")

        try:
            print(f"Response Body: {response.text}")
        except:
            pass

        # We expect this to fail (400 or similar) because no image was sent
        # But it proves the endpoint is reachable
        if response.status_code in [200, 400, 422]:
            print(f"\n✓ Endpoint is REACHABLE (status {response.status_code} is expected)")
            return True
        else:
            print(f"\n⚠ Unexpected status: {response.status_code}")
            return False

    except requests.exceptions.Timeout:
        print(f"✗ TIMEOUT - Server did not respond within 30 seconds")
        print(f"   This is a MAJOR PROBLEM - Face registration module may not be loaded")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"✗ CONNECTION ERROR: {e}")
        return False
    except Exception as e:
        print(f"✗ ERROR: {e}")
        return False


def test_recognize_endpoint():
    """Test the recognize endpoint with a dummy request"""
    print(f"\n{'='*60}")
    print(f"TEST 3: Recognize Endpoint (empty request)")
    print(f"{'='*60}")

    url = f"{CODEPROJECT_BASE_URL}/vision/face/recognize"
    print(f"URL: {url}")
    print(f"NOTE: Testing with empty request to see how endpoint responds")
    print(f"Timeout: 30 seconds")

    try:
        start = time.time()
        # Send empty request just to test connectivity
        response = requests.post(url, timeout=30)
        elapsed = time.time() - start

        print(f"Status Code: {response.status_code}")
        print(f"Response Time: {elapsed:.2f}s")

        try:
            print(f"Response Body: {response.text}")
        except:
            pass

        # We expect this to fail (400 or similar) because no image was sent
        # But it proves the endpoint is reachable
        if response.status_code in [200, 400, 422]:
            print(f"\n✓ Endpoint is REACHABLE (status {response.status_code} is expected)")
            return True
        else:
            print(f"\n⚠ Unexpected status: {response.status_code}")
            return False

    except requests.exceptions.Timeout:
        print(f"✗ TIMEOUT - Server did not respond within 30 seconds")
        print(f"   This is a MAJOR PROBLEM - Face recognition module may not be loaded")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"✗ CONNECTION ERROR: {e}")
        return False
    except Exception as e:
        print(f"✗ ERROR: {e}")
        return False


def test_base_url():
    """Test if the base server is reachable"""
    print(f"\n{'='*60}")
    print(f"TEST 3: Base Server Connectivity")
    print(f"{'='*60}")

    base_url = f"http://{CODEPROJECT_HOST}:{CODEPROJECT_PORT}"
    print(f"URL: {base_url}")

    try:
        start = time.time()
        response = requests.get(base_url, timeout=5)
        elapsed = time.time() - start

        print(f"Status Code: {response.status_code}")
        print(f"Response Time: {elapsed:.2f}s")
        print(f"\n✓ Base server is REACHABLE")
        return True

    except requests.exceptions.Timeout:
        print(f"✗ TIMEOUT")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"✗ CONNECTION ERROR: {e}")
        return False
    except Exception as e:
        print(f"✗ ERROR: {e}")
        return False


if __name__ == '__main__':
    print(f"\n{'*'*60}")
    print(f"*{' '*58}*")
    print(f"*  CodeProject.AI Connection Test{' '*26}*")
    print(f"*{' '*58}*")
    print(f"{'*'*60}")

    print(f"\nTarget Server: {CODEPROJECT_HOST}:{CODEPROJECT_PORT}")
    print(f"API Base URL: {CODEPROJECT_BASE_URL}")

    results = []

    # Run tests
    results.append(("Base Server", test_base_url()))
    results.append(("List Faces", test_list_faces()))
    results.append(("Register Endpoint", test_register_endpoint()))
    results.append(("Recognize Endpoint", test_recognize_endpoint()))

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:25s} : {status}")

    total_passed = sum(1 for _, passed in results if passed)
    print(f"\nTotal: {total_passed}/{len(results)} tests passed")

    if total_passed == len(results):
        print(f"\n✓ All tests passed! CodeProject.AI is working correctly.")
    elif total_passed == 0:
        print(f"\n✗ All tests failed. Check if CodeProject.AI is running.")
        print(f"   - Verify Docker container is running")
        print(f"   - Check IP address: {CODEPROJECT_HOST}")
        print(f"   - Check port: {CODEPROJECT_PORT}")
    else:
        print(f"\n⚠ Some tests failed. CodeProject.AI may have issues.")

    print()
