# DMG Build Troubleshooting Guide

## The Problem

The `npm run build` was failing with:

```
⨯ Exit code: 35. Command failed: hdiutil resize failed. Resource temporarily unavailable (35)
```

This is a common macOS issue when creating DMG files due to system resource constraints.

## Solutions (in order of preference)

### 1. Use the Standard Build (Now Robust by Default)

```bash
npm run build:dmg
```

The default build now includes memory optimization and robust error handling.

### 2. Manual Resource Management

```bash
# Free up system memory first
sudo purge

# Clean build cache
rm -rf dist node_modules/.cache

# Then build
npm run build:dmg
```

### 3. Alternative DMG Format

The `package.json` now uses `UDBZ` format instead of `ULFO` which is more efficient and less resource-intensive.

### 4. System-Level Fixes

```bash
# Check disk space
df -h

# Check memory usage
vm_stat

# Kill any hung hdiutil processes
sudo pkill -f hdiutil

# Clean system temporary files
sudo rm -rf /tmp/t-*
```

## Build Scripts Available

- `npm run build` - Standard build (both architectures)
- `npm run build:dmg` - DMG build with memory optimization
- `npm run build:dmg:single` - x64 only DMG build
- `npm run build:dmg:arm` - arm64 only DMG build
- `npm run build:dmg:robust` - Robust build with retry logic

## Configuration Changes Made

1. **DMG Format**: Changed from `ULFO` to `UDBZ` for better efficiency
2. **Memory Settings**: Added Node.js memory optimization flags
3. **Build Options**: Added `buildDependenciesFromSource: false` to skip unnecessary rebuilds
4. **Retry Logic**: Robust script includes automatic retry with cleanup

## If All Else Fails

As a last resort, you can temporarily use ZIP format:

1. Change `"target": "dmg"` to `"target": "zip"` in `package.json`
2. Run `npm run build`
3. Change back to `"dmg"` when ready

The ZIP file works identically to DMG for distribution purposes.
