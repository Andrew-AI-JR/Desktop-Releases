const apiClient = require('../api/apiClient');
const FormData = require('form-data');

/**
 * Service for resume-related operations
 */
const resumeService = {
  /**
   * Upload a resume
   * @param {Buffer} fileBuffer - Resume file buffer
   * @param {string} fileName - Original file name
   * @param {string} fileType - File extension
   * @param {number} fileSize - File size in bytes
   * @returns {Promise<Object>} Uploaded resume data
   */
  async uploadResume(fileBuffer, fileName, fileType, fileSize) {
    try {
      // Create form data
      const formData = new FormData();
      formData.append('file', fileBuffer, {
        filename: fileName,
        contentType: this.getContentType(fileType),
        knownLength: fileSize,
      });

      // Set form data headers
      const headers = {
        ...formData.getHeaders(),
        'Content-Length': formData.getLengthSync(),
      };

      const response = await apiClient.post('/api/resumes/upload', formData, {
        headers,
      });
      return response.data;
    } catch (error) {
      console.error(
        'Resume upload error:',
        error.response?.data || error.message
      );
      throw {
        message: error.response?.data?.detail || 'Failed to upload resume',
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * List all resumes
   * @returns {Promise<Array>} List of resumes
   */
  async listResumes() {
    try {
      const response = await apiClient.get('/api/resumes/list');
      return response.data;
    } catch (error) {
      console.error(
        'List resumes error:',
        error.response?.data || error.message
      );
      throw {
        message: error.response?.data?.detail || 'Failed to list resumes',
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Download a resume
   * @param {number} resumeId - Resume ID
   * @returns {Promise<Object>} Download URL data
   */
  async downloadResume(resumeId) {
    try {
      const response = await apiClient.get(`/api/resumes/download/${resumeId}`);
      return response.data;
    } catch (error) {
      console.error(
        'Resume download error:',
        error.response?.data || error.message
      );
      throw {
        message: error.response?.data?.detail || 'Failed to download resume',
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Delete a resume
   * @param {number} resumeId - Resume ID
   * @returns {Promise<void>}
   */
  async deleteResume(resumeId) {
    try {
      await apiClient.delete(`/api/resumes/${resumeId}`);
    } catch (error) {
      console.error(
        'Resume delete error:',
        error.response?.data || error.message
      );
      throw {
        message: error.response?.data?.detail || 'Failed to delete resume',
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Get content type based on file extension
   * @param {string} fileType - File extension
   * @returns {string} Content type
   */
  getContentType(fileType) {
    switch (fileType.toLowerCase()) {
      case '.pdf':
        return 'application/pdf';
      case '.doc':
        return 'application/msword';
      case '.docx':
        return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
      default:
        return 'application/octet-stream';
    }
  },
};

module.exports = resumeService;
