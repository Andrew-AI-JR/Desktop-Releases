/**
 * Test script to validate error serialization works correctly
 */

// Simulate the error handling logic
function testErrorSerialization() {
  console.log("Testing error serialization...\n");

  const testErrors = [
    new Error("Simple error message"),
    "String error",
    { message: "Object with message", code: "ERR_TEST", status: 400 },
    { code: "ENOENT", errno: -2, syscall: "spawn", path: "/nonexistent" },
    { random: "object", without: "message" },
    null,
    undefined,
  ];

  testErrors.forEach((error, index) => {
    console.log(`Test ${index + 1}:`, typeof error, error);

    // Robust error message extraction (copy from automationHandlers.js)
    let errorMessage = "Failed to run automation";

    if (typeof error === "string") {
      errorMessage = error;
    } else if (error && typeof error.message === "string") {
      errorMessage = error.message;
    } else if (error && typeof error === "object") {
      // Try to extract meaningful information from the error object
      const parts = [];
      if (error.message) parts.push(error.message);
      if (error.code) parts.push(`(${error.code})`);
      if (error.errno) parts.push(`errno: ${error.errno}`);
      if (error.syscall) parts.push(`syscall: ${error.syscall}`);
      if (error.path) parts.push(`path: ${error.path}`);

      errorMessage =
        parts.length > 0
          ? parts.join(" ")
          : error.toString !== Object.prototype.toString
          ? error.toString()
          : "Unknown error occurred";
    }

    console.log(`  -> Result: "${errorMessage}"`);
    console.log("");
  });
}

if (require.main === module) {
  testErrorSerialization();
}

module.exports = { testErrorSerialization };
