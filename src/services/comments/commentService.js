const apiClient = require("../api/apiClient");

/**
 * Service for comment-related operations
 */
const commentService = {
  /**
   * Generate a LinkedIn comment
   * @param {Object} commentRequest - Comment generation request
   * @returns {Promise<Object>} Generated comment data
   */
  async generateComment(commentRequest) {
    try {
      const response = await apiClient.post(
        "/api/comments/generate",
        commentRequest
      );
      return response.data;
    } catch (error) {
      console.error(
        "Comment generation error:",
        error.response?.data || error.message
      );
      throw {
        message: error.response?.data?.detail || "Failed to generate comment",
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Save a comment to history (if implemented)
   * @param {Object} commentData - Comment data to save
   * @returns {Promise<Object>} Saved comment data
   */
  async saveComment(commentData) {
    try {
      // This would typically involve saving to a database or storage
      // For demo purposes, we'll just return the data
      return commentData;
    } catch (error) {
      console.error("Save comment error:", error);
      throw {
        message: "Failed to save comment",
        status: 500,
      };
    }
  },
};

module.exports = commentService;
