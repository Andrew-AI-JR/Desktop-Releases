const apiClient = require('../api/apiClient');

/**
 * Service for professional profile operations
 */
const profileService = {
  /**
   * Get the user's professional profile
   * @returns {Promise<Object>} Profile data
   */
  async getProfile() {
    try {
      const response = await apiClient.get('/api/profile/');
      return response.data;
    } catch (error) {
      console.error(
        'Get profile error:',
        error.response?.data || error.message
      );
      console.log('Get profile req:', {
        headers: error.request?.headers,
        data: error.request?.data,
        url: error.request?.url,
      });
      throw {
        message: error.response?.data?.detail || 'Failed to get profile',
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Update the user's professional profile
   * @param {Object} profileData - Profile data to update
   * @returns {Promise<Object>} Updated profile data
   */
  async updateProfile(profileData) {
    try {
      const response = await apiClient.post('/api/profile/', profileData);
      return response.data;
    } catch (error) {
      console.error(
        'Update profile error:',
        error.response?.data || error.message
      );
      throw {
        message: error.response?.data?.detail || 'Failed to update profile',
        status: error.response?.status || 500,
      };
    }
  },
};

module.exports = profileService;
