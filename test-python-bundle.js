#!/usr/bin/env node

// Test script to verify Python bundle service without launching the full app
const path = require("path");
const fs = require("fs");

// Mock app for testing
const mockApp = {
  isPackaged: true,
  getAppPath: () => process.cwd(),
};

// Mock process.resourcesPath for testing
const appBundle = path.join(__dirname, "dist/mac-arm64/Junior Desktop.app");
process.resourcesPath = path.join(appBundle, "Contents/Resources");

console.log("=== Python Bundle Service Test ===");
console.log("Testing from app bundle:", appBundle);
console.log("Resources path:", process.resourcesPath);
console.log("Platform:", process.platform, process.arch);

// Load the Python bundle service
const pythonBundleService = require("./src/services/automation/pythonBundleService.js");

try {
  // Override app.isPackaged for testing
  Object.defineProperty(global, "app", {
    value: mockApp,
  });

  // Test if bundled Python is available
  console.log("\n=== Testing Bundled Python ===");
  const isAvailable = pythonBundleService.isBundledPythonAvailable();
  console.log("Bundled Python available:", isAvailable);

  if (isAvailable) {
    const pythonPath = pythonBundleService.getBundledPythonPath();
    console.log("Python path:", pythonPath);
    console.log("File exists:", fs.existsSync(pythonPath));

    if (fs.existsSync(pythonPath)) {
      const stats = fs.statSync(pythonPath);
      console.log("File size:", stats.size, "bytes");
      console.log("Is executable:", !!(stats.mode & parseInt("111", 8)));
    }
  }
} catch (error) {
  console.error("Test failed:", error.message);
  console.error("Stack:", error.stack);
}

console.log("\n=== Test Complete ===");
