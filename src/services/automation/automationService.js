const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const { app, BrowserWindow } = require('electron');
const pythonDependencyService = require('./pythonDependencyService');
const pythonBundleService = require('./pythonBundleService');

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
   * Run LinkedIn automation to post comments
   * @param {Object} config - Automation configuration
   * @returns {Promise<Object>} Result of the automation
   */
  async runLinkedInAutomation(config) {
    if (isRunning) {
      throw new Error('Automation is already running');
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
            reject({
              message:
                'Google Chrome is not installed or not accessible. Please install Chrome to use the LinkedIn automation feature.',
              error: 'Chrome not found',
              status: 400,
            });
            return;
          }

          // Create a temporary config file to pass to the Python script
          configPath = this.createConfigFile(config);

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
      sendLogMessage('Production mode: Using bundled Python executable...');

      // In production, bundled Python MUST be available
      if (!pythonBundleService.isBundledPythonAvailable()) {
        throw new Error(
          'Bundled Python executable not found in production build. The app may be corrupted.'
        );
      }

      // Find bundled script (MUST exist in production)
      const scriptPath = this._findProductionScript();
      sendLogMessage(`Using bundled script: ${path.basename(scriptPath)}`);

      // Get writable paths for logs and Chrome profile
      const logFilePath = this.getLogFilePath();
      const chromeProfilePath = this.getChromeProfilePath();

      sendLogMessage(`Log file: ${logFilePath}`);
      sendLogMessage(`Chrome profile: ${chromeProfilePath}`);

      // Create environment with writable paths
      const env = {
        ...process.env,
        LINKEDIN_LOG_FILE: logFilePath,
        LINKEDIN_CHROME_PROFILE_PATH: chromeProfilePath,
      };

      // Run bundled Python executable
      const pythonProcess = pythonBundleService.runBundledPython(
        [scriptPath, '--config', configPath],
        { env }
      );

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
      sendLogMessage('Development mode: Using system Python...');

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

      sendLogMessage(`Log file: ${logFilePath}`);
      sendLogMessage(`Chrome profile: ${chromeProfilePath}`);

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
    let hasStarted = false;
    let hasErrors = false;

    // Store the process reference globally
    global.pythonProcess = pythonProcess;

    pythonProcess.stdout.on('data', data => {
      const output = data.toString();
      stdoutData += output;
      console.log('Python stdout:', output);

      // Check if automation has actually started
      if (
        !hasStarted &&
        (output.includes('Starting LinkedIn Commenter') ||
          output.includes('[START]'))
      ) {
        hasStarted = true;
        sendLogMessage('Python script started successfully');
      }

      this.parseStatusUpdates(output);

      if (global.mainWindow) {
        global.mainWindow.webContents.send('automation-log', {
          type: 'stdout',
          message: output,
        });
      }
    });

    pythonProcess.stderr.on('data', data => {
      const output = data.toString();
      stderrData += output;
      console.error('Python stderr:', output);

      // Check for error indicators in stderr
      if (this._containsErrorIndicators(output)) {
        hasErrors = true;
        sendLogMessage(
          `Error detected in Python script: ${output.slice(0, 200)}...`
        );
      }

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
      if (code === 0 && !hasErrors && hasStarted) {
        resolve({
          success: true,
          message: 'LinkedIn automation completed successfully',
          output: stdoutData,
        });
      } else {
        // Determine appropriate error message
        let errorMessage;
        if (!hasStarted) {
          errorMessage = 'Python script failed to start properly';
        } else if (hasErrors) {
          errorMessage = 'Python script encountered errors during execution';
        } else {
          errorMessage = `LinkedIn automation failed with exit code ${code}`;
        }

        const errorDetails = {
          message: errorMessage,
          exitCode: code,
          stdout: stdoutData,
          stderr: stderrData,
          usedBundled: useBundled,
          scriptPath,
          hasStarted,
          hasErrors,
          status: 500,
        };

        console.error('Python process exit error:', errorDetails);
        sendLogMessage(`${errorMessage}. Check logs for details.`);
        reject(errorDetails);
      }
    });

    pythonProcess.on('error', error => {
      isRunning = false;
      global.pythonProcess = null;
      this.cleanupConfigFile(configPath);

      const errorDetails = {
        message: 'Failed to start LinkedIn automation process',
        originalError: error.message,
        errorType: error.code || error.name || 'Unknown',
        usedBundled: useBundled,
        scriptPath,
        platform: process.platform,
        arch: process.arch,
        status: 500,
      };

      console.error('Python process error:', errorDetails);
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
        console.error('Error stopping automation:', error);

        // Reset state even if there was an error
        pythonProcess = null;
        isRunning = false;

        reject({
          message: error.message || 'Failed to stop automation',
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
      const juniorDir = path.join(app.getPath('userData'), 'JuniorAI');

      // Create configs subdirectory
      const configDir = path.join(juniorDir, 'configs');
      fs.mkdirSync(configDir, { recursive: true });

      const configPath = path.join(
        configDir,
        `linkedin_config_${Date.now()}.json`
      );

      // Transform the config object to match the Python script's expectations
      // Process keywords from string to the format the Python script expects
      const keywords = config.userInfo?.jobKeywords || '';

      // Get a platform-appropriate Chrome profile path
      const chromeProfilePath = this.getChromeProfilePath();

      const pythonConfig = {
        linkedin_credentials: {
          email: config.credentials?.email || '',
          password: config.credentials?.password || '',
        },
        backend_url: process.env.BACKEND_URL || '',
        browser_config: {
          chrome_profile_path: chromeProfilePath,
          headless: false,
        },
        chrome_profile_path: chromeProfilePath, // Additional field for the Python script
        debug_mode: config.debugMode !== undefined ? config.debugMode : true,
        max_daily_comments: config.limits?.dailyComments || 50,
        max_session_comments: config.limits?.sessionComments || 10,
        calendly_url: config.userInfo?.calendlyLink || '',
        keywords: keywords, // Pass keywords as a string - the script will split it
        user_bio: config.userInfo?.bio || '',
        scroll_pause_time: config.timing?.scrollPauseTime || 5,
        short_sleep_seconds: config.timing?.shortSleepSeconds || 180,
        max_comments: config.limits?.commentsPerCycle || 3,
      };

      fs.writeFileSync(configPath, JSON.stringify(pythonConfig, null, 2));
      return configPath;
    } catch (error) {
      console.error('Error creating config file:', error);
      throw new Error('Failed to create configuration file');
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
   * Parse status updates from the Python script output
   * @param {string} output - Output from the Python script
   */
  parseStatusUpdates(output) {
    try {
      // Look for JSON formatted status updates
      const lines = output.split('\n');

      for (const line of lines) {
        if (line.trim().startsWith('[') && line.includes(']')) {
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
              type: 'log',
              timestamp,
              level,
              message,
            };

            // Use Electron's IPC to send the event to the renderer process
            if (global.mainWindow) {
              global.mainWindow.webContents.send('automation:status', event);
            }
          }
        }
      }
    } catch (error) {
      console.error('Error parsing status updates:', error);
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
              email: config.credentials?.email || '',
              password: config.credentials?.password || '',
            }
          : {
              email: config.credentials?.email || '',
              password: '', // Don't save password if not requested
            },
        rememberCredentials: !!config.rememberCredentials,
        userInfo: {
          calendlyLink: config.userInfo?.calendlyLink || '',
          bio: config.userInfo?.bio || '',
          jobKeywords: config.userInfo?.jobKeywords || '',
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
      console.error('Error saving persistent configuration:', error);
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

  /**
   * Check if stderr output contains error indicators
   * @private
   * @param {string} output - stderr output to check
   * @returns {boolean} True if error indicators are found
   */
  _containsErrorIndicators(output) {
    const errorPatterns = [
      /Traceback \(most recent call last\):/i,
      /Error:/i,
      /Exception:/i,
      /Failed to/i,
      /Cannot create/i,
      /Permission denied/i,
      /No such file or directory/i,
      /PermissionError:/i,
      /FileNotFoundError:/i,
      /ChromeDriverException:/i,
      /selenium\.common\.exceptions/i,
      /TimeoutException:/i,
      /WebDriverException:/i,
    ];

    return errorPatterns.some(pattern => pattern.test(output));
  },
};

module.exports = automationService;
