const { spawn, exec } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

/**
 * PyInstaller-based Python executable builder
 * Creates a standalone executable that includes Python and all dependencies
 */

const PYTHON_EXECUTABLES_DIR = 'resources/python-executables';
const BUILD_DIR = 'build/pyinstaller';
const SCRIPT_SOURCE = 'src/resources/scripts/linkedin_commenter.py';

function getPlatformInfo() {
  const platform = os.platform();
  const arch = os.arch();

  let platformDir;
  let pythonCmd;
  let executableName;

  switch (platform) {
    case 'win32':
      platformDir = arch === 'x64' ? 'win-x64' : 'win-ia32';
      pythonCmd = 'python';
      executableName = 'linkedin_commenter.exe';
      break;
    case 'darwin':
      platformDir = arch === 'arm64' ? 'mac-arm64' : 'mac-x64';
      pythonCmd = 'python3';
      executableName = 'linkedin_commenter';
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
  return outputDir;
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
  const { pythonCmd, platformDir, executableName } = getPlatformInfo();
  const outputDir = path.join(PYTHON_EXECUTABLES_DIR, platformDir);

  return new Promise((resolve, reject) => {
    console.log(`Building standalone executable for ${platformDir}...`);

    // PyInstaller arguments for creating a standalone executable
    const args = [
      '-m',
      'PyInstaller',
      '--onefile',              // Create a single executable file
      '--noconsole',            // Don't show console window (Windows)
      '--clean',                // Clean PyInstaller cache
      '--distpath', outputDir,  // Output directory
      '--workpath', BUILD_DIR,  // Work directory
      '--name', executableName.replace('.exe', ''), // Executable name
      SCRIPT_SOURCE             // Script to build
    ];

    console.log(`Running: ${pythonCmd} ${args.join(' ')}`);

    const process = spawn(pythonCmd, args, {
      stdio: 'inherit',
    });

    process.on('close', code => {
      if (code === 0) {
        console.log(`Build completed successfully for ${platformDir}`);
        
        // Check if the executable was created
        const expectedPath = path.join(outputDir, executableName);
        if (fs.existsSync(expectedPath)) {
          console.log(`✅ Executable created: ${expectedPath}`);
          resolve();
        } else {
          reject(new Error(`Executable not found at expected path: ${expectedPath}`));
        }
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
    console.log('Starting PyInstaller build process...');

    // Check if Python script exists
    if (!fs.existsSync(SCRIPT_SOURCE)) {
      throw new Error('linkedin_commenter.py script not found');
    }

    const { platformDir, executableName } = getPlatformInfo();
    console.log(`Building for platform: ${platformDir}`);

    // In development, check if executable already exists and skip if it does
    const executablePath = path.join(
      PYTHON_EXECUTABLES_DIR,
      platformDir,
      executableName
    );
    if (fs.existsSync(executablePath)) {
      const stats = fs.statSync(executablePath);
      const scriptStats = fs.statSync(SCRIPT_SOURCE);
      
      // Only skip if executable is newer than the script
      if (stats.mtime > scriptStats.mtime) {
        console.log(`✅ Executable already exists and is up to date: ${executablePath}`);
        console.log('Skipping build. Delete the file to force rebuild.');
        return;
      }
    }

    // Create necessary directories
    createDirectories();

    // Check Python installation
    await checkPython();

    // Install PyInstaller
    await installPyInstaller();

    // Install Python dependencies
    await installDependencies();

    // Build the standalone executable
    await buildExecutable();

    console.log('✅ PyInstaller build completed successfully!');
  } catch (error) {
    console.error('❌ Build failed:', error.message);
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
