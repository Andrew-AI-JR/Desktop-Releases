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
      throw {
        message: error.message || "Failed to run automation",
        status: error.status || 500,
      };
    }
  },

  /**
   * Load persistent configuration
   * @param {Electron.IpcMainInvokeEvent} event
   * @returns {Promise<Object>} Loaded configuration
   */
  loadConfig: async (event) => {
    try {
      const config = automationService.loadPersistentConfig();
      return {
        success: !!config,
        config,
      };
    } catch (error) {
      console.error("Load automation config error:", error);
      throw {
        message: error.message || "Failed to load automation configuration",
        status: error.status || 500,
      };
    }
  },

  /**
   * Stop running automation
   * @param {Electron.IpcMainInvokeEvent} event
   * @returns {Promise<Object>} Stop status
   */
  stop: async (event) => {
    try {
      return await automationService.stopAutomation();
    } catch (error) {
      console.error("Stop automation error:", error);
      throw {
        message: error.message || "Failed to stop automation",
        status: error.status || 500,
      };
    }
  },
};
