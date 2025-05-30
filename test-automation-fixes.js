#!/usr/bin/env node

/**
 * Test script to verify automation service fixes
 */

const { app } = require("electron");
const path = require("path");
const fs = require("fs");

// Mock Electron app for testing
const mockApp = {
  isPackaged: false, // Test development mode
  getPath: (name) => {
    if (name === "userData") {
      return "/tmp/junior-test";
    }
    return "/tmp";
  },
  getAppPath: () => {
    return process.cwd();
  },
};

// Replace the real app with our mock
Object.assign(app, mockApp);

// Mock global mainWindow
global.mainWindow = {
  webContents: {
    send: (channel, data) => {
      console.log(`[IPC] ${channel}:`, data);
    },
  },
};

const automationService = require("./src/services/automation/automationService");

async function testAutomationService() {
  console.log("🧪 Testing Automation Service Fixes...\n");

  // Test path methods
  console.log("📁 Testing path methods:");
  const logPath = automationService.getLogFilePath();
  const chromePath = automationService.getChromeProfilePath();

  console.log(`Log file path: ${logPath}`);
  console.log(`Chrome profile path: ${chromePath}`);

  // Check if directories are created
  console.log(`Log directory exists: ${fs.existsSync(path.dirname(logPath))}`);
  console.log(
    `Chrome profile directory exists: ${fs.existsSync(chromePath)}\n`
  );

  // Test error detection
  console.log("🔍 Testing error detection:");

  const testErrorPatterns = [
    "Traceback (most recent call last):",
    "PermissionError: [Errno 13] Permission denied",
    "ChromeDriverException: Something went wrong",
    "FileNotFoundError: No such file",
    "This is just normal output",
  ];

  testErrorPatterns.forEach((pattern) => {
    const hasError = automationService._containsErrorIndicators(pattern);
    console.log(
      `"${pattern.slice(0, 30)}..." -> ${hasError ? "❌ ERROR" : "✅ OK"}`
    );
  });

  console.log("\n✅ All tests completed!");
}

testAutomationService().catch(console.error);
