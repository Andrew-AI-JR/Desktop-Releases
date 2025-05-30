export class AutomationController {
  constructor(viewManager, modalManager) {
    this.viewManager = viewManager;
    this.modalManager = modalManager;

    // Element references
    this.startButton = document.getElementById("start-automation");
    this.stopButton = document.getElementById("stop-automation");
    this.statusText = document.getElementById("automation-status-text");
    this.logContainer = document.getElementById("log-container");

    // Form inputs
    this.linkedinEmailInput = document.getElementById("linkedin-email");
    this.linkedinPasswordInput = document.getElementById("linkedin-password");
    this.rememberCredentialsInput = document.getElementById(
      "remember-credentials"
    );
    this.calendlyUrlInput = document.getElementById("calendly-url");
    this.userBioInput = document.getElementById("user-bio");
    this.keywordsInput = document.getElementById("keywords");

    // State
    this.isRunning = false;

    // Setup event listeners
    this.setupEventListeners();

    // Listen for automation logs from main process
    window.api.automation.onLog((event, data) => {
      if (data && data.message) {
        this.log(data.message);
      }
    });

    // Load saved configuration if available
    this.loadSavedConfig();
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
    try {
      // Validate LinkedIn credentials
      const email = this.linkedinEmailInput.value.trim();
      const password = this.linkedinPasswordInput.value;

      if (!email || !password) {
        this.modalManager.alert(
          "Please enter your LinkedIn email and password.",
          "Validation Error"
        );
        return;
      }

      // Get other configuration values
      const calendlyLink = this.calendlyUrlInput.value.trim();
      const userBio = this.userBioInput.value.trim();
      const jobKeywords = this.keywordsInput.value.trim();
      const rememberCredentials = this.rememberCredentialsInput.checked;

      // Update UI state
      this.setRunningState(true);
      this.log("Starting LinkedIn automation...");

      // Create configuration object
      const config = {
        credentials: {
          email,
          password,
        },
        rememberCredentials: rememberCredentials,
        userInfo: {
          calendlyLink,
          bio: userBio,
          jobKeywords,
        },
        limits: {
          dailyComments: 50, // Using hardcoded values as requested
          sessionComments: 10,
          commentsPerCycle: 3,
        },
        timing: {
          scrollPauseTime: 5,
          shortSleepSeconds: 180,
        },
        debugMode: true,
        searchUrls: [], // The Python script will generate these based on keywords
      };

      // Start automation through the API
      const result = await window.api.automation.runLinkedInAutomation(config);

      // Handle result
      if (result && result.success) {
        this.log("LinkedIn automation process completed successfully!");

        // Note: We've moved credential saving to the main process
        // using the persistent configuration file
      } else {
        throw new Error(result.message || "Unknown error");
      }
    } catch (error) {
      console.error("Automation error:", error);

      // Better error message extraction
      let errorMessage = this.extractErrorMessage(error);

      // Log detailed error information
      this.log(`Error: ${errorMessage}`);
      if (error.stack) {
        console.error("Error stack:", error.stack);
        this.log(`Stack trace: ${error.stack}`);
      }

      this.statusText.textContent = "Automation failed";
      this.modalManager.alert(errorMessage, "Automation Error");

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

      // Use helper function for better error message extraction
      const errorMessage = this.extractErrorMessage(error);

      this.log(`Error stopping automation: ${errorMessage}`);
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

    // Update inputs
    this.linkedinEmailInput.disabled = isRunning;
    this.linkedinPasswordInput.disabled = isRunning;
    this.calendlyUrlInput.disabled = isRunning;
    this.userBioInput.disabled = isRunning;
    this.keywordsInput.disabled = isRunning;
    this.rememberCredentialsInput.disabled = isRunning;

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
      // In a real app, these should be stored securely
      // For now, just using localStorage for demo purposes
      if (window.localStorage) {
        const storedCredentials = localStorage.getItem("linkedinCredentials");
        if (storedCredentials) {
          return JSON.parse(storedCredentials);
        }
      }
      return null;
    } catch (error) {
      console.error("Error getting LinkedIn credentials:", error);
      return null;
    }
  }

  /**
   * Save LinkedIn credentials
   * @param {Object} credentials - LinkedIn credentials
   */
  async saveLinkedInCredentials(credentials) {
    try {
      // In a real app, these should be stored securely
      // For now, just using localStorage for demo purposes
      if (window.localStorage) {
        localStorage.setItem(
          "linkedinCredentials",
          JSON.stringify({
            email: credentials.email,
            password: credentials.password,
          })
        );
      }

      // Also save other configuration
      if (this.calendlyUrlInput.value) {
        localStorage.setItem("calendlyUrl", this.calendlyUrlInput.value);
      }

      if (this.userBioInput.value) {
        localStorage.setItem("userBio", this.userBioInput.value);
      }

      if (this.keywordsInput.value) {
        localStorage.setItem("jobKeywords", this.keywordsInput.value);
      }

      this.log("Configuration saved for future use");
    } catch (error) {
      console.error("Error saving credentials:", error);
    }
  }

  /**
   * Load saved configuration if available
   */
  async loadSavedConfig() {
    try {
      // First try to load from the persistent storage via the main process
      const result = await window.api.automation.loadPersistentConfig();
      console.log("Loaded persistent config:", result);
      if (result && result.success && result.config) {
        const config = result.config;

        // Set credentials if available
        if (config.credentials) {
          this.linkedinEmailInput.value = config.credentials.email || "";
          this.linkedinPasswordInput.value = config.credentials.password || "";
          this.rememberCredentialsInput.checked = !!config.rememberCredentials;
        }

        // Set user info if available
        if (config.userInfo) {
          this.calendlyUrlInput.value = config.userInfo.calendlyLink || "";
          this.userBioInput.value = config.userInfo.bio || "";
          this.keywordsInput.value = config.userInfo.jobKeywords || "";
        }

        return;
      }

      // Fallback to old localStorage method if persistent config not found
      const credentials = await this.getLinkedInCredentials();

      if (credentials) {
        this.linkedinEmailInput.value = credentials.email || "";
        this.linkedinPasswordInput.value = credentials.password || "";
        this.rememberCredentialsInput.checked = true;
      }

      // Load other saved configurations from localStorage
      if (window.localStorage) {
        const calendlyUrl = localStorage.getItem("calendlyUrl");
        if (calendlyUrl) {
          this.calendlyUrlInput.value = calendlyUrl;
        }

        const userBio = localStorage.getItem("userBio");
        if (userBio) {
          this.userBioInput.value = userBio;
        }

        const keywords = localStorage.getItem("jobKeywords");
        if (keywords) {
          this.keywordsInput.value = keywords;
        }
      }
    } catch (error) {
      console.error("Error loading saved config:", error);

      // Use helper function for better error message extraction
      const errorMessage = this.extractErrorMessage(error);

      this.log(`Warning: Could not load saved configuration: ${errorMessage}`);
    }
  }

  /**
   * Extract a meaningful error message from various error types
   * @param {*} error - Error object, string, or other type
   * @returns {string} Human-readable error message
   */
  extractErrorMessage(error) {
    if (typeof error === "string") {
      return error;
    }

    if (error && error.message) {
      return error.message;
    }

    if (error && typeof error === "object") {
      // Try to get useful information from error object
      if (error.code || error.status) {
        const parts = [];
        if (error.code) parts.push(`Code: ${error.code}`);
        if (error.status) parts.push(`Status: ${error.status}`);
        if (error.type) parts.push(`Type: ${error.type}`);
        return parts.join(", ");
      }

      // Last resort: stringify the object
      try {
        return JSON.stringify(error);
      } catch {
        return String(error);
      }
    }

    return "Unknown error occurred";
  }
}
