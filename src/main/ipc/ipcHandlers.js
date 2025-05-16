const authHandlers = require("./authHandlers");
const profileHandlers = require("./profileHandlers");
const paymentHandlers = require("./paymentHandlers");
const resumeHandlers = require("./resumeHandlers");
const commentHandlers = require("./commentHandlers");
const promptHandlers = require("./promptHandlers");
const automationHandlers = require("./automationHandlers");

/**
 * Sets up all IPC handlers for communication between main and renderer processes
 * @param {Electron.IpcMain} ipcMain - The Electron ipcMain instance
 */
function setupIpcHandlers(ipcMain) {
  // Auth handlers
  ipcMain.handle("auth:login", authHandlers.login);
  ipcMain.handle("auth:register", authHandlers.register);
  ipcMain.handle("auth:refreshToken", authHandlers.refreshToken);
  ipcMain.handle("auth:getUser", authHandlers.getUser);
  ipcMain.handle("auth:updateBio", authHandlers.updateBio);
  ipcMain.handle("auth:getBio", authHandlers.getBio);

  // Profile handlers
  ipcMain.handle("profile:get", profileHandlers.getProfile);
  ipcMain.handle("profile:update", profileHandlers.updateProfile);

  // Payment handlers
  ipcMain.handle("payments:createCustomer", paymentHandlers.createCustomer);
  ipcMain.handle(
    "payments:createSubscription",
    paymentHandlers.createSubscription
  );

  // Resume handlers
  ipcMain.handle("resumes:upload", resumeHandlers.upload);
  ipcMain.handle("resumes:list", resumeHandlers.list);
  ipcMain.handle("resumes:download", resumeHandlers.download);
  ipcMain.handle("resumes:delete", resumeHandlers.delete);

  // Comment handlers
  ipcMain.handle("comments:generate", commentHandlers.generate);

  // Prompt handlers
  ipcMain.handle("prompts:create", promptHandlers.create);
  ipcMain.handle("prompts:list", promptHandlers.list);
  ipcMain.handle("prompts:get", promptHandlers.get);
  ipcMain.handle("prompts:update", promptHandlers.update);
  ipcMain.handle("prompts:delete", promptHandlers.delete);

  // Automation handlers
  ipcMain.handle("automation:runLinkedIn", automationHandlers.runLinkedIn);
  ipcMain.handle("automation:stop", automationHandlers.stop);
}

module.exports = { setupIpcHandlers };
