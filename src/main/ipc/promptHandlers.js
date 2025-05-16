const promptService = require("../../services/prompts/promptService");

/**
 * Handlers for prompt-related IPC calls
 */
module.exports = {
  /**
   * Create a new prompt
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {Object} promptData - Prompt data to create
   * @returns {Promise<Object>} Created prompt
   */
  create: async (event, promptData) => {
    try {
      return await promptService.createPrompt(promptData);
    } catch (error) {
      console.error("Create prompt error:", error);
      throw {
        message: error.message || "Failed to create prompt",
        status: error.status || 500,
      };
    }
  },

  /**
   * List prompts with optional filters
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {Object} filters - Optional filters (prompt_type, scope)
   * @returns {Promise<Array>} List of prompts
   */
  list: async (event, filters = {}) => {
    try {
      return await promptService.listPrompts(filters);
    } catch (error) {
      console.error("List prompts error:", error);
      throw {
        message: error.message || "Failed to list prompts",
        status: error.status || 500,
      };
    }
  },

  /**
   * Get a specific prompt
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {number} promptId - Prompt ID
   * @returns {Promise<Object>} Prompt data
   */
  get: async (event, promptId) => {
    try {
      return await promptService.getPrompt(promptId);
    } catch (error) {
      console.error("Get prompt error:", error);
      throw {
        message: error.message || "Failed to get prompt",
        status: error.status || 500,
      };
    }
  },

  /**
   * Update a prompt
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {number} promptId - Prompt ID
   * @param {Object} promptData - Updated prompt data
   * @returns {Promise<Object>} Updated prompt
   */
  update: async (event, promptId, promptData) => {
    try {
      return await promptService.updatePrompt(promptId, promptData);
    } catch (error) {
      console.error("Update prompt error:", error);
      throw {
        message: error.message || "Failed to update prompt",
        status: error.status || 500,
      };
    }
  },

  /**
   * Delete a prompt
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {number} promptId - Prompt ID
   * @returns {Promise<void>}
   */
  delete: async (event, promptId) => {
    try {
      await promptService.deletePrompt(promptId);
      return { success: true };
    } catch (error) {
      console.error("Delete prompt error:", error);
      throw {
        message: error.message || "Failed to delete prompt",
        status: error.status || 500,
      };
    }
  },
};
