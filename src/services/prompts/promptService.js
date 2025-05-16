const apiClient = require("../api/apiClient");

/**
 * Service for prompt-related operations
 */
const promptService = {
  /**
   * Create a new prompt
   * @param {Object} promptData - Prompt data
   * @returns {Promise<Object>} Created prompt
   */
  async createPrompt(promptData) {
    try {
      const response = await apiClient.post("/api/prompts/", promptData);
      return response.data;
    } catch (error) {
      console.error(
        "Create prompt error:",
        error.response?.data || error.message
      );
      throw {
        message: error.response?.data?.detail || "Failed to create prompt",
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Get a list of prompts
   * @param {Object} filters - Optional filters (prompt_type, scope)
   * @returns {Promise<Array>} List of prompts
   */
  async listPrompts(filters = {}) {
    try {
      const queryParams = new URLSearchParams();

      if (filters.prompt_type) {
        queryParams.append("prompt_type", filters.prompt_type);
      }

      if (filters.scope) {
        queryParams.append("scope", filters.scope);
      }

      const url = `/api/prompts/${
        queryParams.toString() ? `?${queryParams.toString()}` : ""
      }`;
      const response = await apiClient.get(url);

      return response.data;
    } catch (error) {
      console.error(
        "List prompts error:",
        error.response?.data || error.message
      );
      throw {
        message: error.response?.data?.detail || "Failed to list prompts",
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Get a specific prompt
   * @param {number} promptId - Prompt ID
   * @returns {Promise<Object>} Prompt data
   */
  async getPrompt(promptId) {
    try {
      const response = await apiClient.get(`/api/prompts/${promptId}`);
      return response.data;
    } catch (error) {
      console.error("Get prompt error:", error.response?.data || error.message);
      throw {
        message: error.response?.data?.detail || "Failed to get prompt",
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Update a prompt
   * @param {number} promptId - Prompt ID
   * @param {Object} promptData - Updated prompt data
   * @returns {Promise<Object>} Updated prompt
   */
  async updatePrompt(promptId, promptData) {
    try {
      const response = await apiClient.put(
        `/api/prompts/${promptId}`,
        promptData
      );
      return response.data;
    } catch (error) {
      console.error(
        "Update prompt error:",
        error.response?.data || error.message
      );
      throw {
        message: error.response?.data?.detail || "Failed to update prompt",
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Delete a prompt
   * @param {number} promptId - Prompt ID
   * @returns {Promise<void>}
   */
  async deletePrompt(promptId) {
    try {
      await apiClient.delete(`/api/prompts/${promptId}`);
    } catch (error) {
      console.error(
        "Delete prompt error:",
        error.response?.data || error.message
      );
      throw {
        message: error.response?.data?.detail || "Failed to delete prompt",
        status: error.response?.status || 500,
      };
    }
  },
};

module.exports = promptService;
