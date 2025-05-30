const automationService = require("../../services/automation/automationService");

/**
 * Handlers for automation-related IPC calls
 */
module.exports = {
  /**
   * Run LinkedIn automation
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {Object} config - Automation configuration
   * @returns {Promise<Object>} Automation status
   */
  runLinkedIn: async (event, config) => {
    try {
      return await automationService.runLinkedInAutomation(config);
    } catch (error) {
      console.error("Run LinkedIn automation error:", error);

      // Robust error message extraction
      let errorMessage = "Failed to run automation";

      if (typeof error === "string") {
        errorMessage = error;
      } else if (error && typeof error.message === "string") {
        errorMessage = error.message;
      } else if (error && typeof error === "object") {
        // Try to extract meaningful information from the error object
        const parts = [];
        if (error.message) parts.push(error.message);
        if (error.code) parts.push(`(${error.code})`);
        if (error.errno) parts.push(`errno: ${error.errno}`);
        if (error.syscall) parts.push(`syscall: ${error.syscall}`);
        if (error.path) parts.push(`path: ${error.path}`);

        errorMessage =
          parts.length > 0
            ? parts.join(" ")
            : error.toString !== Object.prototype.toString
            ? error.toString()
            : "Unknown error occurred";
      }

      // Only throw simple serializable objects
      const serializedError = new Error(errorMessage);
      serializedError.status = (error && error.status) || 500;

      throw serializedError;
    }
  },

  /**
   * Load persistent configuration
   * @param {Electron.IpcMainInvokeEvent} event
   * @returns {Promise<Object>} Loaded configuration
   */
  loadConfig: async (_event) => {
    try {
      const config = automationService.loadPersistentConfig();
      return {
        success: !!config,
        config,
      };
    } catch (error) {
      console.error("Load automation config error:", error);

      // Robust error message extraction
      let errorMessage = "Failed to load automation configuration";

      if (typeof error === "string") {
        errorMessage = error;
      } else if (error && typeof error.message === "string") {
        errorMessage = error.message;
      } else if (error && typeof error === "object") {
        const parts = [];
        if (error.message) parts.push(error.message);
        if (error.code) parts.push(`(${error.code})`);

        errorMessage =
          parts.length > 0
            ? parts.join(" ")
            : error.toString !== Object.prototype.toString
            ? error.toString()
            : "Failed to load automation configuration";
      }

      // Only throw simple serializable objects
      const serializedError = new Error(errorMessage);
      serializedError.status = (error && error.status) || 500;

      throw serializedError;
    }
  },

  /**
   * Stop running automation
   * @param {Electron.IpcMainInvokeEvent} event
   * @returns {Promise<Object>} Stop status
   */
  stop: async (_event) => {
    try {
      return await automationService.stopAutomation();
    } catch (error) {
      console.error("Stop automation error:", error);

      // Robust error message extraction
      let errorMessage = "Failed to stop automation";

      if (typeof error === "string") {
        errorMessage = error;
      } else if (error && typeof error.message === "string") {
        errorMessage = error.message;
      } else if (error && typeof error === "object") {
        const parts = [];
        if (error.message) parts.push(error.message);
        if (error.code) parts.push(`(${error.code})`);

        errorMessage =
          parts.length > 0
            ? parts.join(" ")
            : error.toString !== Object.prototype.toString
            ? error.toString()
            : "Failed to stop automation";
      }

      // Only throw simple serializable objects
      const serializedError = new Error(errorMessage);
      serializedError.status = (error && error.status) || 500;

      throw serializedError;
    }
  },
};
