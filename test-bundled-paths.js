#!/usr/bin/env node

// Test script to verify bundled Python paths in production build
const path = require("path");
const fs = require("fs");

// Simulate Electron app environment
const mockApp = {
  isPackaged: true,
  getAppPath: () =>
    "/Applications/Junior Desktop.app/Contents/Resources/app.asar",
  getPath: (name) => {
    if (name === "userData") {
      return path.join(
        process.env.HOME,
        "Library",
        "Application Support",
        "Junior Desktop"
      );
    }
    return "/tmp";
  },
};

// Mock process.resourcesPath for production build
process.resourcesPath = "/Applications/Junior Desktop.app/Contents/Resources";

// Import and test the services
const automationService = require("./src/services/automation/automationService");
const pythonBundleService = require("./src/services/automation/pythonBundleService");

console.log("Testing bundled Python detection...");
console.log("process.resourcesPath:", process.resourcesPath);
console.log("app.isPackaged:", mockApp.isPackaged);

try {
  // Test if bundled Python is detected
  const hasBundledPython = pythonBundleService.hasBundledPython();
  console.log("Has bundled Python:", hasBundledPython);

  if (hasBundledPython) {
    const bundledPath = pythonBundleService.getBundledPythonPath();
    console.log("Bundled Python path:", bundledPath);
    console.log("Bundled Python exists:", fs.existsSync(bundledPath));
  }

  // Test script path finding
  const scriptPath = automationService.findBundledScriptPath();
  console.log("Script path:", scriptPath);
  console.log("Script exists:", fs.existsSync(scriptPath));
} catch (error) {
  console.error("Error testing bundled paths:", error.message);
}
