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

### Prerequisites

- Node.js (v16+)
- npm or yarn
- Electron v36+

### Setup

1. Clone the repository
2. Install dependencies:

```bash
npm install
```

3. Run the application:

```bash
# Development mode with DevTools
npm run dev

# Production mode
npm start
```

### Building

To build the application for distribution:

```bash
npm run build
```

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
