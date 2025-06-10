const Store = require('electron-store');
const jwt = require('jsonwebtoken');

// Create a secure store for tokens
const tokenStore = new Store({
  name: 'auth-tokens',
  encryptionKey: 'junior-secure-app-token-encryption',
});

/**
 * Manager for authentication tokens
 */
const tokenManager = {
  /**
   * Store access and refresh tokens
   * @param {Object} tokens - Tokens {access_token, refresh_token}
   * @returns {Promise<void>}
   */
  async storeTokens(tokens) {
    try {
      tokenStore.set('tokens', tokens);
    } catch (error) {
      console.error('Error storing tokens:', error);
      throw new Error('Failed to store tokens');
    }
  },

  /**
   * Get the current access token
   * @returns {Promise<string|null>} Access token or null
   */
  async getAccessToken() {
    try {
      const tokens = tokenStore.get('tokens');
      return tokens?.access_token || null;
    } catch (error) {
      console.error('Error getting access token:', error);
      return null;
    }
  },

  /**
   * Get the current refresh token
   * @returns {Promise<string|null>} Refresh token or null
   */
  async getRefreshToken() {
    try {
      const tokens = tokenStore.get('tokens');
      return tokens?.refresh_token || null;
    } catch (error) {
      console.error('Error getting refresh token:', error);
      return null;
    }
  },

  /**
   * Clear all stored tokens
   * @returns {Promise<void>}
   */
  async clearTokens() {
    try {
      tokenStore.delete('tokens');
    } catch (error) {
      console.error('Error clearing tokens:', error);
      throw new Error('Failed to clear tokens');
    }
  },

  /**
   * Check if access token is expired
   * @returns {Promise<boolean>} True if expired, false otherwise
   */
  async isTokenExpired() {
    try {
      const accessToken = await this.getAccessToken();

      if (!accessToken) return true;

      // Decode token without verification to check expiration
      const decoded = jwt.decode(accessToken);
      if (!decoded || !decoded.exp) return true;

      // Check if token is expired with a 30-second buffer
      const currentTime = Math.floor(Date.now() / 1000);
      return decoded.exp <= currentTime + 30;
    } catch (error) {
      console.error('Error checking token expiration:', error);
      return true; // Consider expired on error
    }
  },
};

module.exports = tokenManager;
