const authService = require('../../services/auth/authService');
const tokenManager = require('../../services/auth/tokenManager');

/**
 * Handlers for authentication-related IPC calls
 */
module.exports = {
  /**
   * Handle user login
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {Object} credentials - User credentials {email, password}
   * @returns {Promise<Object>} Token response or error object
   */
  login: async (event, credentials) => {
    const result = await authService.login(credentials);
    if (!result.success) {
      console.error('[authHandler] Login error:', result.error);
    }
    return result;
  },

  /**
   * Handle user registration
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {Object} userData - User registration data {email, password}
   * @returns {Promise<Object>} User response or error object
   */
  register: async (event, userData) => {
    const result = await authService.register(userData);
    if (!result.success) {
      console.error('[authHandler] Registration error:', result.error);
    }
    return result;
  },

  /**
   * Refresh the authentication token
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {string} refreshToken - Refresh token
   * @returns {Promise<Object>} New token response or error object
   */
  refreshToken: async (event, refreshToken) => {
    const result = await authService.refreshToken(refreshToken);
    if (!result.success) {
      console.error('[authHandler] Token refresh error:', result.error);
    }
    return result;
  },

  /**
   * Get the current user data
   * @param {Electron.IpcMainInvokeEvent} event
   * @returns {Promise<Object>} User data or error object
   */
  getUser: async _event => {
    const result = await authService.getCurrentUser();
    if (!result.success) {
      console.error('[authHandler] Get user error:', result.error);
    }
    return result;
  },

  /**
   * Update user bio
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {Object} bio - Bio update {bio: string}
   * @returns {Promise<Object>} Success response or error object
   */
  updateBio: async (event, bio) => {
    const result = await authService.updateBio(bio);
    if (!result.success) {
      console.error('[authHandler] Update bio error:', result.error);
    }
    return result;
  },

  /**
   * Get user bio
   * @param {Electron.IpcMainInvokeEvent} event
   * @returns {Promise<Object>} Bio response or error object
   */
  getBio: async _event => {
    const result = await authService.getBio();
    if (!result.success) {
      console.error('[authHandler] Get bio error:', result.error);
    }
    return result;
  },

  setTokens: async (_event, tokens) => {
    try {
      await tokenManager.storeTokens(tokens);
      return { success: true };
    } catch (error) {
      console.error('[authHandler] Set tokens error:', error);
      return {
        success: false,
        error: {
          message: error.message || 'Failed to store tokens',
          status: error.status || 500,
        },
      };
    }
  },

  getAccessToken: async _event => {
    try {
      const token = await tokenManager.getAccessToken();
      return { success: true, data: token };
    } catch (error) {
      console.error('[authHandler] Get access token error:', error);
      return {
        success: false,
        error: {
          message: error.message || 'Failed to get access token',
          status: error.status || 500,
        },
      };
    }
  },

  clearTokens: async _event => {
    try {
      await tokenManager.clearTokens();
      return { success: true };
    } catch (error) {
      console.error('[authHandler] Clear tokens error:', error);
      return {
        success: false,
        error: {
          message: error.message || 'Failed to clear tokens',
          status: error.status || 500,
        },
      };
    }
  },
};
