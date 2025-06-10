#!/bin/bash

# Script to build DMG with better error handling and resource management

set -e

echo "🔧 Starting DMG build process..."

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf dist
rm -rf node_modules/.cache

# Free up system memory
echo "💾 Freeing system memory..."
# purge command requires sudo, so we'll skip it for now

# Set memory limits for Node.js
export NODE_OPTIONS="--max-old-space-size=4096 --max-heap-size=4096"

# Build Python first
echo "🐍 Building Python component..."
npm run build:python

# Wait a moment for system to settle
sleep 2

# Try DMG build with retry logic
echo "📦 Building DMG..."
RETRY_COUNT=0
MAX_RETRIES=3

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo "Attempt $((RETRY_COUNT + 1)) of $MAX_RETRIES"
    
    if npx electron-builder --mac --publish=never; then
        echo "✅ DMG build successful!"
        break
    else
        echo "❌ Build failed, retrying in 10 seconds..."
        RETRY_COUNT=$((RETRY_COUNT + 1))
        
        if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
            # Clean temporary files and wait
            rm -rf /tmp/t-*
            sleep 10
        else
            echo "❌ Max retries reached. Build failed."
            exit 1
        fi
    fi
done

echo "🎉 Build process completed!"
ls -la dist/
