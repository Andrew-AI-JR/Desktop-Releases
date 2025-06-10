# Developer Setup Guide

This guide will help new developers get the Junior Desktop application running locally and understand the development workflow.

## Prerequisites

Before you start, ensure you have the following installed on your system:

### Required Software

1. **Node.js** (v16 or higher)

   - Download from [nodejs.org](https://nodejs.org/)
   - Verify installation: `node --version` and `npm --version`

2. **Python** (v3.8 or higher)

   - Download from [python.org](https://www.python.org/)
   - Verify installation: `python --version` or `python3 --version`
   - **Important**: Python is required for the LinkedIn automation features

3. **Git**
   - Download from [git-scm.com](https://git-scm.com/)
   - Verify installation: `git --version`

### Platform-Specific Requirements

#### macOS

- **Xcode Command Line Tools**: `xcode-select --install`
- **PyInstaller dependencies**: Will be installed automatically

#### Windows

- **Microsoft Build Tools** or **Visual Studio** (for native modules)
- **Python for Windows** (ensure it's added to PATH)

#### Linux

- **Build essentials**: `sudo apt-get install build-essential`
- **Python dev headers**: `sudo apt-get install python3-dev`

## Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd junior-desktop
```

### 2. Install Dependencies

```bash
npm install
```

This will install all Node.js dependencies including Electron, build tools, and development utilities.

### 3. Set Up Environment Variables

Create a `.env` file in the root directory:

```bash
cp .env.example .env  # If .env.example exists
# or create .env manually
```

Required environment variables:

```
# API Configuration
API_BASE_URL=https://api.junior.com
API_KEY=your_api_key_here

# Development settings
NODE_ENV=development
ELECTRON_ENV=development
```

### 4. Build Python Components

The application includes Python automation scripts that need to be bundled:

```bash
npm run build:python
```

This command:

- Creates Python virtual environments
- Installs required Python dependencies
- Uses PyInstaller to create standalone executables
- Places executables in `resources/python-executables/`

### 5. Run the Application

```bash
# Development mode (with DevTools and hot reload)
npm run dev

# Production mode (without DevTools)
npm start
```

The application should launch and display the main window.

## Development Workflow

### Project Structure Overview

```
junior-desktop/
├── src/
│   ├── main/                 # Electron main process (Node.js)
│   │   ├── main.js          # Application entry point
│   │   ├── preload.js       # Secure IPC bridge
│   │   └── ipc/             # IPC handlers for various features
│   ├── renderer/            # Electron renderer process (Browser)
│   │   ├── index.html       # Main HTML file
│   │   ├── css/             # Stylesheets
│   │   ├── js/              # JavaScript files
│   │   └── components/      # Reusable UI components
│   ├── services/            # Shared business logic
│   │   ├── api/             # API communication
│   │   ├── auth/            # Authentication
│   │   └── automation/      # LinkedIn automation
│   └── resources/           # Static resources and Python scripts
├── scripts/                 # Build and automation scripts
├── docs/                    # Documentation
├── config/                  # Configuration files
└── dist/                    # Build output (generated)
```

### Key Development Commands

```bash
# Development
npm run dev              # Start in development mode
npm run lint             # Check code style and errors
npm run lint:fix         # Automatically fix linting issues

# Building
npm run build            # Build for current platform
npm run build:mac        # Build for macOS
npm run build:win        # Build for Windows
npm run build:linux      # Build for Linux
npm run build:dmg        # Build DMG for macOS

# Python components
npm run build:python     # Build Python executables
npm run build:python:force  # Force rebuild Python components

# Maintenance
npm run clean            # Clean build artifacts
```

### Code Quality

This project uses ESLint for code quality. Before committing:

```bash
npm run lint             # Check for issues
npm run lint:fix         # Auto-fix issues
```

**Important**: All code must pass linting before being committed.

## Key Features to Understand

### 1. LinkedIn Automation

- Uses Python scripts with Selenium for browser automation
- Scripts are bundled as standalone executables using PyInstaller
- Cross-platform support (Windows, macOS, Linux)
- Chrome browser detection and integration

### 2. IPC Communication

- Secure communication between main and renderer processes
- Handlers in `src/main/ipc/` for different features
- Error handling and message serialization

### 3. Authentication

- JWT-based authentication with the Junior API
- Secure credential storage using electron-store
- Session management and token refresh

### 4. Build System

- Electron Builder for creating distributable packages
- Cross-platform Python bundling
- DMG creation for macOS with optimized settings

## Troubleshooting

### Common Issues

#### 1. Python Build Failures

```bash
# Clean and rebuild Python components
npm run build:python:force
```

#### 2. Node.js Memory Issues

```bash
# Increase memory limit (already configured in package.json)
NODE_OPTIONS='--max-old-space-size=4096' npm run build
```

#### 3. DMG Build Errors on macOS

- See `docs/DMG_BUILD_TROUBLESHOOTING.md` for detailed solutions
- Common fix: Ensure Xcode Command Line Tools are installed

#### 4. Permission Errors

```bash
# Fix npm permissions (macOS/Linux)
sudo chown -R $(whoami) ~/.npm
```

### Development Environment Issues

#### Application Won't Start

1. Check that all dependencies are installed: `npm install`
2. Verify Python is available: `python --version`
3. Rebuild Python components: `npm run build:python:force`
4. Check the console for error messages

#### Python Automation Not Working

1. Ensure Chrome is installed on your system
2. Check Python executable exists: `ls resources/python-executables/`
3. Test Python script directly: `python src/resources/scripts/linkedin_commenter.py --help`

#### Build Failures

1. Clean previous builds: `npm run clean`
2. Update Node.js if using an old version
3. Check platform-specific requirements above

## Additional Documentation

For specific topics, refer to:

- **Python Bundling**: `docs/PYTHON_BUNDLING.md`
- **DMG Build Issues**: `docs/DMG_BUILD_TROUBLESHOOTING.md`
- **Cross-Platform Development**: `docs/CROSS_PLATFORM_DEVELOPMENT.md`

## Getting Help

1. Check the documentation in the `docs/` folder
2. Look for similar issues in the project's issue tracker
3. Review the application logs (available in DevTools console)
4. Test the Python components independently before debugging the full application

## Development Best Practices

1. **Always run linting** before committing code
2. **Test on multiple platforms** if making build system changes
3. **Update documentation** when adding new features
4. **Follow the existing code style** and architecture patterns
5. **Use the IPC system** for main/renderer communication
6. **Handle errors gracefully** and provide meaningful error messages

## Next Steps

Once you have the application running:

1. Explore the codebase starting with `src/main/main.js`
2. Understand the IPC communication patterns
3. Review the automation service implementation
4. Test the LinkedIn automation features
5. Experiment with the build system

Happy coding! 🚀
