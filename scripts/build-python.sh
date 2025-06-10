#!/bin/bash

# Build script for creating Python executables for all platforms
# This script should be run in a CI/CD environment or manually on each platform

set -e

echo "Building Python executables for LinkedIn automation..."

# Create output directory
mkdir -p resources/python-executables

# Function to build for current platform
build_current_platform() {
    echo "Building for current platform: $(uname -s)-$(uname -m)"
    
    # Install PyInstaller if not already installed
    python3 -m pip install pyinstaller
    
    # Install required dependencies first
    python3 -m pip install -r src/resources/scripts/requirements.txt
    
    # Create platform-specific output directory
    PLATFORM_DIR=$(get_platform_dir)
    mkdir -p "resources/python-executables/$PLATFORM_DIR"
    
    # Create executable using spec file for better dependency handling
    python3 -m PyInstaller \
        --distpath "resources/python-executables/$PLATFORM_DIR" \
        --workpath "build/pyinstaller" \
        linkedin_commenter.spec
    
    echo "Build completed for $PLATFORM_DIR"
}

# Function to get platform directory name
get_platform_dir() {
    case "$(uname -s)" in
        Darwin*)
            if [ "$(uname -m)" = "arm64" ]; then
                echo "mac-arm64"
            else
                echo "mac-x64"
            fi
            ;;
        Linux*)
            if [ "$(uname -m)" = "x86_64" ]; then
                echo "linux-x64"
            else
                echo "linux-ia32"
            fi
            ;;
        CYGWIN*|MINGW32*|MSYS*|MINGW*)
            if [ "$(uname -m)" = "x86_64" ]; then
                echo "win-x64"
            else
                echo "win-ia32"
            fi
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

# Build for current platform
build_current_platform

echo "Python executable build completed!"
echo "Executable location: resources/python-executables/$(get_platform_dir)/"
