const apiClient = require('../api/apiClient');
const tokenManager = require('./tokenManager');

/**
 * Service for authentication-related operations
 */
const authService = {
  /**
   * Login a user with credentials
   * @param {Object} credentials - User credentials {email, password}
   * @returns {Promise<Object>} Token data or error object
   */
  async login(credentials) {
    console.log('Attempting to login with credentials:', credentials);
    try {
      const response = await apiClient.post('/api/users/token', credentials);

      // Store tokens for future use
      if (response.data && response.data.access_token) {
        await tokenManager.storeTokens(response.data);
      }

      return { success: true, data: response.data };
    } catch (error) {
      console.error('Login error:', error.response?.data || error.message);
      return {
        success: false,
        error: {
          message: error.response?.data?.detail || 'Login failed',
          status: error.response?.status || 500,
          data: error,
        },
      };
    }
  },

  /**
   * Register a new user
   * @param {Object} userData - User registration data {email, password}
   * @returns {Promise<Object>} User data or error object
   */
  async register(userData) {
    try {
      console.log(
        'Attempting to register at ',
        apiClient.defaults.baseURL,
        'path',
        '/api/users/register'
      );
      console.log('User data:', userData);
      const response = await apiClient.post('/api/users/register', userData);
      return { success: true, data: response.data };
    } catch (error) {
      console.error(
        'Registration error:',
        error.response?.data || error.message
      );
      return {
        success: false,
        error: {
          message: error.response?.data?.detail || 'Registration failed',
          status: error.response?.status || 500,
        },
      };
    }
  },

  /**
   * Refresh the authentication token
   * @param {string} refreshToken - Refresh token
   * @returns {Promise<Object>} New token data or error object
   */
  async refreshToken(refreshToken) {
    try {
      const response = await apiClient.post('/api/users/token/refresh', {
        refresh_token: refreshToken,
      });

      // Store new tokens
      if (response.data && response.data.access_token) {
        await tokenManager.storeTokens(response.data);
      }

      return { success: true, data: response.data };
    } catch (error) {
      console.error(
        'Token refresh error:',
        error.response?.data || error.message
      );
      return {
        success: false,
        error: {
          message: error.response?.data?.detail || 'Token refresh failed',
          status: error.response?.status || 500,
        },
      };
    }
  },

  /**
   * Get the current authenticated user
   * @returns {Promise<Object>} User data or error object
   */
  async getCurrentUser() {
    try {
      const response = await apiClient.get('/api/users/me');
      return { success: true, data: response.data };
    } catch (error) {
      console.error('Get user error:', error.response?.data || error.message);
      return {
        success: false,
        error: {
          message: error.response?.data?.detail || 'Failed to get user data',
          status: error.response?.status || 500,
        },
      };
    }
  },

  /**
   * Update the user's bio
   * @param {Object} bioData - Bio update data {bio: string}
   * @returns {Promise<Object>} Response data or error object
   */
  async updateBio(bioData) {
    try {
      const response = await apiClient.put('/api/users/bio', bioData);
      return { success: true, data: response.data };
    } catch (error) {
      console.error('Update bio error:', error.response?.data || error.message);
      return {
        success: false,
        error: {
          message: error.response?.data?.detail || 'Failed to update bio',
          status: error.response?.status || 500,
        },
      };
    }
  },

  /**
   * Get the user's bio
   * @returns {Promise<Object>} Bio data or error object
   */
  async getBio() {
    try {
      const response = await apiClient.get('/api/users/bio');
      return { success: true, data: response.data };
    } catch (error) {
      console.error('Get bio error:', error.response?.data || error.message);
      return {
        success: false,
        error: {
          message: error.response?.data?.detail || 'Failed to get bio',
          status: error.response?.status || 500,
        },
      };
    }
  },

  /**
   * Log out the current user
   * @returns {Promise<Object>} Success or error object
   */
  async logout() {
    try {
      await tokenManager.clearTokens();
      return { success: true };
    } catch (error) {
      console.error('Logout error:', error.message);
      return {
        success: false,
        error: {
          message: 'Logout failed',
          status: 500,
        },
      };
    }
  },
};

module.exports = authService;
