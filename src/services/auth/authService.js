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
    try {
      const response = await apiClient.post('/api/users/token', credentials);
      if (response.data && response.data.access_token) {
        await tokenManager.storeTokens(response.data);
      }
      return { success: true, data: response.data };
    } catch (error) {
      const errorInfo = {
        message: error.response?.data?.detail || 'Login failed. Please check your credentials.',
        status: error.response?.status || 500,
      };
      console.error('Login error:', errorInfo);
      return { success: false, error: errorInfo };
    }
  },

  /**
   * Register a new user
   * @param {Object} userData - User registration data {email, password}
   * @returns {Promise<Object>} User data or error object
   */
  async register(userData) {
    try {
      const response = await apiClient.post('/api/users/register', userData);
      return { success: true, data: response.data };
    } catch (error) {
      const errorInfo = {
        message: error.response?.data?.detail || 'Registration failed. Please try again.',
        status: error.response?.status || 500,
      };
      console.error('Registration error:', errorInfo);
      return { success: false, error: errorInfo };
    }
  },

  /**
   * Request a password reset email.
   * @param {Object} data - Contains user's email { email }
   * @returns {Promise<Object>} Success or error object
   */
  async forgotPassword(data) {
    try {
      const response = await apiClient.post('/api/users/forgot-password', data);
      return { success: true, data: response.data };
    } catch (error) {
      const errorInfo = {
        message: error.response?.data?.detail || 'Failed to send password reset email.',
        status: error.response?.status || 500,
      };
      console.error('Forgot password error:', errorInfo);
      return { success: false, error: errorInfo };
    }
  },

  /**
   * Get the current authenticated user
   * @returns {Promise<Object>} User data or error object
   */
  async getCurrentUser() {
    try {
      // Check if we have a valid token first
      const accessToken = await tokenManager.getAccessToken();
      if (!accessToken) {
        return {
          success: false,
          error: {
            message: 'Not authenticated',
            status: 401,
          },
        };
      }

      // Check if token is expired
      if (await tokenManager.isTokenExpired()) {
        // Try to refresh the token
        const refreshToken = await tokenManager.getRefreshToken();
        if (!refreshToken) {
          await tokenManager.clearTokens();
          return {
            success: false,
            error: {
              message: 'Session expired. Please log in again.',
              status: 401,
            },
          };
        }

        try {
          const response = await apiClient.post('/api/users/token/refresh', {
            refresh_token: refreshToken,
          });

          if (response.data && response.data.access_token) {
            await tokenManager.storeTokens(response.data);
          }
        } catch (error) {
          await tokenManager.clearTokens();
          return {
            success: false,
            error: {
              message: 'Session expired. Please log in again.',
              status: 401,
            },
          };
        }
      }

      const response = await apiClient.get('/api/users/me');
      return { success: true, data: response.data };
    } catch (error) {
      // Handle specific error cases
      if (error.response?.status === 401) {
        await tokenManager.clearTokens();
        return {
          success: false,
          error: {
            message: 'Session expired. Please log in again.',
            status: 401,
          },
        };
      }

      const errorInfo = {
        message: error.response?.data?.detail || 'Failed to get user data.',
        status: error.response?.status || 500,
      };
      console.error('Get user error:', errorInfo);
      return { success: false, error: errorInfo };
    }
  },

  /**
   * Get subscription statistics for the current user
   * @returns {Promise<Object>} Subscription stats or error object
   */
  async getSubscriptionStats() {
    try {
      const response = await apiClient.get('/api/subscription/stats');
      return { success: true, data: response.data };
    } catch (error) {
      const errorInfo = {
        message: error.response?.data?.detail || 'Failed to get subscription stats.',
        status: error.response?.status || 500,
      };
      console.error('Get subscription stats error:', errorInfo);
      return { success: false, error: errorInfo };
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
      const errorInfo = {
        message: error.response?.data?.detail || 'Failed to update bio.',
        status: error.response?.status || 500,
      };
      console.error('Update bio error:', errorInfo);
      return { success: false, error: errorInfo };
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
      const errorInfo = {
        message: error.response?.data?.detail || 'Failed to get bio.',
        status: error.response?.status || 500,
      };
      console.error('Get bio error:', errorInfo);
      return { success: false, error: errorInfo };
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
      const errorInfo = {
        message: 'Logout failed',
        status: 500,
      };
      console.error('Logout error:', errorInfo);
      return { success: false, error: errorInfo };
    }
  },
};

module.exports = authService;
