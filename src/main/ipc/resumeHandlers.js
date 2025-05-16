const resumeService = require("../../services/resumes/resumeService");
const path = require("path");
const fs = require("fs");

/**
 * Handlers for resume-related IPC calls
 */
module.exports = {
  /**
   * Upload a resume
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {string} filePath - Path to the resume file
   * @returns {Promise<Object>} Uploaded resume data
   */
  upload: async (event, filePath) => {
    try {
      if (!filePath || !fs.existsSync(filePath)) {
        throw new Error("Invalid file path");
      }

      const fileName = path.basename(filePath);
      const fileExtension = path.extname(filePath).toLowerCase();
      const fileSize = fs.statSync(filePath).size;

      // Validate file type
      const allowedExtensions = [".pdf", ".doc", ".docx"];
      if (!allowedExtensions.includes(fileExtension)) {
        throw new Error(
          "Invalid file type. Only PDF and Word documents are allowed."
        );
      }

      // Read file content
      const fileBuffer = fs.readFileSync(filePath);

      return await resumeService.uploadResume(
        fileBuffer,
        fileName,
        fileExtension,
        fileSize
      );
    } catch (error) {
      console.error("Resume upload error:", error);
      throw {
        message: error.message || "Failed to upload resume",
        status: error.status || 500,
      };
    }
  },

  /**
   * List all resumes
   * @param {Electron.IpcMainInvokeEvent} event
   * @returns {Promise<Array>} List of resumes
   */
  list: async (event) => {
    try {
      return await resumeService.listResumes();
    } catch (error) {
      console.error("List resumes error:", error);
      throw {
        message: error.message || "Failed to list resumes",
        status: error.status || 500,
      };
    }
  },

  /**
   * Download a resume
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {number} resumeId - Resume ID
   * @returns {Promise<Object>} Download URL data
   */
  download: async (event, resumeId) => {
    try {
      return await resumeService.downloadResume(resumeId);
    } catch (error) {
      console.error("Resume download error:", error);
      throw {
        message: error.message || "Failed to download resume",
        status: error.status || 500,
      };
    }
  },

  /**
   * Delete a resume
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {number} resumeId - Resume ID
   * @returns {Promise<Object>} Success status
   */
  delete: async (event, resumeId) => {
    try {
      await resumeService.deleteResume(resumeId);
      return { success: true };
    } catch (error) {
      console.error("Resume delete error:", error);
      throw {
        message: error.message || "Failed to delete resume",
        status: error.status || 500,
      };
    }
  },
};
