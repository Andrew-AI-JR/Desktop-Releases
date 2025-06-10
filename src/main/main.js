const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { setupIpcHandlers } = require('./ipc/ipcHandlers');
require('dotenv').config({
  path: app.isPackaged
    ? path.join(process.resourcesPath, '.env')
    : path.resolve(process.cwd(), '.env'),
});

// Hot reload setup in development mode
try {
  if (process.argv.includes('--dev')) {
    require('electron-reloader')(module, {
      // Add directories to watch for changes
      watchRenderer: true, // Watch renderer process files
      ignore: [
        /node_modules|[/\\]\.git|[/\\]\.vscode|package.json|package-lock.json/,
      ],
    });
    console.log('Hot reload enabled');
  }
} catch (err) {
  console.error('Error setting up hot reload:', err);
}

// Keep a global reference of the window object to prevent garbage collection
let mainWindow;

// Create the browser window
const createWindow = () => {
  // Determine the appropriate icon path based on platform
  let iconPath;
  if (process.platform === 'darwin') {
    // macOS - use ICNS
    iconPath = path.join(__dirname, '../../assets/icons/icon.icns');
  } else if (process.platform === 'win32') {
    // Windows - use ICO (you'll need to create this)
    iconPath = path.join(__dirname, '../../assets/icons/icon.ico');
  } else {
    // Linux and others - use PNG (you'll need to create this)
    iconPath = path.join(__dirname, '../../assets/icons/icon.png');
  }

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    title: 'Junior Desktop',
    icon: iconPath,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  // Load the index.html of the app
  mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'));

  // Open DevTools in development mode
  if (process.argv.includes('--dev')) {
    mainWindow.webContents.openDevTools();
  }
};

// Create window when Electron is ready
app.whenReady().then(() => {
  createWindow();

  // Make the mainWindow available globally for IPC events
  global.mainWindow = mainWindow;

  setupIpcHandlers(ipcMain);

  // On macOS, re-create a window when dock icon is clicked
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

// Quit the app when all windows are closed (except on macOS)
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
