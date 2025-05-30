#!/usr/bin/env python3

import subprocess
import sys
import os

def test_chrome():
    print("=== Chrome Detection Test ===")
    
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    print(f"Testing Chrome at: {chrome_path}")
    
    if not os.path.exists(chrome_path):
        print("❌ Chrome binary not found!")
        return False
    
    print("✅ Chrome binary exists")
    
    try:
        result = subprocess.run([chrome_path, '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"✅ Chrome version: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ Chrome execution failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ Chrome version check timed out")
        return False
    except Exception as e:
        print(f"❌ Error testing Chrome: {e}")
        return False

if __name__ == "__main__":
    success = test_chrome()
    print(f"\nResult: {'SUCCESS' if success else 'FAILED'}")
    sys.exit(0 if success else 1)
