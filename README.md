# Junior Desktop

An Electron-based desktop application for LinkedIn automation and comment generation.

## Project Structure

```
junior-desktop/
├── assets/               # Static assets
│   ├── fonts/            # Font files
│   ├── icons/            # App icons
│   ├── images/           # Images used in the app
├── build/                # Build output
├── config/               # Configuration files
├── src/                  # Source code
│   ├── main/             # Main process (Node.js)
│   │   ├── main.js       # Main entry point
│   │   ├── preload.js    # Preload script for secure IPC
│   │   ├── ipc/          # IPC handlers
│   ├── renderer/         # Renderer process (Browser)
│   │   ├── index.html    # Main HTML file
│   │   ├── components/   # Reusable UI components
│   │   ├── css/          # Stylesheets
│   │   ├── js/           # JavaScript files
│   │       ├── app.js    # Main renderer script
│   │       ├── controllers/ # UI controllers
│   │       ├── utils/    # Utility functions
│   ├── services/         # Shared services
│       ├── api/          # API client
│       ├── auth/         # Authentication services
│       ├── automation/   # Browser automation
├── package.json          # Dependencies and scripts
├── openapi_spec.json     # API specification
└── README.md             # Project documentation
```

## Features

- User authentication (login/register)
- Profile management
- Subscription handling
- Resume upload and management
- LinkedIn comment generation
- LinkedIn post automation
- Custom prompt management

## Development

### Quick Start

For detailed setup instructions, see **[Developer Setup Guide](docs/DEVELOPER_SETUP.md)**.

#### Prerequisites

- Node.js (v16+)
- Python (v3.8+)
- Platform-specific build tools

#### Basic Setup

```bash
# Clone and install dependencies
npm install

# Build Python automation components
npm run build:python

# Run in development mode
npm run dev
```

### Building

```bash
# Build for current platform
npm run build

# Platform-specific builds
npm run build:mac     # macOS
npm run build:win     # Windows
npm run build:linux   # Linux
npm run build:dmg     # macOS DMG
```

### Code Quality

```bash
npm run lint          # Check code style
npm run lint:fix      # Auto-fix issues
```

## Documentation

- **[Developer Setup Guide](docs/DEVELOPER_SETUP.md)** - Complete setup instructions for new developers
- **[Python Bundling Guide](docs/PYTHON_BUNDLING.md)** - Python automation component details
- **[DMG Build Troubleshooting](docs/DMG_BUILD_TROUBLESHOOTING.md)** - macOS build issues and solutions
- **[Cross-Platform Development](docs/CROSS_PLATFORM_DEVELOPMENT.md)** - Multi-platform development guide

## API Integration

This app integrates with the Junior API specified in the `openapi_spec.json` file. The API provides:

- User authentication
- Profile management
- Payment processing
- Resume management
- Comment generation
- Prompt management

## Architecture

The application follows the main/renderer process architecture of Electron:

1. **Main Process** (Node.js)

   - Handles API communication
   - Manages browser automation
   - Controls the application lifecycle
   - Provides secure IPC channels

2. **Renderer Process** (Browser)

   - Renders the UI
   - Handles user interactions
   - Communicates with the main process via IPC

3. **Services**
   - API client for communicating with the backend
   - Authentication service for managing user sessions
   - Automation service for LinkedIn interactions

## Security

- Secure storage of credentials using `electron-store` with encryption
- Context isolation between processes
- Proper content security policy
- Secure IPC communication
