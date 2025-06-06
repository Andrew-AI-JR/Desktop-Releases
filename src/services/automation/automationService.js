const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const { app, BrowserWindow } = require('electron');
const pythonDependencyService = require('./pythonDependencyService');
const pythonBundleService = require('./pythonBundleService');
const errorCodes = require('./errorCodes');
const apiClient = require('../api/apiClient');
const tokenManager = require('../auth/tokenManager');
// Track the running process
let pythonProcess = null;
let isRunning = false;

// Persistent configuration path
const getPersistentConfigPath = () => {
  const juniorDir = path.join(app.getPath('userData'), 'JuniorAI');
  fs.mkdirSync(juniorDir, { recursive: true });
  return path.join(juniorDir, 'persistent_config.json');
};

/**
 * Service for LinkedIn automation
 */
const automationService = {
  /**
   * Get writable log file path
   * @returns {string} Path to writable log file
   */
  getLogFilePath() {
    const juniorDir = path.join(app.getPath('userData'), 'JuniorAI');
    fs.mkdirSync(juniorDir, { recursive: true });
    return path.join(juniorDir, 'linkedin_commenter.log');
  },

  /**
   * Get writable Chrome profile path
   * @returns {string} Path to writable Chrome profile directory
   */
  /**
   * Check if we're running in development mode
   * @returns {boolean} True if in development mode
   */
  isDevelopmentMode() {
    return !app.isPackaged;
  },

  /**
   * Check subscription status and limits before running automation.
   * @private
   */
  async _checkSubscriptionLimits() {
    try {
      // First check if we have a valid token
      const accessToken = await tokenManager.getAccessToken();
      if (!accessToken) {
        throw {
          message: 'Please log in to use the automation feature',
          status: errorCodes.UNAUTHORIZED,
        };
      }

      const response = await apiClient.get('/api/users/me');
      const userData = response.data;

      // Check for an active subscription using is_active field
      if (!userData || !userData.is_active) {
        throw {
          message: 'No active subscription found',
          status: errorCodes.NO_SUBSCRIPTION,
        };
      }

      return true; // All checks passed.
    } catch (error) {
      // Handle specific error cases
      if (error.response?.status === 401) {
        throw {
          message: 'Please log in to use the automation feature',
          status: errorCodes.UNAUTHORIZED,
        };
      }

      // If the error already has a message, re-throw it
      if (error.message) {
        throw error;
      }

      console.error(
        '[_checkSubscriptionLimits] Error checking subscription status:',
        error
      );
      throw {
        message: 'Could not verify subscription status. Please try again later.',
        status: 500,
      };
    }
  },

  /**
   * Run LinkedIn automation to post comments
   * @param {Object} config - Automation configuration
   * @returns {Promise<Object>} Result of the automation
   */
  async runLinkedInAutomation(config) {
    await this._cleanupStaleProcess();

    if (isRunning) {
      throw new Error('Automation is already running');
    }

    // First, verify subscription and limits.
    try {
      await this._checkSubscriptionLimits();
    } catch (error) {
      console.error('[runLinkedInAutomation] Subscription check failed:', error);
      // Reject the promise to send the error back to the controller.
      return Promise.reject({
        message:
          error.message ||
          'An error occurred while verifying your subscription.',
        status: error.status || 500,
      });
    }

    // Save configuration for future use if remember credentials is checked
    if (config.rememberCredentials) {
      this.savePersistentConfig(config);
    }

    return new Promise((resolve, reject) => {
      const runAsync = async () => {
        let configPath;
        try {
          isRunning = true;

          // Check if Chrome is available before starting
          const chromeAvailable = await this.checkChromeAvailability();
          if (!chromeAvailable) {
            isRunning = false;
            console.error('[runLinkedInAutomation] Chrome not found');
            reject({
              message:
                'Google Chrome is not installed or not accessible. Please install Chrome to use the LinkedIn automation feature.',
              error: 'Chrome not found',
              status: 400,
            });
            return;
          }

          // Create a temporary config file to pass to the Python script
          configPath = await this.createConfigFile(config);

          // Send log messages to renderer
          const sendLogMessage = message => {
            if (global.mainWindow) {
              global.mainWindow.webContents.send('automation-log', {
                type: 'stdout',
                message,
              });
            } else {
              // Fallback to any open window
              const windows = BrowserWindow.getAllWindows();
              if (windows.length > 0) {
                windows[0].webContents.send('automation-log', {
                  type: 'stdout',
                  message,
                });
              }
            }
          };

          // Clear separation: Development vs Production mode
          if (app.isPackaged) {
            // PRODUCTION MODE: Only use bundled Python and bundled script
            await this._runProductionMode(
              config,
              configPath,
              sendLogMessage,
              resolve,
              reject
            );
          } else {
            // DEVELOPMENT MODE: Use system Python and development script
            await this._runDevelopmentMode(
              config,
              configPath,
              sendLogMessage,
              resolve,
              reject
            );
          }
        } catch (error) {
          isRunning = false;

          // Safely cleanup config file if it was created
          if (configPath) {
            this.cleanupConfigFile(configPath);
          }
          console.error(
            '[runLinkedInAutomation] Error during automation run:',
            error
          );
          reject({
            message: error.message || 'Automation failed',
            status: error.status || 500,
          });
        }
      };

      runAsync();
    });
  },

  /**
   * Clean up stale processes before starting new automation
   * @private
   */
  async _cleanupStaleProcess() {
    try {
      // If we think something is running but the process is dead, clean it up
      if (isRunning && global.pythonProcess) {
        // Check if process is actually still running
        try {
          process.kill(global.pythonProcess.pid, 0); // Signal 0 just checks if process exists
        } catch (error) {
          // Process doesn't exist, clean up the state
          console.log('[_cleanupStaleProcess] Cleaning up stale process state');
          isRunning = false;
          global.pythonProcess = null;
          return;
        }
      }

      // If we have a running process, try to stop it gracefully
      if (isRunning) {
        console.log(
          '[_cleanupStaleProcess] Stopping existing automation before starting new one'
        );
        await this.stopAutomation();
      }
    } catch (error) {
      // If cleanup fails, force reset the state
      console.warn(
        '[_cleanupStaleProcess] Error during cleanup, forcing reset:',
        error.message
      );
      isRunning = false;
      global.pythonProcess = null;
    }
  },

  /**
   * Run automation in production mode (packaged app)
   * @private
   */
  async _runProductionMode(
    config,
    configPath,
    sendLogMessage,
    resolve,
    reject
  ) {
    try {
      // In production, bundled Python MUST be available
      if (!pythonBundleService.isBundledPythonAvailable()) {
        throw new Error(
          'Bundled Python executable not found in production build. The app may be corrupted.'
        );
      }

      // Get writable paths for logs and Chrome profile
      const logFilePath = this.getLogFilePath();
      const chromeProfilePath = this.getChromeProfilePath();

      // Create environment with writable paths
      const env = {
        ...process.env,
        LINKEDIN_LOG_FILE: logFilePath,
        LINKEDIN_CHROME_PROFILE_PATH: chromeProfilePath,
      };

      // Run bundled Python with config
      const pythonProcess = pythonBundleService.runBundledPython(
        ['--config', configPath],
        { env }
      );

      // Get script path for handlers
      const scriptPath = pythonBundleService.getScriptPath();

      this._setupProcessHandlers(
        pythonProcess,
        configPath,
        true,
        scriptPath,
        sendLogMessage,
        resolve,
        reject
      );
    } catch (error) {
      isRunning = false;
      this.cleanupConfigFile(configPath);
      console.error('[_runProductionMode] Error:', error);
      reject({
        message: `Production mode failed: ${error.message}`,
        status: 500,
      });
    }
  },

  /**
   * Run automation in development mode
   * @private
   */
  async _runDevelopmentMode(
    config,
    configPath,
    sendLogMessage,
    resolve,
    reject
  ) {
    try {
      // Check system Python availability
      const systemPythonAvailable =
        await pythonBundleService.isSystemPythonAvailable();
      if (!systemPythonAvailable) {
        throw new Error(
          'System Python not found. Please install Python 3.x for development.'
        );
      }

      // Install/verify dependencies
      const dependenciesInstalled =
        await pythonDependencyService.ensureDependencies(message => {
          sendLogMessage(message);
        });

      if (!dependenciesInstalled) {
        throw new Error('Failed to install required Python dependencies.');
      }

      sendLogMessage('Dependencies verified. Starting automation...');

      // Find development script
      const scriptPath = this._findDevelopmentScript();
      sendLogMessage(`Using development script: ${path.basename(scriptPath)}`);

      // Get writable paths for logs and Chrome profile
      const logFilePath = this.getLogFilePath();
      const chromeProfilePath = this.getChromeProfilePath();

      // Create environment with writable paths
      const env = {
        ...process.env,
        LINKEDIN_LOG_FILE: logFilePath,
        LINKEDIN_CHROME_PROFILE_PATH: chromeProfilePath,
      };

      // Run system Python
      const pythonExecutable = pythonBundleService.getFallbackPython();
      const pythonProcess = spawn(
        pythonExecutable,
        [scriptPath, '--config', configPath],
        { env }
      );

      this._setupProcessHandlers(
        pythonProcess,
        configPath,
        false,
        scriptPath,
        sendLogMessage,
        resolve,
        reject
      );
    } catch (error) {
      isRunning = false;
      this.cleanupConfigFile(configPath);
      console.error('[_runDevelopmentMode] Error:', error);
      reject({
        message: `Development mode failed: ${error.message}`,
        status: 500,
      });
    }
  },

  /**
   * Setup process event handlers
   * @private
   */
  _setupProcessHandlers(
    pythonProcess,
    configPath,
    useBundled,
    scriptPath,
    sendLogMessage,
    resolve,
    reject
  ) {
    let stdoutData = '';
    let stderrData = '';

    // Store the process reference globally
    global.pythonProcess = pythonProcess;

    pythonProcess.stdout.on('data', data => {
      const output = data.toString();
      stdoutData += output;
      console.log('[Python] stdout:', output);
      const trimmedOutput = data.toString().trim();
      if (trimmedOutput.startsWith('[APP_OUT]')) {
        const appMessage = trimmedOutput.substring('[APP_OUT]'.length).trim();
        if (appMessage) {
          sendLogMessage(appMessage);
        }
      }
    });

    pythonProcess.stderr.on('data', data => {
      const output = data.toString();
      stderrData += output;
      console.error('[Python] stderr:', output);

      if (global.mainWindow) {
        global.mainWindow.webContents.send('automation-log', {
          type: 'stderr',
          message: output,
        });
      }
    });

    pythonProcess.on('close', code => {
      isRunning = false;
      global.pythonProcess = null;
      this.cleanupConfigFile(configPath);
      // Check for errors even if exit code is 0
      if (code === 0) {
        resolve({
          success: true,
          message: errorCodes[code],
          output: stdoutData,
        });
      } else {
        const errorDetails = {
          message: errorCodes[code] || 'Unknown error occurred',
          exitCode: code,
          stdout: stdoutData,
          stderr: stderrData,
          usedBundled: useBundled,
          scriptPath,
        };

        console.error(
          '[_setupProcessHandlers] Python process exit error:',
          errorDetails
        );
        reject(errorDetails);
      }
    });

    pythonProcess.on('error', error => {
      isRunning = false;
      global.pythonProcess = null;
      this.cleanupConfigFile(configPath);

      const errorDetails = {
        message: 'Faile to start LinkedIn automation process',
        originalError: error.message,
        exitCode: error.code,
        errorType: error.name,
        usedBundled: useBundled,
        scriptPath,
        platform: process.platform,
        arch: process.arch,
        status: 500,
      };

      console.error(
        '[_setupProcessHandlers] Python process error:',
        errorDetails
      );
      sendLogMessage(`Process error: ${error.message}`);
      reject(errorDetails);
    });
  },

  /**
   * Find script in production mode (packaged app)
   * @private
   * @returns {string} Path to the bundled script
   */
  _findProductionScript() {
    if (!process.resourcesPath) {
      throw new Error('Resources path not available in production build');
    }

    const bundledScriptPath = path.join(
      process.resourcesPath,
      'linkedin_commenter.py'
    );

    console.log(`[Production Script] Checking: ${bundledScriptPath}`);

    if (!fs.existsSync(bundledScriptPath)) {
      // Debug what's actually in resources
      try {
        const resourcesContents = fs.readdirSync(process.resourcesPath);
        console.error(
          '[Production Script] Resources contents:',
          resourcesContents
        );
      } catch (error) {
        console.error(
          '[Production Script] Cannot read resources directory:',
          error.message
        );
      }

      throw new Error(
        `Bundled script not found: ${bundledScriptPath}. The app build may be incomplete.`
      );
    }

    console.log(`[Production Script] ✅ Found: ${bundledScriptPath}`);
    return bundledScriptPath;
  },

  /**
   * Find script in development mode
   * @private
   * @returns {string} Path to the development script
   */
  _findDevelopmentScript() {
    const possiblePaths = [
      path.join(
        app.getAppPath(),
        'src',
        'resources',
        'scripts',
        'linkedin_commenter.py'
      ),
      path.join(
        app.getAppPath(),
        'resources',
        'scripts',
        'linkedin_commenter.py'
      ),
      path.join(app.getAppPath(), 'scripts', 'linkedin_commenter.py'),
    ];

    console.log('[Development Script] Looking for linkedin_commenter.py...');
    console.log(`[Development Script] App path: ${app.getAppPath()}`);

    for (const scriptPath of possiblePaths) {
      console.log(`[Development Script] Checking: ${scriptPath}`);
      if (fs.existsSync(scriptPath)) {
        console.log(`[Development Script] ✅ Found: ${scriptPath}`);
        return scriptPath;
      }
    }

    // Debug app directory contents
    try {
      const appContents = fs.readdirSync(app.getAppPath());
      console.error(
        '[Development Script] App directory contents:',
        appContents
      );
    } catch (error) {
      console.error(
        '[Development Script] Cannot read app directory:',
        error.message
      );
    }

    throw new Error(
      `Development script not found. Searched:\n${possiblePaths
        .map(p => `- ${p}`)
        .join('\n')}`
    );
  },

  /**
   * Stop the running automation
   * @returns {Promise<Object>} Result of the stop operation
   */
  async stopAutomation() {
    if (!isRunning || !pythonProcess) {
      return {
        success: true,
        message: 'No automation running',
      };
    }

    return new Promise((resolve, reject) => {
      try {
        // Kill the Python process
        if (process.platform === 'win32') {
          // On Windows
          spawn('taskkill', ['/pid', pythonProcess.pid, '/f', '/t']);
        } else {
          // On macOS/Linux
          process.kill(pythonProcess.pid);
        }

        pythonProcess = null;
        isRunning = false;

        resolve({
          success: true,
          message: 'Automation stopped successfully',
        });
      } catch (error) {
        // Reset state even if there was an error
        pythonProcess = null;
        isRunning = false;
        console.error('[stopAutomation] Error stopping automation:', error);
        reject({
          message: error.message || 'Failed to stop automation',
          status: error.status || 500,
        });
      }
    });
  },

  /**
   * Create a temporary configuration file for the Python script
   * @param {Object} config - Automation configuration
   * @returns {Promise<string>} Path to the created config file
   */
  async createConfigFile(config) {
    // Add paths that the Python script will need
    config.log_file_path = this.getLogFilePath();
    config.chrome_profile_path = this.getChromeProfilePath();

    const tempDir = path.join(app.getPath('userData'), 'temp');
    fs.mkdirSync(tempDir, { recursive: true });
    const configPath = path.join(tempDir, `config-${Date.now()}.json`);

    try {
      fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
      return configPath;
    } catch (error) {
      console.error('[createConfigFile] Error creating temp config file:', error);
      throw new Error('Failed to create automation configuration.');
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
      console.error('Error cleaning up config file:', error);
    }
  },

  /**
   * Save configuration for future use
   * @param {Object} config - Configuration to save
   * @returns {boolean} Success status
   */
  savePersistentConfig(config) {
    const configPath = getPersistentConfigPath();
    try {
      // Only store credentials and user info, not the whole config
      const persistentData = {
        linkedin_email: config.linkedin_email,
        linkedin_password: config.linkedin_password,
        calendly_link: config.calendly_link,
        user_bio: config.user_bio,
        job_keywords: config.job_keywords,
      };

      // Only save if remember credentials is true
      if (config.remember_credentials) {
        fs.writeFileSync(configPath, JSON.stringify(persistentData, null, 2));
      } else {
        // If not checked, remove any existing saved config
        if (fs.existsSync(configPath)) {
          fs.unlinkSync(configPath);
        }
      }
    } catch (error) {
      console.error('[savePersistentConfig] Error saving config:', error);
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
        console.log('No persistent configuration found');
        return null;
      }

      console.log('Loading persistent configuration from:', configPath);
      const configData = fs.readFileSync(configPath, 'utf8');
      const config = JSON.parse(configData);
      console.log('Loaded persistent configuration');
      return config;
    } catch (error) {
      console.error('Error loading persistent configuration:', error);
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
      const juniorDir = path.join(app.getPath('userData'), 'JuniorAI');

      // Create a dedicated directory for Chrome profiles
      const chromeProfileDir = path.join(juniorDir, 'chrome_profiles');

      // Create a unique profile for each session (optional - you can also reuse the same profile)
      const sessionProfileDir = path.join(chromeProfileDir, 'selenium_profile');

      // Ensure the directory exists
      fs.mkdirSync(sessionProfileDir, { recursive: true });

      console.log(`Chrome profile directory: ${sessionProfileDir}`);
      return sessionProfileDir;
    } catch (error) {
      console.error('Error creating Chrome profile directory:', error);
      // Return a default path in case of error
      return path.join(app.getPath('temp'), 'JuniorAI', 'chrome_profile');
    }
  },

  /**
   * Check if Chrome is available on the system
   * @returns {Promise<boolean>} True if Chrome is found
   */
  async checkChromeAvailability() {
    const fs = require('fs');

    return new Promise(resolve => {
      let chromePaths = [];

      if (process.platform === 'win32') {
        chromePaths = [
          'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
          'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        ];
      } else if (process.platform === 'darwin') {
        chromePaths = [
          '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
          '/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
        ];
      } else {
        // For Linux, try which command
        const { spawn } = require('child_process');
        const whichProcess = spawn('which', ['google-chrome'], {
          stdio: 'pipe',
        });

        whichProcess.on('close', code => {
          resolve(code === 0);
        });

        whichProcess.on('error', () => {
          resolve(false);
        });

        setTimeout(() => {
          whichProcess.kill();
          resolve(false);
        }, 2000);
        return;
      }

      // For Windows and macOS, just check if the file exists
      for (const chromePath of chromePaths) {
        try {
          if (fs.existsSync(chromePath)) {
            console.log(`Chrome found at: ${chromePath}`);
            resolve(true);
            return;
          }
        } catch (error) {
          console.error(`Error checking Chrome path ${chromePath}:`, error);
        }
      }

      console.log('Chrome not found in any expected locations');
      resolve(false);
    });
  },
};

module.exports = automationService;
