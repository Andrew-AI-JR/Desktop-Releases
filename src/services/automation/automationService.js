const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const { app } = require("electron");

// Track the running process
let pythonProcess = null;
let isRunning = false;

/**
 * Service for LinkedIn automation
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

    return new Promise((resolve, reject) => {
      try {
        isRunning = true;

        // Create a temporary config file to pass to the Python script
        const configPath = this.createConfigFile(config);

        // Find the Python script path
        const scriptPath = this.findScriptPath();

        // Set up the Python process
        const pythonExecutable =
          process.platform === "win32" ? "python" : "python3";
        pythonProcess = spawn(pythonExecutable, [
          scriptPath,
          "--config",
          configPath,
        ]);

        // Handle process output
        let stdoutData = "";
        let stderrData = "";

        pythonProcess.stdout.on("data", (data) => {
          const output = data.toString();
          stdoutData += output;

          // Parse status updates from Python
          this.parseStatusUpdates(output);
        });

        pythonProcess.stderr.on("data", (data) => {
          stderrData += data.toString();
          console.error("Python stderr:", data.toString());
        });

        pythonProcess.on("close", (code) => {
          isRunning = false;
          pythonProcess = null;

          // Clean up temporary config file
          this.cleanupConfigFile(configPath);

          if (code === 0) {
            resolve({
              success: true,
              message: "LinkedIn automation completed successfully",
              output: stdoutData,
            });
          } else {
            reject({
              message: `LinkedIn automation failed with code ${code}`,
              error: stderrData,
              status: 500,
            });
          }
        });

        pythonProcess.on("error", (error) => {
          isRunning = false;
          pythonProcess = null;
          this.cleanupConfigFile(configPath);

          reject({
            message: "Failed to start LinkedIn automation",
            error: error.message,
            status: 500,
          });
        });
      } catch (error) {
        isRunning = false;
        this.cleanupConfigFile(config.configPath);

        reject({
          message: error.message || "Automation failed",
          status: error.status || 500,
        });
      }
    });
  },

  /**
   * Stop the running automation
   * @returns {Promise<Object>} Result of the stop operation
   */
  async stopAutomation() {
    if (!isRunning || !pythonProcess) {
      return {
        success: true,
        message: "No automation running",
      };
    }

    return new Promise((resolve, reject) => {
      try {
        // Kill the Python process
        if (process.platform === "win32") {
          // On Windows
          spawn("taskkill", ["/pid", pythonProcess.pid, "/f", "/t"]);
        } else {
          // On macOS/Linux
          process.kill(pythonProcess.pid);
        }

        pythonProcess = null;
        isRunning = false;

        resolve({
          success: true,
          message: "Automation stopped successfully",
        });
      } catch (error) {
        console.error("Error stopping automation:", error);

        // Reset state even if there was an error
        pythonProcess = null;
        isRunning = false;

        reject({
          message: error.message || "Failed to stop automation",
          status: error.status || 500,
        });
      }
    });
  },

  /**
   * Create a temporary configuration file for the Python script
   * @param {Object} config - Configuration options
   * @returns {string} Path to the created config file
   */
  createConfigFile(config) {
    try {
      const configDir = path.join(app.getPath("userData"), "configs");
      fs.mkdirSync(configDir, { recursive: true });

      const configPath = path.join(
        configDir,
        `linkedin_config_${Date.now()}.json`
      );

      // Transform the config object to match the Python script's expectations
      const pythonConfig = {
        credentials: {
          linkedin_email: config.credentials?.email || "",
          linkedin_password: config.credentials?.password || "",
        },
        limits: {
          max_daily_comments: config.limits?.dailyComments || 15,
          max_session_comments: config.limits?.sessionComments || 5,
          max_comments: config.limits?.commentsPerCycle || 3,
        },
        user_info: {
          calendly_link: config.userInfo?.calendlyLink || "",
          job_search_keywords: config.userInfo?.jobKeywords || [],
          user_bio: config.userInfo?.bio || "",
        },
        timing: {
          scroll_pause_time: config.timing?.scrollPauseTime || 5,
          short_sleep_seconds: config.timing?.shortSleepSeconds || 180,
        },
        search_urls: config.searchUrls || [],
        debug_mode: config.debugMode !== undefined ? config.debugMode : true,
      };

      fs.writeFileSync(configPath, JSON.stringify(pythonConfig, null, 2));
      return configPath;
    } catch (error) {
      console.error("Error creating config file:", error);
      throw new Error("Failed to create configuration file");
    }
  },

  /**
   * Clean up temporary config file
   * @param {string} configPath - Path to the config file
   */
  cleanupConfigFile(configPath) {
    try {
      if (configPath && fs.existsSync(configPath)) {
        fs.unlinkSync(configPath);
      }
    } catch (error) {
      console.error("Error cleaning up config file:", error);
    }
  },

  /**
   * Find the path to the LinkedIn commenter script
   * @returns {string} Path to the script
   */
  findScriptPath() {
    // Look in common locations
    const possiblePaths = [
      path.join(
        app.getAppPath(),
        "resources",
        "scripts",
        "linkedin_commenter.py"
      ),
      path.join(app.getAppPath(), "scripts", "linkedin_commenter.py"),
      path.join(app.getPath("userData"), "scripts", "linkedin_commenter.py"),
    ];

    for (const scriptPath of possiblePaths) {
      if (fs.existsSync(scriptPath)) {
        return scriptPath;
      }
    }

    throw new Error(
      "LinkedIn automation script not found. Please ensure it's installed correctly."
    );
  },

  /**
   * Parse status updates from the Python script output
   * @param {string} output - Output from the Python script
   */
  parseStatusUpdates(output) {
    try {
      // Look for JSON formatted status updates
      const lines = output.split("\n");

      for (const line of lines) {
        if (line.trim().startsWith("[") && line.includes("]")) {
          // This looks like a log line from the Python script
          // Format: [timestamp] [LEVEL] message

          // Extract timestamp and message
          const match = line.match(/\[(.*?)\]\s+\[(.*?)\]\s+(.*)/);
          if (match) {
            const timestamp = match[1];
            const level = match[2];
            const message = match[3];

            // Emit an event with the status update
            const event = {
              type: "log",
              timestamp,
              level,
              message,
            };

            // Use Electron's IPC to send the event to the renderer process
            if (global.mainWindow) {
              global.mainWindow.webContents.send("automation:status", event);
            }
          }
        }
      }
    } catch (error) {
      console.error("Error parsing status updates:", error);
    }
  },
};

module.exports = automationService;
