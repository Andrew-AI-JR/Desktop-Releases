const automationService = require('../../services/automation/automationService');

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
      const result = await automationService.runLinkedInAutomation(config);
      return result;
    } catch (error) {
      console.error(
        '[runLinkedIn] Run LinkedIn automation error:',
        error?.message
      );

      // Return error instead of throwing to avoid Electron IPC wrapper
      return {
        success: false,
        error: true,
        message: error?.message || 'Unknown error',
        originalError: error,
      };
    }
  },

  /**
   * Load persistent configuration
   * @param {Electron.IpcMainInvokeEvent} event
   * @returns {Promise<Object>} Loaded configuration
   */
  loadConfig: async _event => {
    try {
      const config = automationService.loadPersistentConfig();
      return {
        success: !!config,
        config,
      };
    } catch (error) {
      console.error('[loadConfig] Load automation config error:', error);

      // Return error instead of throwing
      return {
        success: false,
        error: true,
        message: error?.message || 'Unknown error',
        originalError: error,
      };
    }
  },

  /**
   * Stop running automation
   * @param {Electron.IpcMainInvokeEvent} event
   * @returns {Promise<Object>} Stop status
   */
  stop: async _event => {
    try {
      return await automationService.stopAutomation();
    } catch (error) {
      console.error('[stopAutomation] Error:', error);

      // Return error instead of throwing
      return {
        success: false,
        error: true,
        message: error?.message || 'Unknown error',
        originalError: error,
      };
    }
  },
};
