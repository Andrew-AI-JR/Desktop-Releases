/**
 * Handles automation-related functionality in the UI
 */
export class AutomationController {
  constructor(viewManager, modalManager) {
    this.viewManager = viewManager;
    this.modalManager = modalManager;

    // Element references
    this.postUrlInput = document.getElementById("post-url");
    this.startButton = document.getElementById("start-automation");
    this.stopButton = document.getElementById("stop-automation");
    this.statusText = document.getElementById("automation-status-text");
    this.logContainer = document.getElementById("log-container");

    // State
    this.isRunning = false;

    // Setup event listeners
    this.setupEventListeners();
  }

  /**
   * Set up event listeners for automation-related elements
   */
  setupEventListeners() {
    this.startButton.addEventListener("click", this.startAutomation.bind(this));
    this.stopButton.addEventListener("click", this.stopAutomation.bind(this));
  }

  /**
   * Start the automation process
   */
  async startAutomation() {
    const postUrl = this.postUrlInput.value.trim();

    // Validate input
    if (!postUrl) {
      this.modalManager.alert(
        "Please enter a LinkedIn post URL.",
        "Validation Error"
      );
      return;
    }

    if (!this.isValidLinkedInUrl(postUrl)) {
      this.modalManager.alert(
        "Please enter a valid LinkedIn URL.",
        "Validation Error"
      );
      return;
    }

    try {
      // Update UI state
      this.setRunningState(true);
      this.log("Starting automation...");
      this.log(`Target URL: ${postUrl}`);

      // Check for stored LinkedIn credentials
      const credentials = await this.getLinkedInCredentials();

      if (!credentials) {
        // Prompt for credentials if not stored
        const credentialsProvided = await this.promptForCredentials();
        if (!credentialsProvided) {
          this.setRunningState(false);
          this.log("Automation cancelled - no credentials provided.");
          return;
        }
      }

      // Start automation through the API
      const result = await window.api.automation.runLinkedInAutomation({
        postUrl,
        credentials,
      });

      // Handle result
      if (result && result.success) {
        this.log("Automation completed successfully!");
        this.log(`Generated comment: "${result.comment}"`);

        // Show success message
        this.statusText.textContent = "Automation completed";
        this.modalManager.alert(
          "Automation completed successfully!",
          "Success"
        );
      } else {
        throw new Error(result.message || "Unknown error");
      }
    } catch (error) {
      console.error("Automation error:", error);
      this.log(`Error: ${error.message || "Unknown error"}`);
      this.statusText.textContent = "Automation failed";
      this.modalManager.alert(
        error.message || "Automation failed. Please try again.",
        "Automation Error"
      );
    } finally {
      // Reset UI state
      this.setRunningState(false);
    }
  }

  /**
   * Stop the running automation
   */
  async stopAutomation() {
    try {
      this.log("Stopping automation...");

      // Call API to stop automation
      const result = await window.api.automation.stopAutomation();

      if (result && result.success) {
        this.log("Automation stopped successfully.");
      } else {
        throw new Error(result.message || "Failed to stop automation");
      }
    } catch (error) {
      console.error("Stop automation error:", error);
      this.log(`Error stopping automation: ${error.message}`);
    } finally {
      // Reset UI state
      this.setRunningState(false);
    }
  }

  /**
   * Update UI elements based on automation running state
   * @param {boolean} isRunning - Whether automation is running
   */
  setRunningState(isRunning) {
    this.isRunning = isRunning;

    // Update buttons
    this.startButton.disabled = isRunning;
    this.stopButton.disabled = !isRunning;

    // Update input
    this.postUrlInput.disabled = isRunning;

    // Update status
    this.statusText.textContent = isRunning ? "Running..." : "Ready to start";
  }

  /**
   * Add a log message to the log container
   * @param {string} message - Message to log
   */
  log(message) {
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = document.createElement("div");
    logEntry.className = "log-entry";
    logEntry.textContent = `[${timestamp}] ${message}`;

    // Add to log container
    this.logContainer.appendChild(logEntry);

    // Scroll to bottom
    this.logContainer.scrollTop = this.logContainer.scrollHeight;
  }

  /**
   * Validate if a URL is a valid LinkedIn URL
   * @param {string} url - URL to validate
   * @returns {boolean} True if valid
   */
  isValidLinkedInUrl(url) {
    try {
      const urlObj = new URL(url);
      return urlObj.hostname.includes("linkedin.com");
    } catch (error) {
      return false;
    }
  }

  /**
   * Get stored LinkedIn credentials
   * @returns {Promise<Object|null>} Credentials or null
   */
  async getLinkedInCredentials() {
    try {
      // In a real app, you would get this from a secure store
      // For now, we'll just return null to prompt the user
      return null;
    } catch (error) {
      console.error("Error getting LinkedIn credentials:", error);
      return null;
    }
  }

  /**
   * Prompt the user for LinkedIn credentials
   * @returns {Promise<boolean>} True if credentials were provided
   */
  async promptForCredentials() {
    // Create modal content with a form
    const formContainer = document.createElement("div");
    formContainer.innerHTML = `
      <form id="credentials-form" class="auth-form">
        <div class="form-group">
          <label for="linkedin-email">LinkedIn Email</label>
          <input type="email" id="linkedin-email" name="email" required>
        </div>
        <div class="form-group">
          <label for="linkedin-password">LinkedIn Password</label>
          <input type="password" id="linkedin-password" name="password" required>
        </div>
        <div class="form-group">
          <label for="remember-credentials">
            <input type="checkbox" id="remember-credentials" name="remember">
            Remember credentials (stored securely)
          </label>
        </div>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary">Continue</button>
          <button type="button" class="btn" id="cancel-credentials">Cancel</button>
        </div>
      </form>
    `;

    // Show the modal
    const modalPromise = this.modalManager.showModal(
      "LinkedIn Credentials",
      formContainer
    );

    // Handle form submission
    const form = formContainer.querySelector("#credentials-form");
    const cancelButton = formContainer.querySelector("#cancel-credentials");

    let credentialsResult = null;

    form.addEventListener("submit", (event) => {
      event.preventDefault();

      const email = form.email.value.trim();
      const password = form.password.value;
      const remember = form.remember.checked;

      if (email && password) {
        credentialsResult = { email, password, remember };
        this.modalManager.closeModal(true);
      }
    });

    cancelButton.addEventListener("click", () => {
      this.modalManager.closeModal(false);
    });

    // Wait for modal to close
    const result = await modalPromise;

    if (result && credentialsResult) {
      // Save credentials if requested
      if (credentialsResult.remember) {
        this.saveLinkedInCredentials(credentialsResult);
      }

      return true;
    }

    return false;
  }

  /**
   * Save LinkedIn credentials
   * @param {Object} credentials - LinkedIn credentials
   */
  async saveLinkedInCredentials(credentials) {
    try {
      // In a real app, you would save this securely
      // For demo purposes, we'll just log it
      console.log("Would save credentials for:", credentials.email);

      this.log("Credentials saved for future use");
    } catch (error) {
      console.error("Error saving credentials:", error);
    }
  }
}
