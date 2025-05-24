const authService = require("../../services/auth/authService");

/**
 * Handlers for authentication-related IPC calls
 */
module.exports = {
  /**
   * Handle user login
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {Object} credentials - User credentials {email, password}
   * @returns {Promise<Object>} Token response or error
   */
  login: async (event, credentials) => {
    try {
      return await authService.login(credentials);
    } catch (error) {
      console.error("Login error:", error);
      throw {
        message: error.message || "Login failed",
        status: error.status || 500,
      };
    }
  },

  /**
   * Handle user registration
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {Object} userData - User registration data {email, password}
   * @returns {Promise<Object>} User response or error
   */
  register: async (event, userData) => {
    try {
      return await authService.register(userData);
    } catch (error) {
      console.error("[authHandler] Registration error:", error);
      throw {
        message: error.message || "Registration failed",
        status: error.status || 500,
      };
    }
  },

  /**
   * Refresh the authentication token
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {string} refreshToken - Refresh token
   * @returns {Promise<Object>} New token response or error
   */
  refreshToken: async (event, refreshToken) => {
    try {
      return await authService.refreshToken(refreshToken);
    } catch (error) {
      console.error("Token refresh error:", error);
      throw {
        message: error.message || "Token refresh failed",
        status: error.status || 500,
      };
    }
  },

  /**
   * Get the current user data
   * @param {Electron.IpcMainInvokeEvent} event
   * @returns {Promise<Object>} User data or error
   */
  getUser: async (event) => {
    try {
      return await authService.getCurrentUser();
    } catch (error) {
      console.error("Get user error:", error);
      throw {
        message: error.message || "Failed to get user data",
        status: error.status || 500,
      };
    }
  },

  /**
   * Update user bio
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {Object} bio - Bio update {bio: string}
   * @returns {Promise<Object>} Success response or error
   */
  updateBio: async (event, bio) => {
    try {
      return await authService.updateBio(bio);
    } catch (error) {
      console.error("Update bio error:", error);
      throw {
        message: error.message || "Failed to update bio",
        status: error.status || 500,
      };
    }
  },

  /**
   * Get user bio
   * @param {Electron.IpcMainInvokeEvent} event
   * @returns {Promise<Object>} Bio response or error
   */
  getBio: async (event) => {
    try {
      return await authService.getBio();
    } catch (error) {
      console.error("Get bio error:", error);
      throw {
        message: error.message || "Failed to get bio",
        status: error.status || 500,
      };
    }
  },
};
