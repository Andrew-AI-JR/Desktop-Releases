const commentService = require("../../services/comments/commentService");

/**
 * Handlers for comment-related IPC calls
 */
module.exports = {
  /**
   * Generate a LinkedIn comment
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {Object} commentRequest - Comment generation request
   * @returns {Promise<Object>} Generated comment or error
   */
  generate: async (event, commentRequest) => {
    try {
      return await commentService.generateComment(commentRequest);
    } catch (error) {
      console.error("Comment generation error:", error);
      throw {
        message: error.message || "Failed to generate comment",
        status: error.status || 500,
      };
    }
  },
};
