const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const { app } = require('electron');

/**
 * Service to manage bundled Python executable
 */
const pythonBundleService = {
  /**
   * Get the path to the bundled Python executable
   * @returns {string} Path to the bundled Python executable
   */
  getBundledPythonPath() {
    const platform = process.platform;
    const arch = process.arch;

    // Get the resources directory (different in development vs production)
    const resourcesPath = app.isPackaged
      ? process.resourcesPath // In production, extraResources go directly to resourcesPath
      : path.join(app.getAppPath(), 'resources');

    let executableName;
    let platformDir;

    switch (platform) {
      case 'win32':
        platformDir = arch === 'x64' ? 'win-x64' : 'win-ia32';
        executableName = 'linkedin_commenter.exe';
        break;
      case 'darwin':
        platformDir = arch === 'arm64' ? 'mac-arm64' : 'mac-x64';
        executableName = 'linkedin_commenter';
        break;
      case 'linux':
        platformDir = arch === 'x64' ? 'linux-x64' : 'linux-ia32';
        executableName = 'linkedin_commenter';
        break;
      default:
        throw new Error(`Unsupported platform: ${platform}`);
    }

    const executablePath = path.join(
      resourcesPath,
      'python-executables',
      platformDir,
      executableName
    );

    if (!fs.existsSync(executablePath)) {
      throw new Error(
        `Bundled Python executable not found at: ${executablePath}`
      );
    }

    return executablePath;
  },

  /**
   * Get the path to the LinkedIn commenter script (not needed for standalone executable)
   * @returns {string} Path to the LinkedIn commenter script
   */
  getScriptPath() {
    // For standalone executable, script is embedded, so we return null
    // But keep this method for compatibility
    return null;
  },

  /**
   * Check if bundled Python executable exists and should be used
   * @returns {boolean} True if bundled executable exists and should be used
   */
  isBundledPythonAvailable() {
    try {
      // Clear separation: Development vs Production
      if (!app.isPackaged) {
        console.log(
          '[Python Bundle] Development mode - bundled Python disabled'
        );
        return false;
      }

      // Production mode: ONLY use bundled Python
      const executablePath = this.getBundledPythonPath();
      const exists = fs.existsSync(executablePath);

      console.log('[Python Bundle] Production mode - checking bundled Python:');
      console.log(
        `[Python Bundle] - Platform: ${process.platform}-${process.arch}`
      );
      console.log(`[Python Bundle] - Expected executable: ${executablePath}`);
      console.log(`[Python Bundle] - File exists: ${exists}`);

      if (!exists) {
        // Debug missing bundled Python in production
        console.error(
          '[Python Bundle] CRITICAL: Bundled Python executable missing in production!'
        );
        this._debugMissingBundledPython();
        throw new Error(`Bundled Python executable missing: ${executablePath}`);
      }

      return true;
    } catch (error) {
      console.error(
        '[Python Bundle] Bundled Python check failed:',
        error.message
      );
      if (app.isPackaged) {
        // In production, this is a critical error
        throw error;
      }
      return false;
    }
  },

  /**
   * Debug helper for missing bundled Python
   * @private
   */
  _debugMissingBundledPython() {
    try {
      const resourcesPath = process.resourcesPath;
      console.log(`[Python Bundle Debug] Resources path: ${resourcesPath}`);

      if (fs.existsSync(resourcesPath)) {
        const contents = fs.readdirSync(resourcesPath);
        console.log('[Python Bundle Debug] Resources contents:', contents);

        const pythonDir = path.join(resourcesPath, 'python-executables');
        if (fs.existsSync(pythonDir)) {
          const pythonContents = fs.readdirSync(pythonDir);
          console.log(
            '[Python Bundle Debug] Python dir contents:',
            pythonContents
          );
        } else {
          console.log(
            '[Python Bundle Debug] Python executables directory missing'
          );
        }
      } else {
        console.log('[Python Bundle Debug] Resources path does not exist');
      }
    } catch (error) {
      console.error('[Python Bundle Debug] Error during debug:', error.message);
    }
  },

  /**
   * Run the bundled Python executable (standalone executable)
   * @param {Array<string>} args - Arguments to pass to the executable
   * @param {Object} options - Spawn options
   * @returns {ChildProcess} The spawned process
   */
  runBundledPython(args = [], options = {}) {
    const executablePath = this.getBundledPythonPath();

    // Make sure the executable has the right permissions on Unix systems
    if (process.platform !== 'win32') {
      try {
        fs.chmodSync(executablePath, '755');
      } catch (error) {
        console.warn('Could not set executable permissions:', error.message);
      }
    }

    console.log(
      `Running bundled standalone executable: ${executablePath} ${args.join(' ')}`
    );

    // For standalone executable, we run it directly with arguments
    return spawn(executablePath, args, {
      ...options,
      stdio: options.stdio || ['pipe', 'pipe', 'pipe'],
    });
  },

  /**
   * Get the fallback Python executable (system Python)
   * @returns {string} Python executable name
   */
  getFallbackPython() {
    return process.platform === 'win32' ? 'python' : 'python3';
  },

  /**
   * Check if system Python is available
   * @returns {Promise<boolean>} True if system Python is available
   */
  async isSystemPythonAvailable() {
    return new Promise(resolve => {
      const pythonExecutable = this.getFallbackPython();
      const checkProcess = spawn(pythonExecutable, ['--version']);

      checkProcess.on('close', code => {
        resolve(code === 0);
      });

      checkProcess.on('error', () => {
        resolve(false);
      });

      // Timeout after 5 seconds
      setTimeout(() => {
        checkProcess.kill();
        resolve(false);
      }, 5000);
    });
  },
};

module.exports = pythonBundleService;
