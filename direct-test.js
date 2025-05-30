const path = require("path");
const fs = require("fs");

console.log("=== Direct Python Bundle Test ===");

const appBundle = path.join(__dirname, "dist/mac-arm64/Junior Desktop.app");
const resourcesPath = path.join(appBundle, "Contents/Resources");
const pythonDir = path.join(resourcesPath, "python-executables");
const executablePath = path.join(pythonDir, "mac-arm64", "linkedin_commenter");

console.log("App bundle:", appBundle);
console.log("Resources path:", resourcesPath);
console.log("Python dir:", pythonDir);
console.log("Executable path:", executablePath);

console.log("\n=== File Checks ===");
console.log("App bundle exists:", fs.existsSync(appBundle));
console.log("Resources path exists:", fs.existsSync(resourcesPath));
console.log("Python dir exists:", fs.existsSync(pythonDir));
console.log("Executable exists:", fs.existsSync(executablePath));

if (fs.existsSync(resourcesPath)) {
  const contents = fs
    .readdirSync(resourcesPath)
    .filter((item) => item.includes("python") || item.includes("linkedin"));
  console.log("Relevant resources:", contents);
}

if (fs.existsSync(pythonDir)) {
  console.log("Python dir contents:", fs.readdirSync(pythonDir));

  const macDir = path.join(pythonDir, "mac-arm64");
  if (fs.existsSync(macDir)) {
    console.log("Mac ARM64 contents:", fs.readdirSync(macDir));
  }
}

if (fs.existsSync(executablePath)) {
  const stats = fs.statSync(executablePath);
  console.log("\n=== Executable Info ===");
  console.log("Size:", stats.size, "bytes");
  console.log("Is file:", stats.isFile());
  console.log("Permissions:", stats.mode.toString(8));
  console.log("Is executable:", !!(stats.mode & parseInt("111", 8)));
}
