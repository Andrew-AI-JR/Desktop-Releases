#!/usr/bin/env node

/**
 * Test script to verify bundled Python path logic
 * This simulates how the app would behave in different environments
 */

const path = require("path");
const fs = require("fs");

// Mock Electron app object for testing
const createMockApp = (isPackaged, resourcesPath = null) => ({
  isPackaged,
  getAppPath: () => process.cwd(),
  getPath: (name) => {
    if (name === "userData") return "/tmp/test-user-data";
    if (name === "temp") return "/tmp";
    return "/tmp";
  },
});

// Mock process.resourcesPath
const setResourcesPath = (resourcesPath) => {
  if (resourcesPath) {
    process.resourcesPath = resourcesPath;
  } else {
    delete process.resourcesPath;
  }
};

// Test the production script finding logic
const testProductionScript = (resourcesPath) => {
  console.log(`\n🧪 Testing Production Mode`);
  console.log(`Resources path: ${resourcesPath || "undefined"}`);

  setResourcesPath(resourcesPath);

  try {
    if (!process.resourcesPath) {
      throw new Error("Resources path not available in production build");
    }

    const bundledScriptPath = path.join(
      process.resourcesPath,
      "linkedin_commenter.py"
    );
    console.log(`[Production Script] Checking: ${bundledScriptPath}`);

    if (!fs.existsSync(bundledScriptPath)) {
      // Debug what's actually in resources
      try {
        const resourcesContents = fs.readdirSync(process.resourcesPath);
        console.error(
          `[Production Script] Resources contents:`,
          resourcesContents
        );
      } catch (error) {
        console.error(
          `[Production Script] Cannot read resources directory:`,
          error.message
        );
      }

      throw new Error(
        `Bundled script not found: ${bundledScriptPath}. The app build may be incomplete.`
      );
    }

    console.log(`[Production Script] ✅ Found: ${bundledScriptPath}`);
    return bundledScriptPath;
  } catch (error) {
    console.error(`[Production Script] ❌ Error: ${error.message}`);
    return null;
  }
};

// Test the development script finding logic
const testDevelopmentScript = (mockApp) => {
  console.log(`\n🧪 Testing Development Mode`);
  console.log(`App path: ${mockApp.getAppPath()}`);

  const possiblePaths = [
    path.join(
      mockApp.getAppPath(),
      "src",
      "resources",
      "scripts",
      "linkedin_commenter.py"
    ),
    path.join(
      mockApp.getAppPath(),
      "resources",
      "scripts",
      "linkedin_commenter.py"
    ),
    path.join(mockApp.getAppPath(), "scripts", "linkedin_commenter.py"),
  ];

  console.log(`[Development Script] Looking for linkedin_commenter.py...`);

  for (const scriptPath of possiblePaths) {
    console.log(`[Development Script] Checking: ${scriptPath}`);
    if (fs.existsSync(scriptPath)) {
      console.log(`[Development Script] ✅ Found: ${scriptPath}`);
      return scriptPath;
    }
  }

  // Debug app directory contents
  try {
    const appContents = fs.readdirSync(mockApp.getAppPath());
    console.error(`[Development Script] App directory contents:`, appContents);
  } catch (error) {
    console.error(
      `[Development Script] Cannot read app directory:`,
      error.message
    );
  }

  console.error(
    `[Development Script] ❌ Development script not found. Searched:\n${possiblePaths
      .map((p) => `- ${p}`)
      .join("\n")}`
  );
  return null;
};

// Test bundled Python executable detection
const testBundledPython = (
  resourcesPath,
  platform = "darwin",
  arch = "arm64"
) => {
  console.log(`\n🧪 Testing Bundled Python Detection`);
  console.log(`Platform: ${platform}-${arch}`);
  console.log(`Resources path: ${resourcesPath || "undefined"}`);

  setResourcesPath(resourcesPath);

  try {
    if (!resourcesPath) {
      throw new Error("Resources path not available");
    }

    let executableName;
    let platformDir;

    switch (platform) {
      case "win32":
        platformDir = arch === "x64" ? "win-x64" : "win-ia32";
        executableName = "linkedin_commenter.exe";
        break;
      case "darwin":
        platformDir = arch === "arm64" ? "mac-arm64" : "mac-x64";
        executableName = "linkedin_commenter";
        break;
      case "linux":
        platformDir = arch === "x64" ? "linux-x64" : "linux-ia32";
        executableName = "linkedin_commenter";
        break;
      default:
        throw new Error(`Unsupported platform: ${platform}`);
    }

    const executablePath = path.join(
      resourcesPath,
      "python-executables",
      platformDir,
      executableName
    );

    console.log(`[Bundled Python] Expected path: ${executablePath}`);

    if (!fs.existsSync(executablePath)) {
      console.error(`[Bundled Python] ❌ Not found: ${executablePath}`);

      // Debug what's actually there
      const pythonDir = path.join(resourcesPath, "python-executables");
      if (fs.existsSync(pythonDir)) {
        const pythonContents = fs.readdirSync(pythonDir);
        console.log(`[Bundled Python] Python dir contents:`, pythonContents);
      }

      return false;
    }

    console.log(`[Bundled Python] ✅ Found: ${executablePath}`);
    return true;
  } catch (error) {
    console.error(`[Bundled Python] ❌ Error: ${error.message}`);
    return false;
  }
};

// Run tests
console.log("🔬 Testing Bundled Python Path Logic\n");
console.log("=".repeat(50));

// Test 1: Development mode (current directory)
console.log(`\n📁 Test 1: Development Mode (Current Directory)`);
const devApp = createMockApp(false);
testDevelopmentScript(devApp);

// Test 2: Production mode with built app resources
console.log(`\n📦 Test 2: Production Mode (Built App)`);
const builtAppResourcesPath = path.join(
  process.cwd(),
  "dist/mac-arm64/Junior Desktop.app/Contents/Resources"
);
testProductionScript(builtAppResourcesPath);
testBundledPython(builtAppResourcesPath);

// Test 3: Production mode with missing resources (error case)
console.log(`\n❌ Test 3: Production Mode (Missing Resources)`);
testProductionScript("/nonexistent/path");
testBundledPython("/nonexistent/path");

console.log(`\n✅ Test Summary:`);
console.log(`- Development mode: Should find script in src/resources/scripts/`);
console.log(`- Production mode: Should find script in Contents/Resources/`);
console.log(
  `- Production mode: Should find bundled Python in Contents/Resources/python-executables/`
);
console.log(`- Error handling: Should fail gracefully with clear messages`);
