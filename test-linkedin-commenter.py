#!/usr/bin/env python3
"""
Test script to verify the LinkedIn commenter proof-of-concept works correctly.
"""

import subprocess
import sys
import os

def test_linkedin_commenter():
    """Test the LinkedIn commenter script."""
    script_path = os.path.join(os.path.dirname(__file__), 'src', 'resources', 'scripts', 'linkedin_commenter.py')
    
    print("🧪 Testing LinkedIn Commenter - Proof of Concept...")
    
    # Test 1: Basic execution
    print("📋 Test 1: Basic execution")
    try:
        result = subprocess.run([sys.executable, script_path], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ Basic execution passed")
        else:
            print(f"❌ Basic execution failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Basic execution error: {e}")
        return False
    
    # Test 2: With debug flag
    print("📋 Test 2: Debug mode")
    try:
        result = subprocess.run([sys.executable, script_path, '--debug'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and "Debug mode enabled" in result.stdout:
            print("✅ Debug mode passed")
        else:
            print(f"❌ Debug mode failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Debug mode error: {e}")
        return False
    
    # Test 3: With config flag
    print("📋 Test 3: Config mode")
    try:
        result = subprocess.run([sys.executable, script_path, '--config', 'test.json'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and "Configuration file specified" in result.stdout:
            print("✅ Config mode passed")
        else:
            print(f"❌ Config mode failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Config mode error: {e}")
        return False
    
    # Test 4: Import validation
    print("📋 Test 4: Import validation")
    try:
        result = subprocess.run([sys.executable, script_path], 
                              capture_output=True, text=True, timeout=10)
        if "All dependencies imported successfully" in result.stdout:
            print("✅ All dependencies imported successfully")
        else:
            print("❌ Dependency imports failed")
            return False
    except Exception as e:
        print(f"❌ Import validation error: {e}")
        return False
    
    print("🎉 All tests passed! LinkedIn Commenter proof-of-concept is working correctly.")
    return True

if __name__ == "__main__":
    success = test_linkedin_commenter()
    sys.exit(0 if success else 1)
