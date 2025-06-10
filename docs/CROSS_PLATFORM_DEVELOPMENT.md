# Cross-Platform Development Guide

This guide explains how to work with the Junior Desktop application across different platforms during development.

## 🎯 **Development Workflow**

### **Quick Start (Any Platform)**

```bash
# Clone and setup
git clone [your-repo]
cd junior-desktop
npm install

# First time setup - builds Python executable for your platform
npm run build:python

# Start development
npm start
```

### **How `npm run build` Works on Each Platform**

#### **macOS (Your Current Platform)**

```bash
npm run build:python  # ✅ Creates resources/python-executables/mac-arm64/linkedin_commenter
npm run build         # ✅ Creates Junior Desktop.dmg with bundled Python
```

#### **Windows Development**

```bash
npm run build:python  # ✅ Creates resources/python-executables/win-x64/linkedin_commenter.exe
npm run build         # ✅ Creates Junior Desktop Setup.exe with bundled Python
```

#### **Linux Development**

```bash
npm run build:python  # ✅ Creates resources/python-executables/linux-x64/linkedin_commenter
npm run build         # ✅ Creates Junior Desktop.AppImage with bundled Python
```

## 🔄 **Smart Development Features**

### **Incremental Builds**

The build system is optimized for development:

```bash
# First run: Downloads dependencies, builds executable (~2-3 minutes)
npm run build:python

# Subsequent runs: Skips if executable exists (~5 seconds)
npm run build:python  # ✅ "Executable already exists, skipping..."

# Force rebuild when needed
npm run build:python:force  # Deletes and rebuilds
```

### **Platform Detection**

The system automatically detects your platform:

```javascript
// Automatically creates the right executable:
// macOS ARM64: mac-arm64/linkedin_commenter
// macOS Intel: mac-x64/linkedin_commenter
// Windows 64:  win-x64/linkedin_commenter.exe
// Linux 64:    linux-x64/linkedin_commenter
```

## 📁 **Directory Structure During Development**

```
junior-desktop/
├── resources/python-executables/
│   └── mac-arm64/                    # ← Built for your platform
│       ├── linkedin_commenter        # ← 23MB standalone executable
│       └── linkedin_commenter.log    # ← Runtime logs
├── build/pyinstaller/                # ← Build cache (can be deleted)
├── dist/                            # ← Final app packages
└── src/services/automation/
    ├── automationService.js         # ← Detects bundled Python automatically
    └── pythonBundleService.js       # ← Cross-platform executable management
```

## 🎯 **Available Scripts**

| Script                       | Purpose                                      | When to Use                                  |
| ---------------------------- | -------------------------------------------- | -------------------------------------------- |
| `npm start`                  | Start app in development                     | Daily development                            |
| `npm run build:python`       | Build Python executable for current platform | First time, after Python changes             |
| `npm run build:python:force` | Force rebuild Python executable              | When executable is corrupted                 |
| `npm run build`              | Build complete application package           | Testing full app, preparing for distribution |
| `npm run clean`              | Clean all build artifacts                    | When builds are acting strange               |

## 🚀 **GitHub Actions (Production Builds)**

The GitHub Actions workflow builds for ALL platforms automatically:

```yaml
# Triggered on:
git push origin main        # → Builds all platforms, creates artifacts
git tag v1.0.0             # → Builds all platforms, creates GitHub release
git push origin v1.0.0     # → Downloads include .dmg, .exe, .AppImage
```

## ⚡ **Development Tips**

### **Fast Development Cycle**

```bash
# Day 1: Initial setup (slow)
npm install                 # ~1 minute
npm run build:python       # ~2-3 minutes (downloads everything)

# Day 2+: Fast development (fast)
npm start                   # ~3 seconds (uses existing executable)
npm run build              # ~30 seconds (just packages app)
```

### **When to Rebuild Python Executable**

- ✅ **Never**: During UI/JavaScript development
- ✅ **Rarely**: When `requirements.txt` changes
- ✅ **Sometimes**: When `linkedin_commenter.py` changes
- ✅ **Always**: When switching between development machines

### **Troubleshooting**

```bash
# Python executable issues
npm run build:python:force   # Rebuilds from scratch

# Electron build issues
npm run clean               # Cleans all caches
npm install                 # Reinstalls dependencies

# "Python not found" errors
which python3               # Check Python installation
python3 --version           # Should be 3.8+
```

## 🔧 **Platform-Specific Notes**

### **macOS**

- ✅ Uses `python3` command
- ✅ Creates universal binaries (ARM64 + Intel)
- ✅ Code signing supported (set `CSC_LINK` and `CSC_KEY_PASSWORD`)

### **Windows**

- ✅ Uses `python` command
- ✅ Creates `.exe` and `.msi` installers
- ✅ Auto-updater supported

### **Linux**

- ✅ Uses `python3` command
- ✅ Creates `.AppImage`, `.deb`, and `.rpm` packages
- ✅ Desktop integration included

## 🎯 **Summary**

**For Development**: `npm run build` works on any platform and creates a complete, redistributable application with Python bundled in.

**For Production**: GitHub Actions automatically builds for all platforms when you push tags, creating download-ready installers for users.

**No Python Required for End Users**: The final applications are completely self-contained! 🎉
