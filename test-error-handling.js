#!/usr/bin/env node

/**
 * Test script to validate the error handling improvements
 */

const { spawn } = require("child_process");
const path = require("path");

console.log("Testing Electron app error handling improvements...");

// Start the app
const electronProcess = spawn("npm", ["start"], {
  cwd: "/Users/roberthall/projects/junior-desktop",
  stdio: "inherit",
});

electronProcess.on("error", (error) => {
  console.error("Failed to start Electron app:", error);
  process.exit(1);
});

electronProcess.on("close", (code) => {
  console.log(`Electron app exited with code ${code}`);
  process.exit(code);
});

// Handle process termination
process.on("SIGINT", () => {
  console.log("\nTerminating Electron app...");
  electronProcess.kill("SIGINT");
  process.exit(0);
});

process.on("SIGTERM", () => {
  console.log("\nTerminating Electron app...");
  electronProcess.kill("SIGTERM");
  process.exit(0);
});
