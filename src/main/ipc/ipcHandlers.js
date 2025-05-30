const authHandlers = require('./authHandlers');
const automationHandlers = require('./automationHandlers');

/**
 * Sets up all IPC handlers for communication between main and renderer processes
 * @param {Electron.IpcMain} ipcMain - The Electron ipcMain instance
 */
function setupIpcHandlers(ipcMain) {
  // Auth handlers
  ipcMain.handle('auth:login', authHandlers.login);
  ipcMain.handle('auth:register', authHandlers.register);
  ipcMain.handle('auth:refreshToken', authHandlers.refreshToken);
  ipcMain.handle('auth:getUser', authHandlers.getUser);
  ipcMain.handle('auth:updateBio', authHandlers.updateBio);
  ipcMain.handle('auth:getBio', authHandlers.getBio);
  ipcMain.handle('auth:setTokens', authHandlers.setTokens);
  ipcMain.handle('auth:getAccessToken', authHandlers.getAccessToken);
  ipcMain.handle('auth:clearTokens', authHandlers.clearTokens);

  // Automation handlers
  ipcMain.handle('automation:runLinkedIn', automationHandlers.runLinkedIn);
  ipcMain.handle('automation:stop', automationHandlers.stop);
  ipcMain.handle('automation:loadConfig', automationHandlers.loadConfig);
}

module.exports = { setupIpcHandlers };
