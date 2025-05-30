#!/usr/bin/env node

const { spawn } = require("child_process");

async function testChromeDetection() {
  console.log("=== Chrome Detection Test ===");
  console.log("Platform:", process.platform);

  return new Promise((resolve) => {
    let chromeCommand;
    let chromeArgs = ["--version"];

    if (process.platform === "darwin") {
      chromeCommand =
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
    }

    console.log("Testing command:", chromeCommand, chromeArgs.join(" "));

    const chromeProcess = spawn(chromeCommand, chromeArgs, {
      stdio: "pipe",
      windowsHide: true,
    });

    let stdout = "";
    let stderr = "";

    chromeProcess.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    chromeProcess.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    chromeProcess.on("close", (code) => {
      console.log("Exit code:", code);
      console.log("Stdout:", stdout.trim());
      console.log("Stderr:", stderr.trim());
      console.log("Chrome available:", code === 0);
      resolve(code === 0);
    });

    chromeProcess.on("error", (error) => {
      console.log("Process error:", error.message);
      resolve(false);
    });

    // Timeout after 5 seconds
    setTimeout(() => {
      console.log("Timeout - killing process");
      chromeProcess.kill();
      resolve(false);
    }, 5000);
  });
}

testChromeDetection().then((result) => {
  console.log("Final result:", result);
  process.exit(result ? 0 : 1);
});
