const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const { setupIpcHandlers } = require("./ipc/ipcHandlers");
require("dotenv").config();

// Hot reload setup in development mode
try {
  if (process.argv.includes("--dev")) {
    require("electron-reloader")(module, {
      // Add directories to watch for changes
      watchRenderer: true, // Watch renderer process files
      ignore: [
        /node_modules|[/\\]\.git|[/\\]\.vscode|package.json|package-lock.json/,
      ],
    });
    console.log("Hot reload enabled");
  }
} catch (err) {
  console.error("Error setting up hot reload:", err);
}

// Keep a global reference of the window object to prevent garbage collection
let mainWindow;

// Create the browser window
const createWindow = () => {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  // Load the index.html of the app
  mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));

  // Open DevTools in development mode
  if (process.argv.includes("--dev")) {
    mainWindow.webContents.openDevTools();
  }
};

// Create window when Electron is ready
app.whenReady().then(() => {
  createWindow();
  setupIpcHandlers(ipcMain);

  // On macOS, re-create a window when dock icon is clicked
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

// Quit the app when all windows are closed (except on macOS)
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
