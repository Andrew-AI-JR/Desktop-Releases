export class AuthController {
  constructor(viewManager, modalManager) {
    this.viewManager = viewManager;
    this.modalManager = modalManager;

    // Element references
    this.loginForm = document.getElementById("login-form");
    this.registerForm = document.getElementById("register-form");
    this.showRegisterLink = document.getElementById("show-register");
    this.showLoginLink = document.getElementById("show-login");
    this.logoutButton = document.getElementById("logout");

    // Bind event handlers
    this.setupEventListeners();
  }

  /**
   * Set up event listeners for auth-related elements
   */
  setupEventListeners() {
    // Switch between login and register views
    this.showRegisterLink.addEventListener("click", (e) => {
      e.preventDefault();
      this.viewManager.showView("register");
    });

    this.showLoginLink.addEventListener("click", (e) => {
      e.preventDefault();
      this.viewManager.showView("login");
    });

    // Handle form submissions
    this.loginForm.addEventListener("submit", this.handleLogin.bind(this));
    this.registerForm.addEventListener(
      "submit",
      this.handleRegister.bind(this)
    );

    // Handle logout
    this.logoutButton.addEventListener("click", this.handleLogout.bind(this));
  }

  /**
   * Handle login form submission
   * @param {Event} event - Form submit event
   */
  async handleLogin(event) {
    event.preventDefault();

    const email = this.loginForm.email.value.trim();
    const password = this.loginForm.password.value;

    // Simple validation
    if (!email || !password) {
      this.modalManager.alert(
        "Please enter both email and password.",
        "Login Error"
      );
      return;
    }

    try {
      // Show loading state
      this.setFormLoading(this.loginForm, true);

      // Call API to login
      const result = await window.api.auth.login({ email, password });

      if (result) {
        // Clear form
        this.loginForm.reset();

        // Get user info
        const user = await this.getCurrentUser();

        // Update UI with user info
        this.updateUserInfo(user);

        // Switch to dashboard view
        this.viewManager.showView("dashboard");

        // Load initial data
        this.loadInitialData();
      }
    } catch (error) {
      console.error("Login error:", error);
      this.modalManager.alert(
        error.message || "Login failed. Please try again.",
        "Login Error"
      );
    } finally {
      // Remove loading state
      this.setFormLoading(this.loginForm, false);
    }
  }

  /**
   * Handle register form submission
   * @param {Event} event - Form submit event
   */
  async handleRegister(event) {
    event.preventDefault();

    const email = this.registerForm.email.value.trim();
    const password = this.registerForm.password.value;
    const confirmPassword = this.registerForm.confirmPassword.value;

    // Simple validation
    if (!email || !password || !confirmPassword) {
      this.modalManager.alert(
        "Please fill out all fields.",
        "Registration Error"
      );
      return;
    }

    if (password !== confirmPassword) {
      this.modalManager.alert("Passwords do not match.", "Registration Error");
      return;
    }

    try {
      // Show loading state
      this.setFormLoading(this.registerForm, true);

      // Call API to register
      const result = await window.api.auth.register({ email, password });

      if (result) {
        // Clear form
        this.registerForm.reset();

        // Show success message and redirect to login
        await this.modalManager.alert(
          "Registration successful! Please log in.",
          "Success"
        );
        this.viewManager.showView("login");
      }
    } catch (error) {
      console.error("Registration error:", error);
      this.modalManager.alert(
        error.message || "Registration failed. Please try again.",
        "Registration Error"
      );
    } finally {
      // Remove loading state
      this.setFormLoading(this.registerForm, false);
    }
  }

  /**
   * Handle logout button click
   */
  async handleLogout() {
    const confirmed = await this.modalManager.confirm(
      "Are you sure you want to log out?"
    );

    if (confirmed) {
      try {
        // Call API to logout
        await window.api.auth.logout();

        // Reset UI to login view
        this.viewManager.showView("login");
        document.querySelector(".user-name").textContent = "Guest";
      } catch (error) {
        console.error("Logout error:", error);
        this.modalManager.alert(
          "An error occurred during logout.",
          "Logout Error"
        );
      }
    }
  }

  /**
   * Get the current authenticated user
   * @returns {Promise<Object>} User data
   */
  async getCurrentUser() {
    try {
      return await window.api.auth.getUser();
    } catch (error) {
      console.error("Get user error:", error);
      throw error;
    }
  }

  /**
   * Check if a user is currently logged in
   * @returns {Promise<boolean>} True if logged in
   */
  async isLoggedIn() {
    try {
      const user = await this.getCurrentUser();
      return !!(user && user.id);
    } catch (error) {
      return false;
    }
  }

  /**
   * Update user information in UI
   * @param {Object} user - User data
   */
  updateUserInfo(user) {
    const userNameElement = document.querySelector(".user-name");
    if (userNameElement && user.email) {
      userNameElement.textContent = user.email.split("@")[0]; // Display username part of email
    }
  }

  /**
   * Set loading state on a form
   * @param {HTMLElement} form - Form element
   * @param {boolean} isLoading - Whether the form is in loading state
   */
  setFormLoading(form, isLoading) {
    const submitButton = form.querySelector('button[type="submit"]');

    if (isLoading) {
      submitButton.disabled = true;
      submitButton.textContent = "Loading...";
    } else {
      submitButton.disabled = false;
      submitButton.textContent =
        form.id === "login-form" ? "Login" : "Register";
    }
  }

  /**
   * Trigger loading of initial data after login
   */
  loadInitialData() {
    // Dispatch custom event for other controllers to listen to
    const event = new CustomEvent("user:loggedin");
    document.dispatchEvent(event);
  }
}
