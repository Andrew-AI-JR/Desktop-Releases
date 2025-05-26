const apiClient = require("../api/apiClient");
const tokenManager = require("./tokenManager");

/**
 * Service for authentication-related operations
 */
const authService = {
  /**
   * Login a user with credentials
   * @param {Object} credentials - User credentials {email, password}
   * @returns {Promise<Object>} Token data
   */
  async login(credentials) {
    console.log("Attempting to login with credentials:", credentials);
    try {
      const response = await apiClient.post("/api/users/token", credentials);

      // Store tokens for future use
      if (response.data && response.data.access_token) {
        await tokenManager.storeTokens(response.data);
      }

      return response.data;
    } catch (error) {
      console.error("Login error:", error.response?.data || error.message);
      throw {
        message: error.response?.data?.detail || "Login failed",
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Register a new user
   * @param {Object} userData - User registration data {email, password}
   * @returns {Promise<Object>} User data
   */
  async register(userData) {
    try {
      console.log(
        "Attempting to register at ",
        apiClient.defaults.baseURL,
        "path",
        "/api/users/register"
      );
      console.log("User data:", userData);
      const response = await apiClient.post("/api/users/register", userData);
      return response.data;
    } catch (error) {
      console.error(
        "Registration error:",
        error.response?.data || error.message
      );
      throw {
        message: error.response?.data?.detail || "Registration failed",
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Refresh the authentication token
   * @param {string} refreshToken - Refresh token
   * @returns {Promise<Object>} New token data
   */
  async refreshToken(refreshToken) {
    try {
      const response = await apiClient.post("/api/users/token/refresh", {
        refresh_token: refreshToken,
      });

      // Store new tokens
      if (response.data && response.data.access_token) {
        await tokenManager.storeTokens(response.data);
      }

      return response.data;
    } catch (error) {
      console.error(
        "Token refresh error:",
        error.response?.data || error.message
      );
      throw {
        message: error.response?.data?.detail || "Token refresh failed",
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Get the current authenticated user
   * @returns {Promise<Object>} User data
   */
  async getCurrentUser() {
    try {
      const response = await apiClient.get("/api/users/me");
      return response.data;
    } catch (error) {
      console.error("Get user error:", error.response?.data || error.message);
      throw {
        message: error.response?.data?.detail || "Failed to get user data",
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Update the user's bio
   * @param {Object} bioData - Bio update data {bio: string}
   * @returns {Promise<Object>} Response data
   */
  async updateBio(bioData) {
    try {
      const response = await apiClient.put("/api/users/bio", bioData);
      return response.data;
    } catch (error) {
      console.error("Update bio error:", error.response?.data || error.message);
      throw {
        message: error.response?.data?.detail || "Failed to update bio",
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Get the user's bio
   * @returns {Promise<Object>} Bio data
   */
  async getBio() {
    try {
      const response = await apiClient.get("/api/users/bio");
      return response.data;
    } catch (error) {
      console.error("Get bio error:", error.response?.data || error.message);
      throw {
        message: error.response?.data?.detail || "Failed to get bio",
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Log out the current user
   * @returns {Promise<void>}
   */
  async logout() {
    try {
      await tokenManager.clearTokens();
    } catch (error) {
      console.error("Logout error:", error.message);
      throw {
        message: "Logout failed",
        status: 500,
      };
    }
  },
};

module.exports = authService;
