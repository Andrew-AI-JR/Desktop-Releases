const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

// Configuration
const config = {
  scriptPath: 'src/resources/scripts/linkedin_commenter.py',
  outputDir: 'resources/python-executables/win-x64',
  buildDir: 'build/pyinstaller',
  executableName: 'linkedin_commenter.exe',
  pythonCmd: 'python',
  requirements: 'src/resources/scripts/requirements.txt'
};

// Utility functions
function log(message, level = 'info') {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] [${level.toUpperCase()}] ${message}`);
}

function runCommand(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    log(`Running: ${command} ${args.join(' ')}`, 'debug');
    const process = spawn(command, args, { ...options });
    
    let stdout = '';
    let stderr = '';
    
    process.stdout.on('data', (data) => {
      const str = data.toString();
      stdout += str;
      process.stdout.write(str);
    });
    
    process.stderr.on('data', (data) => {
      const str = data.toString();
      stderr += str;
      process.stderr.write(str);
    });
    
    process.on('close', (code) => {
      if (code === 0) {
        resolve({ stdout, stderr });
      } else {
        const error = new Error(`Command failed with code ${code}`);
        error.stdout = stdout;
        error.stderr = stderr;
        reject(error);
      }
    });
    
    process.on('error', (error) => {
      error.stdout = stdout;
      error.stderr = stderr;
      reject(error);
    });
  });
}

async function main() {
  try {
    log('Starting Python executable build process');
    
    // Create output directories
    fs.mkdirSync(config.outputDir, { recursive: true });
    fs.mkdirSync(config.buildDir, { recursive: true });
    
    // Install requirements
    log('Installing Python dependencies...');
    await runCommand(config.pythonCmd, [
      '-m', 'pip', 'install', '-r', config.requirements
    ]);
    
    // Build with PyInstaller
    log('Building executable with PyInstaller...');
    await runCommand(config.pythonCmd, [
      '-m', 'PyInstaller',
      '--onefile',
      '--noconsole',
      '--clean',
      '--distpath', config.outputDir,
      '--workpath', path.join(config.buildDir, 'work'),
      '--specpath', path.join(config.buildDir, 'spec'),
      '--name', path.basename(config.executableName, '.exe'),
      config.scriptPath
    ]);
    
    log('Build completed successfully!');
    log(`Executable created at: ${path.join(config.outputDir, config.executableName)}`);
    
  } catch (error) {
    log(`Build failed: ${error.message}`, 'error');
    process.exit(1);
  }
}

// Run the build
main();
