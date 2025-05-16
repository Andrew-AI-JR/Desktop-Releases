const profileService = require("../../services/profile/profileService");

/**
 * Handlers for profile-related IPC calls
 */
module.exports = {
  /**
   * Get the user's professional profile
   * @param {Electron.IpcMainInvokeEvent} event
   * @returns {Promise<Object>} Profile data or error
   */
  getProfile: async (event) => {
    try {
      return await profileService.getProfile();
    } catch (error) {
      console.error("Get profile error:", error);
      throw {
        message: error.message || "Failed to get profile",
        status: error.status || 500,
      };
    }
  },

  /**
   * Update the user's professional profile
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {Object} profileData - Profile update data
   * @returns {Promise<Object>} Updated profile data or error
   */
  updateProfile: async (event, profileData) => {
    try {
      return await profileService.updateProfile(profileData);
    } catch (error) {
      console.error("Update profile error:", error);
      throw {
        message: error.message || "Failed to update profile",
        status: error.status || 500,
      };
    }
  },
};
