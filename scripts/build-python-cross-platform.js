const { spawn, exec } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

/**
 * Cross-platform Python executable builder
 * This script builds Python executables for the current platform
 * Usage:
 *   npm run build:python       - Build for current platform only
 *   npm run build:python:local - Use local shell script (Unix only)
 */

const PYTHON_EXECUTABLES_DIR = 'resources/python-executables';
const BUILD_DIR = 'build/pyinstaller';

// Check if we're in development mode (only build for current platform)
const isDevelopment = process.env.NODE_ENV !== 'production' && !process.env.CI;

function getPlatformInfo() {
  const platform = os.platform();
  const arch = os.arch();

  let platformDir;
  let pythonCmd;
  let executableName;

  switch (platform) {
    case 'darwin':
      platformDir = arch === 'arm64' ? 'mac-arm64' : 'mac-x64';
      pythonCmd = 'python3';
      executableName = 'linkedin_commenter';
      break;
    case 'win32':
      platformDir = arch === 'x64' ? 'win-x64' : 'win-ia32';
      pythonCmd = 'python';
      executableName = 'linkedin_commenter.exe';
      break;
    case 'linux':
      platformDir = arch === 'x64' ? 'linux-x64' : 'linux-ia32';
      pythonCmd = 'python3';
      executableName = 'linkedin_commenter';
      break;
    default:
      throw new Error(`Unsupported platform: ${platform}`);
  }

  return { platformDir, pythonCmd, platform, executableName };
}

function createDirectories() {
  const { platformDir } = getPlatformInfo();
  const outputDir = path.join(PYTHON_EXECUTABLES_DIR, platformDir);

  // Create directories
  fs.mkdirSync(outputDir, { recursive: true });
  fs.mkdirSync(BUILD_DIR, { recursive: true });

  console.log(`Created directories: ${outputDir}, ${BUILD_DIR}`);
}

function checkPython() {
  const { pythonCmd } = getPlatformInfo();

  return new Promise((resolve, reject) => {
    exec(`${pythonCmd} --version`, (error, stdout, _stderr) => {
      if (error) {
        reject(
          new Error(
            `Python not found. Please install Python 3.x: ${error.message}`
          )
        );
        return;
      }

      console.log(`Found Python: ${stdout.trim()}`);
      resolve();
    });
  });
}

function installPyInstaller() {
  const { pythonCmd } = getPlatformInfo();

  return new Promise((resolve, reject) => {
    console.log('Installing PyInstaller...');

    const process = spawn(pythonCmd, ['-m', 'pip', 'install', 'pyinstaller'], {
      stdio: 'inherit',
    });

    process.on('close', code => {
      if (code === 0) {
        console.log('PyInstaller installed successfully');
        resolve();
      } else {
        reject(new Error(`Failed to install PyInstaller (exit code: ${code})`));
      }
    });

    process.on('error', error => {
      reject(new Error(`Failed to install PyInstaller: ${error.message}`));
    });
  });
}

function installDependencies() {
  const { pythonCmd } = getPlatformInfo();
  const requirementsPath = 'src/resources/scripts/requirements.txt';

  return new Promise((resolve, reject) => {
    console.log('Installing Python dependencies...');

    const process = spawn(
      pythonCmd,
      ['-m', 'pip', 'install', '-r', requirementsPath],
      {
        stdio: 'inherit',
      }
    );

    process.on('close', code => {
      if (code === 0) {
        console.log('Dependencies installed successfully');
        resolve();
      } else {
        reject(
          new Error(`Failed to install dependencies (exit code: ${code})`)
        );
      }
    });

    process.on('error', error => {
      reject(new Error(`Failed to install dependencies: ${error.message}`));
    });
  });
}

function buildExecutable() {
  const { pythonCmd, platformDir } = getPlatformInfo();
  const specFile = 'linkedin_commenter.spec';
  const outputDir = path.join(PYTHON_EXECUTABLES_DIR, platformDir);

  return new Promise((resolve, reject) => {
    console.log(`Building Python executable for ${platformDir}...`);

    const args = [
      '-m',
      'PyInstaller',
      '--distpath',
      outputDir,
      '--workpath',
      BUILD_DIR,
      specFile,
    ];

    const process = spawn(pythonCmd, args, {
      stdio: 'inherit',
    });

    process.on('close', code => {
      if (code === 0) {
        console.log(`Build completed successfully for ${platformDir}`);
        console.log(`Executable location: ${outputDir}/linkedin_commenter`);
        resolve();
      } else {
        reject(new Error(`Build failed (exit code: ${code})`));
      }
    });

    process.on('error', error => {
      reject(new Error(`Build failed: ${error.message}`));
    });
  });
}

async function main() {
  try {
    console.log('Starting Python executable build process...');

    // Check if spec file exists
    if (!fs.existsSync('linkedin_commenter.spec')) {
      throw new Error('linkedin_commenter.spec file not found');
    }

    // Check if Python script exists
    if (!fs.existsSync('src/resources/scripts/linkedin_commenter.py')) {
      throw new Error('linkedin_commenter.py script not found');
    }

    const { platformDir, executableName } = getPlatformInfo();
    console.log(`Building for platform: ${platformDir}`);

    // In development, check if executable already exists and skip if it does
    // if (isDevelopment) {
    //   const executablePath = path.join(
    //     PYTHON_EXECUTABLES_DIR,
    //     platformDir,
    //     executableName
    //   );
    //   if (fs.existsSync(executablePath)) {
    //     console.log(`✅ Python executable already exists: ${executablePath}`);
    //     console.log(
    //       'Skipping build in development mode. Delete the file to force rebuild.'
    //     );
    //     return;
    //   }
    // }

    // Create necessary directories
    createDirectories();

    // Check Python installation
    await checkPython();

    // Install PyInstaller
    await installPyInstaller();

    // Install Python dependencies
    await installDependencies();

    // Build the executable
    await buildExecutable();

    console.log('Python executable build completed successfully!');
  } catch (error) {
    console.error('Build failed:', error.message);
    process.exit(1);
  }
}

// Run if this script is executed directly
if (require.main === module) {
  main();
}

module.exports = {
  getPlatformInfo,
  buildExecutable,
  main,
};
