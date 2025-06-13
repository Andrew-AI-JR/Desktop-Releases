const fs = require('fs');
const path = require('path');
const fse = require('fs-extra');

const srcDir = path.join(__dirname, '..', 'chromium-win64', 'chrome-win');
const chromedriver = path.join(__dirname, '..', 'chromium-win64', 'chromedriver-win64', 'chromedriver-win64', 'chromedriver.exe');

// Allow overriding dist output directory via environment variable so we can
// build into a fresh folder (e.g., dist-build) when the default `dist` is
// locked by another process.
const OUTPUT_DIR = process.env.BUILD_OUTPUT_DIR || 'dist-build';
const destDir = path.join(__dirname, '..', OUTPUT_DIR, 'win-unpacked', 'resources', 'chrome-win');

// Copy all Chromium 137 files
fse.copySync(srcDir, destDir, { overwrite: true });
console.log(`Copied Chromium 137 files from ${srcDir} to ${destDir}`);

// Copy the matching chromedriver.exe
fse.copyFileSync(chromedriver, path.join(destDir, 'chromedriver.exe'));
console.log(`Copied chromedriver.exe to ${destDir}`);
