#!/usr/bin/env node

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

console.log("🔧 Starting robust DMG build process...");

// Clean previous builds
console.log("🧹 Cleaning previous builds...");
try {
  execSync("rm -rf dist", { stdio: "inherit" });
  execSync("rm -rf node_modules/.cache", { stdio: "inherit" });
  console.log("✅ Cleaned build directories");
} catch (error) {
  console.log("⚠️  Warning: Could not clean all directories");
}

// Clean temporary DMG files that might be causing issues
console.log("🧹 Cleaning temporary DMG files...");
try {
  execSync("rm -rf /tmp/t-*", { stdio: "inherit" });
  console.log("✅ Cleaned temporary files");
} catch (error) {
  console.log("⚠️  Warning: Could not clean temporary files");
}

// Set environment variables for better resource management
process.env.NODE_OPTIONS = "--max-old-space-size=4096 --max-heap-size=4096";
process.env.ELECTRON_BUILDER_CACHE = path.join(
  __dirname,
  "..",
  "node_modules",
  ".cache",
  "electron-builder"
);

// Build Python component first
console.log("🐍 Building Python component...");
try {
  execSync("npm run build:python", { stdio: "inherit" });
  console.log("✅ Python build completed");
} catch (error) {
  console.error("❌ Python build failed:", error.message);
  process.exit(1);
}

// Wait for system to settle
console.log("⏳ Waiting for system to settle...");
setTimeout(() => {
  buildDMG();
}, 2000);

function buildDMG() {
  console.log("📦 Building DMG...");

  const maxRetries = 3;
  let retryCount = 0;

  function attemptBuild() {
    console.log(`Attempt ${retryCount + 1} of ${maxRetries}`);

    try {
      // Try building x64 first (usually more stable)
      execSync("npx electron-builder --mac --x64 --publish=never", {
        stdio: "inherit",
        env: {
          ...process.env,
          ELECTRON_BUILDER_DMG_FORMAT: "UDBZ",
        },
      });

      console.log("✅ x64 DMG build successful!");

      // Then build arm64
      execSync("npx electron-builder --mac --arm64 --publish=never", {
        stdio: "inherit",
        env: {
          ...process.env,
          ELECTRON_BUILDER_DMG_FORMAT: "UDBZ",
        },
      });

      console.log("✅ arm64 DMG build successful!");
      console.log("🎉 All builds completed successfully!");

      // List final outputs
      execSync("ls -la dist/", { stdio: "inherit" });
    } catch (error) {
      console.error(
        `❌ Build attempt ${retryCount + 1} failed:`,
        error.message
      );
      retryCount++;

      if (retryCount < maxRetries) {
        console.log("🔄 Cleaning up and retrying...");

        // Clean up any partial builds
        try {
          execSync("rm -rf dist", { stdio: "inherit" });
          execSync("rm -rf /tmp/t-*", { stdio: "inherit" });
        } catch (cleanError) {
          console.log("⚠️  Warning during cleanup:", cleanError.message);
        }

        // Wait before retry
        setTimeout(() => {
          attemptBuild();
        }, 10000);
      } else {
        console.error("❌ Max retries reached. Build failed.");
        console.error("💡 Try running: sudo purge && npm run build:dmg:single");
        process.exit(1);
      }
    }
  }

  attemptBuild();
}
