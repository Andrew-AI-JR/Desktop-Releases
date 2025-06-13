const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const { app, BrowserWindow } = require('electron');
const pythonDependencyService = require('./pythonDependencyService');
const pythonBundleService = require('./pythonBundleService');
const errorCodes = require('./errorCodes');
const tokenManager = require('../auth/tokenManager');

// Initialize global automation state
global.isAutomationRunning = global.isAutomationRunning || false;
global.pythonProcess = global.pythonProcess || null;

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
    await this._cleanupStaleProcess();

    if (global.isAutomationRunning) {
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

      // Create environment with writable paths
      const env = {
        ...process.env,
        LINKEDIN_LOG_FILE: logFilePath,
        LINKEDIN_CHROME_PROFILE_PATH: chromeProfilePath,
      };

      // Run bundled executable directly (no script path needed - it's compiled in)
      const pythonProcess = pythonBundleService.runBundledPython(
        ['--config', configPath], // Only pass the config, not the script path
        { env }
      );

      // For the handlers, we'll use the executable path as the "script path"
      const executablePath = pythonBundleService.getBundledPythonPath();

      this._setupProcessHandlers(
        pythonProcess,
        configPath,
        true,
        executablePath, // Use executable path instead of script path
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

      // Run system Python with unbuffered output for immediate GUI updates
      const pythonExecutable = pythonBundleService.getFallbackPython();
      const pythonProcess = spawn(
        pythonExecutable,
        ['-u', scriptPath, '--config', configPath], // -u flag for unbuffered output
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
      global.isAutomationRunning = false;
      global.pythonProcess = null;
      this.cleanupConfigFile(configPath);
      
      const resultObj = {
        exitCode: code,
        stdout: stdoutData,
        stderr: stderrData,
        usedBundled: useBundled,
        scriptPath
      };

      if (global.automationStoppedByUser) {
        resolve({ success: true, stopped: true, ...resultObj });
      } else if (code === 0) {
        resolve({ success: true, ...resultObj });
      } else {
        resultObj.error = true;
        resultObj.message = errorCodes[code] || 'Process exited with errors';
        resolve(resultObj);
      }

      // Reset flag after handling
      global.automationStoppedByUser = false;
    });

    pythonProcess.on('error', error => {
      global.isAutomationRunning = false;
      global.pythonProcess = null;
      this.cleanupConfigFile(configPath);

      const errorDetails = {
        ...(global.automationStoppedByUser ? { success: true } : { error: true }),
        stopped: !!global.automationStoppedByUser,
        message: 'Process start/stopped with error',
        originalError: error.message,
        exitCode: error.code,
        errorType: error.name,
        usedBundled: useBundled,
        scriptPath,
        platform: process.platform,
        arch: process.arch,
        status: 500
      };

      console.error('[_setupProcessHandlers] Python process error:', errorDetails);
      sendLogMessage(`Process error: ${error.message}`);
      resolve(errorDetails);
      global.automationStoppedByUser = false;
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
    return new Promise((resolve) => {
      try {
        console.log('[stopAutomation] Current state:', {
          isRunning: global.isAutomationRunning,
          hasPythonProcess: !!global.pythonProcess,
          pythonPid: global.pythonProcess?.pid
        });

        // Case 1: Nothing is running
        if (!global.isAutomationRunning && !global.pythonProcess) {
          console.log('[stopAutomation] No automation running');
          return resolve({
            success: true,
            message: 'No automation running'
          });
        }

        // Case 2: State says running but no process (inconsistent state)
        if (global.isAutomationRunning && !global.pythonProcess) {
          console.log('[stopAutomation] Inconsistent state - running but no process');
          global.isAutomationRunning = false;
          return resolve({
            success: true,
            message: 'State reset - no process was running'
          });
        }

        // Case 3: Process exists but state says not running (another inconsistent state)
        if (!global.isAutomationRunning && global.pythonProcess) {
          console.log('[stopAutomation] Inconsistent state - process exists but marked as not running');
          global.isAutomationRunning = true; // Temporarily set to true so we handle it in the next block
        }

        // Case 4: Actually running with a process
        if (global.isAutomationRunning && global.pythonProcess) {
          console.log(`[stopAutomation] Stopping running process (PID: ${global.pythonProcess.pid})`);
          
          try {
            // First check if process is actually running
            process.kill(global.pythonProcess.pid, 0);
            
            // Process exists, kill it
            if (process.platform === 'win32') {
              spawn('taskkill', ['/pid', global.pythonProcess.pid, '/f', '/t']);
            } else {
              process.kill(global.pythonProcess.pid, 'SIGTERM');
            }
            
            console.log('[stopAutomation] Process terminated successfully');
          } catch (killError) {
            // Process doesn't exist or permission error
            console.log('[stopAutomation] Process already terminated or inaccessible:', killError.message);
          }

          // Mark flag so process handlers know this was user-initiated
          global.automationStoppedByUser = true;
        }

        // Always clean up state
        global.pythonProcess = null;
        global.isAutomationRunning = false;

        return resolve({
          success: true,
          message: 'Automation stopped successfully'
        });
      } catch (error) {
        // Unexpected error - still clean up state
        console.error('[stopAutomation] Unexpected error:', error);
        global.pythonProcess = null;
        global.isAutomationRunning = false;
        
        return resolve({
          success: true,
          message: 'Automation stopped (with cleanup)',
          warning: error.message
        });
      }
    });
  },

  /**
   * Create a temporary configuration file for the Python script
   * @param {Object} config - Configuration options
   * @returns {Promise<string>} Path to the created config file
   */
  async createConfigFile(config) {
    try {
      let accessToken = '';
      try {
        console.log('[createConfigFile] Starting token retrieval...');
        
        // Try to get access token
        accessToken = await tokenManager.getAccessToken();
        
        // FALLBACK: If tokenManager fails, try direct store access
        if (!accessToken) {
          console.log('[createConfigFile] tokenManager.getAccessToken() returned null, trying direct store access...');
          try {
            const Store = require('electron-store');
            const directTokenStore = new Store({
              name: 'auth-tokens',
              encryptionKey: 'junior-secure-app-token-encryption',
            });
            const directTokens = directTokenStore.get('tokens');
            if (directTokens && directTokens.access_token) {
              accessToken = directTokens.access_token;
              console.log('[createConfigFile] ✅ Successfully retrieved access token via direct store access');
            } else {
              console.log('[createConfigFile] ❌ No tokens found in direct store access either');
            }
          } catch (directError) {
            console.error('[createConfigFile] ❌ Direct store access failed:', directError.message);
          }
        }
        console.log(
          '[createConfigFile] Retrieved access token for config:',
          accessToken ? `Token found (${accessToken.substring(0, 20)}...)` : 'No token'
        );
        
        // Additional debugging - check raw token store
        const Store = require('electron-store');
        const tokenStore = new Store({
          name: 'auth-tokens',
          encryptionKey: 'junior-secure-app-token-encryption',
        });
        const rawTokens = tokenStore.get('tokens');
        console.log('[createConfigFile] Raw tokens from store:', rawTokens ? 'Found' : 'NULL');
        if (rawTokens) {
          console.log('[createConfigFile] Token keys available:', Object.keys(rawTokens));
          console.log('[createConfigFile] Access token in raw:', !!rawTokens.access_token);
        }
        
        if (accessToken) {
          console.log('[createConfigFile] ✅ Access token will be added to Python config');
        } else {
          console.warn('[createConfigFile] ⚠️ WARNING: No access token available - Python script will fail to authenticate with backend');
        }
      } catch (error) {
        console.error(
          '[createConfigFile] ❌ ERROR retrieving access token:',
          error.message
        );
        console.error('[createConfigFile] Stack trace:', error.stack);
      }

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
        backend_url: process.env.API_URL || 'https://junior-api-915940312680.us-west1.run.app',
        browser_config: {
          chrome_profile_path: chromeProfilePath,
          headless: false,
        },
        access_token: accessToken,
        chrome_profile_path: chromeProfilePath, // Additional field for the Python script
        debug_mode: config.debugMode !== undefined ? config.debugMode : true,
        max_daily_comments: config.limits?.dailyComments || 50,
        max_session_comments: config.limits?.sessionComments || 10,
        calendly_link: config.userInfo?.calendlyLink || '',
        job_keywords: keywords, // Pass keywords as a string - the script will split it
        user_bio: config.userInfo?.bio || '',
        log_file_path: this.getLogFilePath(),
        scroll_pause_time: config.timing?.scrollPauseTime || 5,
        short_sleep_seconds: config.timing?.shortSleepSeconds || 180,
        max_comments: config.limits?.commentsPerCycle || 3,
      };
      
      // Debug: Log what's being written to config
      console.log('[createConfigFile] Writing config to:', configPath);
      console.log('[createConfigFile] Config contains access_token:', !!pythonConfig.access_token);
      if (pythonConfig.access_token) {
        console.log('[createConfigFile] Access token preview:', pythonConfig.access_token.substring(0, 30) + '...');
      }
      
      console.log('[createConfigFile] Keywords value:', keywords);
      
      fs.writeFileSync(configPath, JSON.stringify(pythonConfig, null, 2));
      console.log('[createConfigFile] Config file written successfully');
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
};

/**
 * Force reset the automation state - use this to clear stuck states
 * @returns {Object} Result of the reset operation
 */
automationService.forceResetState = function() {
  const wasRunning = global.isAutomationRunning;
  
  // Force kill any process if it exists
  if (global.pythonProcess) {
    try {
      if (process.platform === 'win32') {
        // On Windows
        spawn('taskkill', ['/pid', global.pythonProcess.pid, '/f', '/t']);
      } else {
        // On macOS/Linux
        process.kill(global.pythonProcess.pid);
      }
    } catch (e) {
      // Ignore errors during forced kill
      console.log('[forceResetState] Error killing process:', e.message);
    }
  }
  
  // Reset state variables
  global.pythonProcess = null;
  global.isAutomationRunning = false;
  
  console.log(`Forced reset of automation state. Was running: ${wasRunning}`);
  
  return {
    success: true,
    wasRunning,
    message: 'Automation state has been forcibly reset'
  };
};

module.exports = automationService;
