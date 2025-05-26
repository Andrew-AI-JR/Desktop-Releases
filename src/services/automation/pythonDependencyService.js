const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const { app } = require("electron");

/**
 * Service to manage Python dependencies for the automation scripts
 */
const pythonDependencyService = {
  /**
   * Check if Python is installed and accessible
   * @returns {Promise<boolean>} True if Python is installed
   */
  async isPythonInstalled() {
    return new Promise((resolve) => {
      const pythonExecutable =
        process.platform === "win32" ? "python" : "python3";

      const pythonProcess = spawn(pythonExecutable, ["--version"]);

      pythonProcess.on("error", () => {
        // Python not found
        resolve(false);
      });

      pythonProcess.on("close", (code) => {
        resolve(code === 0);
      });
    });
  },

  /**
   * Get the path to the requirements.txt file
   * @returns {string} Path to requirements.txt
   */
  getRequirementsPath() {
    const possiblePaths = [
      path.join(app.getAppPath(), "resources", "scripts", "requirements.txt"),
      path.join(
        app.getAppPath(),
        "src",
        "resources",
        "scripts",
        "requirements.txt"
      ),
    ];

    for (const reqPath of possiblePaths) {
      if (fs.existsSync(reqPath)) {
        console.log(`Found requirements.txt at: ${reqPath}`);
        return reqPath;
      }
    }

    throw new Error("requirements.txt not found");
  },

  /**
   * Install Python dependencies listed in requirements.txt
   * @returns {Promise<{success: boolean, message: string}>} Installation result
   */
  async installDependencies() {
    try {
      const isPythonAvailable = await this.isPythonInstalled();

      if (!isPythonAvailable) {
        return {
          success: false,
          message: "Python not found. Please install Python 3.x and try again.",
        };
      }

      const requirementsPath = this.getRequirementsPath();

      return new Promise((resolve) => {
        const pythonExecutable =
          process.platform === "win32" ? "python" : "python3";
        const pipArgs = ["-m", "pip", "install", "-r", requirementsPath];

        console.log(
          `Installing Python dependencies: ${pythonExecutable} ${pipArgs.join(
            " "
          )}`
        );

        const pipProcess = spawn(pythonExecutable, pipArgs);

        let stdoutData = "";
        let stderrData = "";

        pipProcess.stdout.on("data", (data) => {
          const output = data.toString();
          stdoutData += output;
          console.log("pip stdout:", output);
        });

        pipProcess.stderr.on("data", (data) => {
          const output = data.toString();
          stderrData += output;
          console.error("pip stderr:", output);
        });

        pipProcess.on("error", (error) => {
          console.error("pip process error:", error);
          resolve({
            success: false,
            message: `Failed to start pip: ${error.message}`,
            error: error.message,
          });
        });

        pipProcess.on("close", (code) => {
          if (code === 0) {
            resolve({
              success: true,
              message: "Dependencies installed successfully",
              output: stdoutData,
            });
          } else {
            resolve({
              success: false,
              message: `Failed to install dependencies (exit code ${code})`,
              error: stderrData,
            });
          }
        });
      });
    } catch (error) {
      console.error("Error installing dependencies:", error);
      return {
        success: false,
        message: error.message || "Failed to install dependencies",
      };
    }
  },

  /**
   * Check and install dependencies if needed
   * @param {Function} progressCallback - Callback for installation progress updates
   * @returns {Promise<boolean>} True if dependencies are installed
   */
  async ensureDependencies(progressCallback = null) {
    try {
      if (progressCallback) {
        progressCallback("Checking for Python installation...");
      }

      const isPythonAvailable = await this.isPythonInstalled();

      if (!isPythonAvailable) {
        if (progressCallback) {
          progressCallback(
            "Python not found. Please install Python 3.x and try again."
          );
        }
        return false;
      }

      if (progressCallback) {
        progressCallback("Installing required Python packages...");
      }

      const result = await this.installDependencies();

      if (progressCallback) {
        progressCallback(result.message);
      }

      return result.success;
    } catch (error) {
      console.error("Error ensuring dependencies:", error);
      if (progressCallback) {
        progressCallback(`Error: ${error.message}`);
      }
      return false;
    }
  },
};

module.exports = pythonDependencyService;
