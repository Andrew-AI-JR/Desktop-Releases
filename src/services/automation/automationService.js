const puppeteer = require("puppeteer-core");
const path = require("path");
const { app } = require("electron");
const apiClient = require("../api/apiClient");

// Track the running browser instance
let browser = null;
let isRunning = false;

/**
 * Service for browser automation
 */
const automationService = {
  /**
   * Run LinkedIn automation to post comments
   * @param {Object} config - Automation configuration
   * @returns {Promise<Object>} Result of the automation
   */
  async runLinkedInAutomation(config) {
    if (isRunning) {
      throw new Error("Automation is already running");
    }

    isRunning = true;
    let page = null;

    try {
      // Launch browser - looking for Chrome in standard locations
      browser = await puppeteer.launch({
        headless: false, // Set to true in production
        executablePath: await this.findChromePath(),
        userDataDir: path.join(app.getPath("userData"), "ChromeProfile"),
        args: ["--no-sandbox", "--disable-setuid-sandbox"],
      });

      page = await browser.newPage();

      // Set viewport size
      await page.setViewport({ width: 1280, height: 800 });

      // Navigate to LinkedIn
      await page.goto("https://www.linkedin.com/login", {
        waitUntil: "networkidle2",
      });

      // Check if already logged in
      const isLoggedIn = await page.evaluate(() => {
        return window.location.href.includes("feed");
      });

      if (!isLoggedIn) {
        // Login process
        await this.linkedInLogin(page, config.credentials);
      }

      // Navigate to the post URL if provided
      if (config.postUrl) {
        await page.goto(config.postUrl, { waitUntil: "networkidle2" });
      }

      // Get the post text
      const postText = await this.extractPostText(page);

      // Generate comment using the API
      const commentData = await apiClient.post("/api/comments/generate", {
        post_text: postText,
        source_linkedin_url: config.postUrl,
      });

      // Add the comment to the post
      await this.addComment(page, commentData.data.comment);

      // Close browser
      await browser.close();
      browser = null;
      isRunning = false;

      return {
        success: true,
        message: "Automation completed successfully",
        comment: commentData.data.comment,
      };
    } catch (error) {
      console.error("Automation error:", error);

      // Clean up on error
      if (browser) {
        await browser.close();
        browser = null;
      }

      isRunning = false;

      throw {
        message: error.message || "Automation failed",
        status: error.status || 500,
      };
    }
  },

  /**
   * Stop the running automation
   * @returns {Promise<Object>} Result of the stop operation
   */
  async stopAutomation() {
    if (!isRunning || !browser) {
      return {
        success: true,
        message: "No automation running",
      };
    }

    try {
      await browser.close();
      browser = null;
      isRunning = false;

      return {
        success: true,
        message: "Automation stopped successfully",
      };
    } catch (error) {
      console.error("Error stopping automation:", error);

      // Reset state even if there was an error
      browser = null;
      isRunning = false;

      throw {
        message: error.message || "Failed to stop automation",
        status: error.status || 500,
      };
    }
  },

  /**
   * Login to LinkedIn
   * @param {puppeteer.Page} page - Puppeteer page
   * @param {Object} credentials - LinkedIn credentials
   * @returns {Promise<void>}
   */
  async linkedInLogin(page, credentials) {
    try {
      // Fill in email and password
      await page.type("#username", credentials.email);
      await page.type("#password", credentials.password);

      // Click login button
      await Promise.all([
        page.waitForNavigation({ waitUntil: "networkidle2" }),
        page.click(".login__form_action_container button"),
      ]);

      // Check for login errors
      const errorElement = await page.$(".alert-content");
      if (errorElement) {
        const errorText = await page.evaluate(
          (el) => el.textContent,
          errorElement
        );
        throw new Error(`LinkedIn login failed: ${errorText.trim()}`);
      }
    } catch (error) {
      console.error("LinkedIn login error:", error);
      throw error;
    }
  },

  /**
   * Extract text from a LinkedIn post
   * @param {puppeteer.Page} page - Puppeteer page
   * @returns {Promise<string>} Post text
   */
  async extractPostText(page) {
    try {
      // Wait for post content to load
      await page.waitForSelector(".feed-shared-update-v2__description-wrapper");

      // Extract post text
      const postText = await page.evaluate(() => {
        const postElement = document.querySelector(
          ".feed-shared-update-v2__description-wrapper"
        );
        return postElement ? postElement.textContent.trim() : "";
      });

      return postText;
    } catch (error) {
      console.error("Error extracting post text:", error);
      throw new Error("Failed to extract post text");
    }
  },

  /**
   * Add a comment to a LinkedIn post
   * @param {puppeteer.Page} page - Puppeteer page
   * @param {string} comment - Comment text
   * @returns {Promise<void>}
   */
  async addComment(page, comment) {
    try {
      // Click on comment button if not already in comment mode
      const commentButton = await page.$(
        '.feed-shared-social-action-bar__action-button[aria-label*="comment"]'
      );
      if (commentButton) {
        await commentButton.click();
      }

      // Wait for comment input to appear
      await page.waitForSelector(
        ".comments-comment-box__form-container .ql-editor"
      );

      // Type comment
      await page.type(
        ".comments-comment-box__form-container .ql-editor",
        comment
      );

      // Submit comment
      await Promise.all([
        page.waitForSelector(".comments-comment-item__main-content"), // Wait for comment to appear
        page.click(".comments-comment-box__submit-button"),
      ]);
    } catch (error) {
      console.error("Error adding comment:", error);
      throw new Error("Failed to add comment");
    }
  },

  /**
   * Find Chrome/Chromium executable path based on platform
   * @returns {Promise<string>} Chrome executable path
   */
  async findChromePath() {
    const platform = process.platform;

    // Default paths for different platforms
    const chromePaths = {
      win32: [
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
      ],
      darwin: [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
      ],
      linux: [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
      ],
    };

    // Use platform-specific paths
    const paths = chromePaths[platform] || [];

    // Check if any of the paths exist
    for (const path of paths) {
      try {
        // In a real implementation, we would check if the file exists
        // For simplicity, we'll just return the first path for the platform
        return path;
      } catch (error) {
        continue;
      }
    }

    throw new Error(
      "Could not find Chrome/Chromium installation. Please install Chrome or Chromium."
    );
  },
};

module.exports = automationService;
