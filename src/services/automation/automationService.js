const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const { app, BrowserWindow } = require('electron');

// Persistent file logger for debugging Python process events
const logToFile = (msg) => {
  try {
    const logPath = path.join(app.getPath('userData'), 'main.log');
    fs.appendFileSync(logPath, `[${new Date().toISOString()}] ${msg}\n`);
  } catch (e) {
    // Ignore logging errors
  }
};
const pythonDependencyService = require('./pythonDependencyService');
const pythonBundleService = require('./pythonBundleService');
const errorCodes = require('./errorCodes');
const apiClient = require('../api/apiClient');
const tokenManager = require('../auth/tokenManager');
// Track the running process - use global variables to ensure consistency across app lifecycle
global.pythonProcess = global.pythonProcess || null;
global.isAutomationRunning = global.isAutomationRunning || false;

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
    // Try to use the user's Documents folder first
    const userDocumentsPath = app.getPath('documents');
    const defaultLogPath = path.join(userDocumentsPath, 'JuniorAI', 'logs', 'linkedin_commenter.log');
    
    try {
      // Create the logs directory
      const logDir = path.dirname(defaultLogPath);
      fs.mkdirSync(logDir, { recursive: true });
      return defaultLogPath;
    } catch (e) {
      console.error(`[getLogFilePath] Error creating directory ${logDir}:`, e);
      // Fallback to userData if creating desired path fails
      const fallbackDir = path.join(app.getPath('userData'), 'JuniorAI', 'logs');
      fs.mkdirSync(fallbackDir, { recursive: true });
      return path.join(fallbackDir, 'linkedin_commenter.log');
    }
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
  logToFile(`[AutomationService] runLinkedInAutomation called with config: ${JSON.stringify(config)}`);
    await this._cleanupStaleProcess();

    if (global.isAutomationRunning) {
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
          global.isAutomationRunning = true;

          // Check if Chrome is available before starting
          const chromeAvailable = await this.checkChromeAvailability();
          if (!chromeAvailable) {
            global.isAutomationRunning = false;
            console.error('[runLinkedInAutomation] Chrome not found');
            reject({
              message:
                'Google Chrome is not installed or not accessible. Please install Chrome to use the LinkedIn automation feature.',
              error: 'Chrome not found',
              status: 400,
            });
            return;
          }

          // Fetch access token for backend authentication
          const accessToken = await tokenManager.getAccessToken();
          if (!accessToken) {
            logToFile('[AutomationService] Backend access token not found. Automation may fail.');
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

          // Append access token to config for Python script execution
          const executionConfig = {
            ...config,
            accessToken, // Add token for backend auth
          };

          // Clear separation: Development vs Production mode
          if (app.isPackaged) {
            // PRODUCTION MODE: Only use bundled Python and bundled script
            await this._runProductionMode(
              executionConfig,
              configPath,
              sendLogMessage,
              resolve,
              reject
            );
          } else {
            // DEVELOPMENT MODE: Use system Python and development script
            await this._runDevelopmentMode(
              executionConfig,
              configPath,
              sendLogMessage,
              resolve,
              reject
            );
          }
        } catch (error) {
          global.isAutomationRunning = false;

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
      if (global.isAutomationRunning && global.pythonProcess) {
        // Check if process is actually still running
        try {
          process.kill(global.pythonProcess.pid, 0); // Signal 0 just checks if process exists
        } catch (error) {
          // Process doesn't exist, clean up the state
          console.log('[_cleanupStaleProcess] Cleaning up stale process state');
          global.isAutomationRunning = false;
          global.pythonProcess = null;
          return;
        }
      }

      // If we have a running process, try to stop it gracefully
      if (global.isAutomationRunning) {
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
      global.isAutomationRunning = false;
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
      const chromePath = this.getBundledChromePath();

      // Create environment with writable paths
      const env = {
        ...process.env,
        LINKEDIN_LOG_FILE: logFilePath,
        LINKEDIN_CHROME_PROFILE_PATH: chromeProfilePath,
        CHROME_PATH: chromePath || '', // Pass Chrome path to Python script
      };

      // Construct arguments for Python script
      const scriptArgs = this._buildScriptArguments(config, configPath, true);
      logToFile(`[Production] Executing with args: ${JSON.stringify(scriptArgs)}`);

      // Run bundled Python with config
      const pythonProcess = pythonBundleService.runBundledPython(
        scriptArgs.slice(1), // Remove the script path itself, as runBundledPython prepends it
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
      global.isAutomationRunning = false;
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

      // Construct arguments for Python script
      const scriptArgs = this._buildScriptArguments(config, configPath, false);
      logToFile(`[Development] Executing: ${pythonExecutable} with args: ${JSON.stringify(scriptArgs)}`);

      // Run system Python with unbuffered output for immediate GUI updates
      const pythonExecutable = pythonBundleService.getFallbackPython();
      const pythonProcess = spawn(
        pythonExecutable,
        ['-u', ...scriptArgs], // -u flag for unbuffered output
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
      global.isAutomationRunning = false;
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
      logToFile('[Python] stdout: ' + output);
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
      logToFile('[Python] stderr: ' + output);

      if (global.mainWindow) {
        global.mainWindow.webContents.send('automation-log', {
          type: 'stderr',
          message: output,
        });
      }
    });

    pythonProcess.on('close', code => {
      try {
        global.isAutomationRunning = false;
        global.pythonProcess = null;
        this.cleanupConfigFile(configPath);
        
        // Check for errors even if exit code is 0
        logToFile(`[Python] process exited with code: ${code}`);
        console.log(`[_setupProcessHandlers] Python process closed with code: ${code}`);
        
        if (code === 0) {
          resolve({
            success: true,
            message: errorCodes[code] || 'Process completed successfully',
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
          
          try {
            logToFile('[Python] process exit error: ' + JSON.stringify(errorDetails));
            logToFile('[Python] process exit error: ' + JSON.stringify(errorDetails), 'main.log');
          } catch (logError) {
            console.warn('[_setupProcessHandlers] Logging error during close event:', logError.message);
          }
          
          reject(errorDetails);
        }
      } catch (closeError) {
        console.error('[_setupProcessHandlers] Error in close handler:', closeError);
        // Force reset state to prevent stuck conditions
        global.isAutomationRunning = false;
        global.pythonProcess = null;
        
        // Always try to cleanup config file
        try {
          this.cleanupConfigFile(configPath);
        } catch (cleanupError) {
          console.warn('[_setupProcessHandlers] Config cleanup error:', cleanupError.message);
        }
        
        // Reject with safe error details
        reject({
          message: 'Process handler error during cleanup',
          originalError: closeError.message,
          exitCode: code || -1,
          status: 500,
        });
      }
    });

    pythonProcess.on('error', error => {
      try {
        global.isAutomationRunning = false;
        global.pythonProcess = null;
        this.cleanupConfigFile(configPath);

        const errorDetails = {
          message: 'Failed to start LinkedIn automation process',
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
        
        try {
          logToFile('[Python] process error: ' + JSON.stringify(errorDetails));
          sendLogMessage(`Process error: ${error.message}`);
        } catch (logError) {
          console.warn('[_setupProcessHandlers] Logging error during error event:', logError.message);
        }
        
        reject(errorDetails);
      } catch (errorHandlerError) {
        console.error('[_setupProcessHandlers] Error in error handler:', errorHandlerError);
        // Force reset state to prevent stuck conditions
        global.isAutomationRunning = false;
        global.pythonProcess = null;
        
        // Always try to cleanup config file
        try {
          this.cleanupConfigFile(configPath);
        } catch (cleanupError) {
          console.warn('[_setupProcessHandlers] Config cleanup error in error handler:', cleanupError.message);
        }
        
        // Reject with safe error details
        reject({
          message: 'Critical error in process error handler',
          originalError: errorHandlerError.message,
          processError: error.message,
          status: 500,
        });
      }
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
    if (!global.isAutomationRunning || !global.pythonProcess) {
      return {
        success: true,
        message: 'No automation running',
      };
    }

    return new Promise((resolve) => {
      try {
        console.log('[stopAutomation] Attempting to stop automation process...');
        
        const processToKill = global.pythonProcess;
        const pidToKill = processToKill?.pid;
        
        if (!pidToKill) {
          console.log('[stopAutomation] No valid PID found, resetting state');
          global.pythonProcess = null;
          global.isAutomationRunning = false;
          resolve({
            success: true,
            message: 'No valid process found, state reset',
          });
          return;
        }

        // Set a timeout to force cleanup if process doesn't terminate
        const forceCleanupTimeout = setTimeout(() => {
          console.log('[stopAutomation] Force cleanup timeout reached');
          global.pythonProcess = null;
          global.isAutomationRunning = false;
          resolve({
            success: true,
            message: 'Automation stopped (forced cleanup after timeout)',
          });
        }, 5000); // 5 second timeout

        // Handle process termination event
        const onProcessExit = () => {
          try {
            clearTimeout(forceCleanupTimeout);
            global.pythonProcess = null;
            global.isAutomationRunning = false;
            console.log('[stopAutomation] Process terminated successfully');
            resolve({
              success: true,
              message: 'Automation stopped successfully',
            });
          } catch (exitError) {
            console.error('[stopAutomation] Error in onProcessExit:', exitError);
            // Still resolve successfully to prevent unhandled rejection
            global.pythonProcess = null;
            global.isAutomationRunning = false;
            resolve({
              success: true,
              message: 'Automation stopped (with cleanup warning)',
              warning: exitError.message,
            });
          }
        };

        // Listen for process exit (only if process still exists)
        if (processToKill && !processToKill.killed) {
          processToKill.once('exit', onProcessExit);
          processToKill.once('close', onProcessExit);
        }

        // Kill the Python process using the correct method per platform
        if (process.platform === 'win32') {
          // On Windows - use taskkill to terminate process tree
          console.log(`[stopAutomation] Killing Windows process tree for PID: ${pidToKill}`);
          
          const killProcess = spawn('taskkill', ['/pid', pidToKill.toString(), '/f', '/t'], {
            detached: true,
            stdio: 'ignore'
          });

          killProcess.on('error', (error) => {
            console.warn('[stopAutomation] Taskkill error (non-critical):', error.message);
            // Don't fail, continue with cleanup
          });

          killProcess.on('exit', (code) => {
            console.log(`[stopAutomation] Taskkill exited with code: ${code}`);
            // Code 0 = success, 128 = process not found (already dead)
            if (code === 0 || code === 128) {
              // Success or process already dead
              if (!global.pythonProcess) {
                // Already cleaned up by onProcessExit
                return;
              }
              // Trigger cleanup manually if process didn't emit exit event
              setTimeout(onProcessExit, 1000);
            }
          });

        } else {
          // On macOS/Linux - use process.kill
          console.log(`[stopAutomation] Killing process for PID: ${pidToKill}`);
          
          try {
            process.kill(pidToKill, 'SIGTERM');
            
            // If SIGTERM doesn't work after 3 seconds, use SIGKILL
            setTimeout(() => {
              if (global.pythonProcess && global.pythonProcess.pid === pidToKill) {
                console.log('[stopAutomation] SIGTERM timeout, using SIGKILL');
                try {
                  process.kill(pidToKill, 'SIGKILL');
                } catch (killError) {
                  console.warn('[stopAutomation] SIGKILL error:', killError.message);
                }
              }
            }, 3000);
            
          } catch (killError) {
            console.warn('[stopAutomation] Process kill error:', killError.message);
            // Process might already be dead, trigger cleanup
            onProcessExit();
          }
        }

      } catch (error) {
        console.error('[stopAutomation] Critical error during stop:', error);
        
        // Force reset state to prevent stuck states
        global.pythonProcess = null;
        global.isAutomationRunning = false;
        
        // Always resolve successfully to prevent unhandled rejections
        resolve({
          success: true,
          message: 'Automation process terminated (with error recovery)',
          warning: error.message,
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
  logToFile(`[AutomationService] createConfigFile received config: ${JSON.stringify(config)}`);

  // --- PATCH: Ensure config is in correct format for Python script ---
  // Set backend_url
  config.backend_url = 'https://junior-api-915940312680.us-west1.run.app';

  // Move credentials under linkedin_credentials
  if (config.linkedin_email || config.linkedin_password) {
    config.linkedin_credentials = config.linkedin_credentials || {};
    // Force log level to debug for GUI rendering
    config.log_level = 'debug';

    // Set Chrome path based on environment
    if (app.isPackaged) {
      // In production, use bundled Chromium from resources
      config.chrome_path = path.join(process.resourcesPath, 'chrome-win', 'chrome.exe');
    } else {
      // In development, use system Chrome
      config.chrome_path = null; // Let the Python script find system Chrome
    }
    console.log('[DEBUG] Chrome path for Python automation:', config.chrome_path);
    if (config.linkedin_email) {
      config.linkedin_credentials.email = config.linkedin_email;
      delete config.linkedin_email;
    }
    if (config.linkedin_password) {
      config.linkedin_credentials.password = config.linkedin_password;
      delete config.linkedin_password;
    }
  }
  // --- END PATCH ---

  // Add paths that the Python script will need
  config.log_file_path = this.getLogFilePath();
  config.chrome_profile_path = this.getChromeProfilePath();

  // CRITICAL: Add the base directory path so Python script can resolve paths correctly
  config.base_dir = path.resolve(__dirname, '../../..');  // Go up from src/services/automation to junior-desktop root
  
  // Add access token to config if available
  if (config.accessToken) {
    config.access_token = config.accessToken;  // Convert to snake_case for Python
    delete config.accessToken;  // Remove camelCase version
  }

  logToFile(`[AutomationService] Config before writing to file: ${JSON.stringify(config, null, 2)}`);

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
      if (!configPath) {
        console.log('[cleanupConfigFile] No config path provided, skipping cleanup');
        return;
      }

      if (typeof configPath !== 'string') {
        console.warn('[cleanupConfigFile] Invalid config path type:', typeof configPath);
        return;
      }

      if (fs.existsSync(configPath)) {
        try {
          fs.unlinkSync(configPath);
          console.log(`[cleanupConfigFile] Config file cleaned up: ${configPath}`);
        } catch (unlinkError) {
          console.warn(
            `[cleanupConfigFile] Failed to delete config file ${configPath}:`,
            unlinkError.message
          );
        }
      } else {
        console.log(`[cleanupConfigFile] Config file not found (already cleaned?): ${configPath}`);
      }
    } catch (error) {
      console.warn(
        `[cleanupConfigFile] Error during config cleanup for ${configPath}:`,
        error.message
      );
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
   * Get the path to bundled Chromium
   * @returns {string|null} Path to bundled Chromium or null if not found
   */
  getBundledChromePath() {
    if (!app.isPackaged) {
      return null;
    }

    if (process.platform === 'win32') {
      const chromePath = path.join(process.resourcesPath, 'chrome-win', 'chrome.exe');
      if (fs.existsSync(chromePath)) {
        console.log(`Bundled Chrome found at: ${chromePath}`);
        return chromePath;
      }
    }

    const chromePaths = [];
    if (process.platform === 'darwin') {
      chromePaths.push(
        path.join(process.resourcesPath, 'chrome', 'Google Chrome.app', 'Contents', 'MacOS', 'Google Chrome'),
        path.join(process.resourcesPath, 'chrome-mac', 'Google Chrome.app', 'Contents', 'MacOS', 'Google Chrome')
      );
    } else {
      chromePaths.push(
        path.join(process.resourcesPath, 'chrome', 'chrome'),
        path.join(process.resourcesPath, 'chrome-linux', 'chrome')
      );
    }

    for (const chromePath of chromePaths) {
      if (fs.existsSync(chromePath)) {
        console.log(`Bundled Chrome found at: ${chromePath}`);
        return chromePath;
      }
    }

    console.log('Bundled Chrome not found');
    return null;
  },

  /**
   * Check if Chrome is available on the system
   * @returns {Promise<boolean>} True if Chrome is found
   */
  async checkChromeAvailability() {
    return new Promise(resolve => {
      // First check for bundled Chrome in production mode
      if (app.isPackaged) {
        const bundledChromePath = this.getBundledChromePath();
        if (bundledChromePath) {
          resolve(true);
          return;
        }
      }

      // Then check for system Chrome
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

      // For Windows and macOS, check if the file exists
      for (const chromePath of chromePaths) {
        try {
          if (fs.existsSync(chromePath)) {
            console.log(`System Chrome found at: ${chromePath}`);
            resolve(true);
            return;
          }
        } catch (error) {
          console.error(`Error checking Chrome path ${chromePath}:`, error);
        }
      }

      console.log('No Chrome installation found');
      resolve(false);
    });
  },

  /**
   * Builds the command-line arguments for the Python script.
   * @param {Object} config - The automation configuration.
   * @param {string} configPath - The path to the temporary config file.
   * @param {boolean} isProduction - Flag to determine which script path to use.
   * @returns {string[]} An array of command-line arguments.
   * @private
   */
  _buildScriptArguments(config, configPath, isProduction) {
    const scriptPath = isProduction
      ? this._findProductionScript()
      : this._findDevelopmentScript();

    const scriptArgs = [
      scriptPath, // Script path is the first arg
      '--config',
      configPath,
    ];

    // Add LinkedIn credentials if available from the config object
    if (config.linkedinUser) {
      scriptArgs.push('--email', config.linkedinUser);
    }
    if (config.linkedinPass) {
      scriptArgs.push('--password', config.linkedinPass);
    }

    // Add backend authentication credentials from the config object
    if (config.accessToken) {
      scriptArgs.push('--access-token', config.accessToken);
    } else if (config.backendUser && config.backendPass) {
      // Fallback to email/password if no token
      scriptArgs.push('--backend-email', config.backendUser);
      scriptArgs.push('--backend-password', config.backendPass);
    }

    if (config.debugMode) {
      scriptArgs.push('--debug');
    }

    return scriptArgs;
  },
};

/**
 * Force reset the automation state - use this to clear stuck states
 * @returns {Object} Result of the reset operation
 */
automationService.forceResetState = function() {
  const wasRunning = global.isAutomationRunning;
  let killAttempted = false;
  
  // Force kill any process if it exists
  if (global.pythonProcess) {
    try {
      const pidToKill = global.pythonProcess.pid;
      
      if (pidToKill) {
        killAttempted = true;
        console.log(`[forceResetState] Force killing process PID: ${pidToKill}`);
        
        if (process.platform === 'win32') {
          // On Windows - use taskkill with error handling
          const killProcess = spawn('taskkill', ['/pid', pidToKill.toString(), '/f', '/t'], {
            detached: true,
            stdio: 'ignore'
          });
          
          killProcess.on('error', (error) => {
            console.warn('[forceResetState] Taskkill error (ignored):', error.message);
          });
          
        } else {
          // On macOS/Linux - use process.kill with SIGKILL for force kill
          try {
            process.kill(pidToKill, 'SIGKILL');
          } catch (killError) {
            console.warn('[forceResetState] SIGKILL error (ignored):', killError.message);
          }
        }
      }
    } catch (e) {
      // Ignore all errors during forced kill
      console.warn('[forceResetState] Error during force kill (ignored):', e.message);
    }
  }
  
  // Always reset state variables regardless of kill success
  global.pythonProcess = null;
  global.isAutomationRunning = false;
  
  const resultMessage = killAttempted 
    ? 'Automation state forcibly reset with process termination'
    : 'Automation state forcibly reset (no active process found)';
  
  console.log(`[forceResetState] ${resultMessage}. Was running: ${wasRunning}`);
  
  try {
    logToFile(`Forced reset of automation state. Was running: ${wasRunning}, Kill attempted: ${killAttempted}`);
  } catch (logError) {
    // Don't let logging errors affect the reset operation
    console.warn('[forceResetState] Logging error (ignored):', logError.message);
  }
  
  return {
    success: true,
    wasRunning,
    killAttempted,
    message: resultMessage
  };
};

module.exports = automationService;
