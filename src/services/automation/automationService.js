const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const { app, BrowserWindow } = require("electron");
const pythonDependencyService = require("./pythonDependencyService");

// Track the running process
let pythonProcess = null;
let isRunning = false;

// Persistent configuration path
const getPersistentConfigPath = () => {
  const juniorDir = path.join(app.getPath("userData"), "JuniorAI");
  fs.mkdirSync(juniorDir, { recursive: true });
  return path.join(juniorDir, "persistent_config.json");
};

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

    // Save configuration for future use if remember credentials is checked
    if (config.rememberCredentials) {
      this.savePersistentConfig(config);
    }

    return new Promise(async (resolve, reject) => {
      try {
        isRunning = true;

        // Create a temporary config file to pass to the Python script
        const configPath = this.createConfigFile(config);

        // Find the Python script path
        const scriptPath = this.findScriptPath();

        // Send log messages to renderer
        const sendLogMessage = (message) => {
          if (global.mainWindow) {
            global.mainWindow.webContents.send("automation-log", {
              type: "stdout",
              message,
            });
          } else {
            // Fallback to any open window
            const windows = BrowserWindow.getAllWindows();
            if (windows.length > 0) {
              windows[0].webContents.send("automation-log", {
                type: "stdout",
                message,
              });
            }
          }
        };

        // Check and install Python dependencies
        sendLogMessage("Checking Python dependencies...");

        const dependenciesInstalled =
          await pythonDependencyService.ensureDependencies((message) => {
            sendLogMessage(message);
          });

        if (!dependenciesInstalled) {
          isRunning = false;
          reject({
            message: "Failed to install required Python dependencies",
            status: 500,
          });
          return;
        }

        sendLogMessage("Dependencies verified. Starting automation...");

        // Set up the Python process
        const pythonExecutable =
          process.platform === "win32" ? "python" : "python3";

        // Create a custom environment with the Chrome profile path
        const env = { ...process.env };
        const chromeProfilePath = this.getChromeProfilePath();
        env.LINKEDIN_CHROME_PROFILE_PATH = chromeProfilePath;

        pythonProcess = spawn(
          pythonExecutable,
          [scriptPath, "--config", configPath],
          {
            env: env,
          }
        );

        // Handle process output
        let stdoutData = "";
        let stderrData = "";

        // Get any BrowserWindows to send log events
        const { BrowserWindow } = require("electron");

        pythonProcess.stdout.on("data", (data) => {
          const output = data.toString();
          stdoutData += output;
          console.log("Python stdout:", output);

          // Parse status updates from Python
          this.parseStatusUpdates(output);

          // Send log to renderer process
          if (global.mainWindow) {
            global.mainWindow.webContents.send("automation-log", {
              type: "stdout",
              message: output,
            });
          }
        });

        pythonProcess.stderr.on("data", (data) => {
          const output = data.toString();
          stderrData += output;
          console.error("Python stderr:", output);

          // Send error log to renderer process
          if (global.mainWindow) {
            global.mainWindow.webContents.send("automation-log", {
              type: "stderr",
              message: output,
            });
          }
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

        // Safely cleanup config file if it was created
        if (config && config.configPath) {
          this.cleanupConfigFile(config.configPath);
        }

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
      // Create JuniorAI directory in platform-appropriate user data location
      const juniorDir = path.join(app.getPath("userData"), "JuniorAI");

      // Create configs subdirectory
      const configDir = path.join(juniorDir, "configs");
      fs.mkdirSync(configDir, { recursive: true });

      const configPath = path.join(
        configDir,
        `linkedin_config_${Date.now()}.json`
      );

      // Transform the config object to match the Python script's expectations
      // Process keywords from string to the format the Python script expects
      const keywords = config.userInfo?.jobKeywords || "";

      // Get a platform-appropriate Chrome profile path
      const chromeProfilePath = this.getChromeProfilePath();

      const pythonConfig = {
        linkedin_credentials: {
          email: config.credentials?.email || "",
          password: config.credentials?.password || "",
        },
        browser_config: {
          chrome_profile_path: chromeProfilePath,
          headless: false,
        },
        chrome_profile_path: chromeProfilePath, // Additional field for the Python script
        debug_mode: config.debugMode !== undefined ? config.debugMode : true,
        max_daily_comments: config.limits?.dailyComments || 50,
        max_session_comments: config.limits?.sessionComments || 10,
        calendly_url: config.userInfo?.calendlyLink || "",
        keywords: keywords, // Pass keywords as a string - the script will split it
        user_bio: config.userInfo?.bio || "",
        scroll_pause_time: config.timing?.scrollPauseTime || 5,
        short_sleep_seconds: config.timing?.shortSleepSeconds || 180,
        max_comments: config.limits?.commentsPerCycle || 3,
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
      path.join(
        app.getAppPath(),
        "src",
        "resources",
        "scripts",
        "linkedin_commenter.py"
      ),
    ];

    for (const scriptPath of possiblePaths) {
      if (fs.existsSync(scriptPath)) {
        console.log(`Found LinkedIn automation script at: ${scriptPath}`);
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

  /**
   * Save configuration for future use
   * @param {Object} config - Configuration to save
   * @returns {boolean} Success status
   */
  savePersistentConfig(config) {
    try {
      const configPath = getPersistentConfigPath();

      // Prepare configuration for persistent storage
      const persistentConfig = {
        credentials: config.rememberCredentials
          ? {
              email: config.credentials?.email || "",
              password: config.credentials?.password || "",
            }
          : {
              email: config.credentials?.email || "",
              password: "", // Don't save password if not requested
            },
        rememberCredentials: !!config.rememberCredentials,
        userInfo: {
          calendlyLink: config.userInfo?.calendlyLink || "",
          bio: config.userInfo?.bio || "",
          jobKeywords: config.userInfo?.jobKeywords || "",
        },
        limits: {
          dailyComments: config.limits?.dailyComments || 50,
          sessionComments: config.limits?.sessionComments || 10,
          commentsPerCycle: config.limits?.commentsPerCycle || 3,
        },
        timing: {
          scrollPauseTime: config.timing?.scrollPauseTime || 5,
          shortSleepSeconds: config.timing?.shortSleepSeconds || 180,
        },
        debugMode: config.debugMode !== undefined ? config.debugMode : true,
        lastUpdated: new Date().toISOString(),
      };

      fs.writeFileSync(configPath, JSON.stringify(persistentConfig, null, 2));
      console.log(`Configuration saved to ${configPath}`);
      return true;
    } catch (error) {
      console.error("Error saving persistent configuration:", error);
      return false;
    }
  },

  /**
   * Load saved configuration
   * @returns {Object|null} Loaded configuration or null
   */
  loadPersistentConfig() {
    try {
      const configPath = getPersistentConfigPath();
      if (!fs.existsSync(configPath)) {
        console.log("No persistent configuration found");
        return null;
      }
      console.log("Loading persistent configuration from:", configPath);
      const configData = fs.readFileSync(configPath, "utf8");
      const config = JSON.parse(configData);
      console.log("Loaded persistent configuration");
      return config;
    } catch (error) {
      console.error("Error loading persistent configuration:", error);
      return null;
    }
  },

  /**
   * Create and get the path to a Chrome profile directory in the user data location
   * @returns {string} Path to Chrome profile directory
   */
  getChromeProfilePath() {
    try {
      // Create a "JuniorAI" subdirectory in the platform-appropriate user data directory
      const juniorDir = path.join(app.getPath("userData"), "JuniorAI");

      // Create a dedicated directory for Chrome profiles
      const chromeProfileDir = path.join(juniorDir, "chrome_profiles");

      // Create a unique profile for each session (optional - you can also reuse the same profile)
      const sessionProfileDir = path.join(chromeProfileDir, "selenium_profile");

      // Ensure the directory exists
      fs.mkdirSync(sessionProfileDir, { recursive: true });

      console.log(`Chrome profile directory: ${sessionProfileDir}`);
      return sessionProfileDir;
    } catch (error) {
      console.error("Error creating Chrome profile directory:", error);
      // Return a default path in case of error
      return path.join(app.getPath("temp"), "JuniorAI", "chrome_profile");
    }
  },
};

module.exports = automationService;
