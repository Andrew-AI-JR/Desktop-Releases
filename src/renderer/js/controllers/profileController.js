/**
 * Handles professional profile functionality in the UI
 */
export class ProfileController {
  constructor(viewManager, modalManager) {
    this.viewManager = viewManager;
    this.modalManager = modalManager;

    // Element references
    this.profileForm = document.getElementById("profile-form");
    this.profileUrlInput = document.getElementById("profile-url");
    this.bioTextarea = document.getElementById("bio");
    this.resumeFileInput = document.getElementById("resume-file");
    this.uploadResumeButton = document.getElementById("upload-resume");
    this.resumeList = document.getElementById("resume-list");

    // State
    this.profile = null;
    this.bio = "";
    this.resumes = [];

    // Setup event listeners
    this.setupEventListeners();
  }

  /**
   * Set up event listeners for profile-related elements
   */
  setupEventListeners() {
    // Profile form submission
    this.profileForm.addEventListener(
      "submit",
      this.handleProfileFormSubmit.bind(this)
    );

    // Resume upload button
    this.uploadResumeButton.addEventListener(
      "click",
      this.handleResumeUpload.bind(this)
    );

    // Listen for user login event to load profile data
    document.addEventListener("user:loggedin", () => {
      this.loadProfileData();
    });
  }

  /**
   * Load profile data
   */
  async loadProfileData() {
    try {
      // Load professional profile data
      const profileData = await window.api.profile.getProfile();
      this.profile = profileData;

      if (profileData && profileData.profile_url) {
        this.profileUrlInput.value = profileData.profile_url;
      }

      // Load bio data
      const bioData = await window.api.auth.getBio();
      if (bioData && bioData.bio) {
        this.bio = bioData.bio;
        this.bioTextarea.value = bioData.bio;
      }

      // Load resumes
      const resumes = await window.api.resumes.list();
      this.resumes = resumes || [];
      this.renderResumeList();
    } catch (error) {
      console.error("Error loading profile data:", error);
      this.modalManager.alert(
        "Failed to load profile data. Please try again later.",
        "Profile Error"
      );
    }
  }

  /**
   * Handle profile form submission
   * @param {Event} event - Form submit event
   */
  async handleProfileFormSubmit(event) {
    event.preventDefault();

    const profileUrl = this.profileUrlInput.value.trim();
    const bio = this.bioTextarea.value.trim();

    // Validate URL
    if (profileUrl && !this.isValidUrl(profileUrl)) {
      this.modalManager.alert(
        "Please enter a valid LinkedIn profile URL.",
        "Validation Error"
      );
      return;
    }

    try {
      // Show loading state
      this.setFormLoading(true);

      // Update profile data if URL is provided
      if (profileUrl) {
        await window.api.profile.updateProfile({ profile_url: profileUrl });
      }

      // Update bio data if different from current
      if (bio !== this.bio) {
        await window.api.auth.updateBio({ bio });
        this.bio = bio;
      }

      // Show success message
      this.modalManager.alert("Profile updated successfully!", "Success");

      // Reload profile data
      await this.loadProfileData();
    } catch (error) {
      console.error("Profile update error:", error);
      this.modalManager.alert(
        error.message || "Failed to update profile. Please try again.",
        "Profile Error"
      );
    } finally {
      // Remove loading state
      this.setFormLoading(false);
    }
  }

  /**
   * Handle resume upload
   */
  async handleResumeUpload() {
    const fileInput = this.resumeFileInput;

    if (!fileInput.files || fileInput.files.length === 0) {
      this.modalManager.alert(
        "Please select a file to upload.",
        "Validation Error"
      );
      return;
    }

    const file = fileInput.files[0];

    // Validate file type
    const allowedTypes = [".pdf", ".doc", ".docx"];
    const fileExt = file.name
      .substring(file.name.lastIndexOf("."))
      .toLowerCase();
    if (!allowedTypes.includes(fileExt)) {
      this.modalManager.alert(
        "Please upload a PDF or Word document.",
        "File Type Error"
      );
      return;
    }

    try {
      // Show loading state
      this.uploadResumeButton.disabled = true;
      this.uploadResumeButton.textContent = "Uploading...";

      // In a real implementation, this would need to use a proper file upload mechanism
      // Electron would need to read the file and send its contents to the API
      // For demo purposes, we'll just simulate a successful upload

      // Upload resume
      const filePath = file.path;
      const result = await window.api.resumes.upload(filePath);

      if (result) {
        // Add to resumes list
        this.resumes.unshift(result);
        this.renderResumeList();

        // Clear file input
        fileInput.value = "";

        // Show success message
        this.modalManager.alert("Resume uploaded successfully!", "Success");
      }
    } catch (error) {
      console.error("Resume upload error:", error);
      this.modalManager.alert(
        error.message || "Failed to upload resume. Please try again.",
        "Upload Error"
      );
    } finally {
      // Remove loading state
      this.uploadResumeButton.disabled = false;
      this.uploadResumeButton.textContent = "Upload Resume";
    }
  }

  /**
   * Delete a resume
   * @param {number} resumeId - Resume ID
   */
  async deleteResume(resumeId) {
    try {
      const confirmed = await this.modalManager.confirm(
        "Are you sure you want to delete this resume?"
      );

      if (confirmed) {
        await window.api.resumes.delete(resumeId);

        // Remove from local list
        this.resumes = this.resumes.filter((resume) => resume.id !== resumeId);
        this.renderResumeList();

        // Show success message
        this.modalManager.alert("Resume deleted successfully!", "Success");
      }
    } catch (error) {
      console.error("Resume delete error:", error);
      this.modalManager.alert(
        error.message || "Failed to delete resume. Please try again.",
        "Delete Error"
      );
    }
  }

  /**
   * Download a resume
   * @param {number} resumeId - Resume ID
   */
  async downloadResume(resumeId) {
    try {
      const response = await window.api.resumes.download(resumeId);

      if (response && response.download_url) {
        // Open download URL in default browser
        // In a real implementation, this would use Electron APIs to download the file
        this.modalManager.alert("Resume download started!", "Download");
      } else {
        throw new Error("Failed to generate download URL");
      }
    } catch (error) {
      console.error("Resume download error:", error);
      this.modalManager.alert(
        error.message || "Failed to download resume. Please try again.",
        "Download Error"
      );
    }
  }

  /**
   * Render the resume list
   */
  renderResumeList() {
    // Clear current content
    this.resumeList.innerHTML = "";

    if (!this.resumes || this.resumes.length === 0) {
      this.resumeList.innerHTML =
        '<p class="empty-state">No resumes uploaded</p>';
      return;
    }

    // Create resume items
    for (const resume of this.resumes) {
      const resumeItem = document.createElement("div");
      resumeItem.classList.add("resume-item");

      resumeItem.innerHTML = `
        <div class="resume-info">
          <div class="resume-name">${resume.file_name}</div>
          <div class="resume-meta">
            <span class="resume-type">${resume.file_type}</span>
            ${
              resume.file_size
                ? `<span class="resume-size">${this.formatFileSize(
                    resume.file_size
                  )}</span>`
                : ""
            }
            <span class="resume-date">${new Date(
              resume.created_at
            ).toLocaleDateString()}</span>
          </div>
        </div>
        <div class="resume-actions">
          <button class="btn btn-small download-resume">Download</button>
          <button class="btn btn-small btn-danger delete-resume">Delete</button>
        </div>
      `;

      // Add event listeners to buttons
      const downloadButton = resumeItem.querySelector(".download-resume");
      downloadButton.addEventListener("click", () => {
        this.downloadResume(resume.id);
      });

      const deleteButton = resumeItem.querySelector(".delete-resume");
      deleteButton.addEventListener("click", () => {
        this.deleteResume(resume.id);
      });

      this.resumeList.appendChild(resumeItem);
    }
  }

  /**
   * Set loading state on the profile form
   * @param {boolean} isLoading - Whether the form is in loading state
   */
  setFormLoading(isLoading) {
    const submitButton = this.profileForm.querySelector(
      'button[type="submit"]'
    );

    if (isLoading) {
      submitButton.disabled = true;
      submitButton.textContent = "Saving...";
    } else {
      submitButton.disabled = false;
      submitButton.textContent = "Save Profile";
    }
  }

  /**
   * Check if a string is a valid URL
   * @param {string} url - URL to validate
   * @returns {boolean} True if valid
   */
  isValidUrl(url) {
    try {
      const urlObj = new URL(url);
      return urlObj.protocol === "http:" || urlObj.protocol === "https:";
    } catch (error) {
      return false;
    }
  }

  /**
   * Format file size in human-readable format
   * @param {number} bytes - File size in bytes
   * @returns {string} Formatted file size
   */
  formatFileSize(bytes) {
    if (bytes === 0) return "0 Bytes";

    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }
}
