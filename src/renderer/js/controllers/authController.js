export class AuthController {
  constructor(viewManager, modalManager) {
    this.viewManager = viewManager;
    this.modalManager = modalManager;

    // Element references
    this.loginForm = document.getElementById('login-form');
    this.registerForm = document.getElementById('register-form');
    this.showRegisterLink = document.getElementById('show-register');
    this.showLoginLink = document.getElementById('show-login');
    this.loginOverlay = document.getElementById('login-overlay');
    this.registerOverlay = document.getElementById('register-overlay');
    this.mainApp = document.getElementById('main-app');
    this.userProfile = document.getElementById('user-profile');

    // Bind event handlers
    this.setupEventListeners();
  }

  /**
   * Set up event listeners for auth-related elements
   */
  setupEventListeners() {
    // Switch between login and register views
    this.showRegisterLink.addEventListener('click', e => {
      e.preventDefault();
      this.showRegisterOverlay();
    });

    this.showLoginLink.addEventListener('click', e => {
      e.preventDefault();
      this.showLoginOverlay();
    });

    // Handle form submissions
    this.loginForm.addEventListener('submit', this.handleLogin.bind(this));
    this.registerForm.addEventListener(
      'submit',
      this.handleRegister.bind(this)
    );

    // Setup logout functionality - will be bound when user is logged in
  }

  /**
   * Setup logout functionality after login
   */
  setupLogoutEventListener() {
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', this.handleLogout.bind(this));
    }
  }

  /**
   * Show login overlay
   */
  showLoginOverlay() {
    this.loginOverlay.classList.remove('hidden');
    this.registerOverlay.classList.add('hidden');
    this.clearErrors();
  }

  /**
   * Show register overlay
   */
  showRegisterOverlay() {
    this.registerOverlay.classList.remove('hidden');
    this.loginOverlay.classList.add('hidden');
    this.clearErrors();
  }

  /**
   * Show main app (user is authenticated)
   */
  showMainApp() {
    this.loginOverlay.classList.add('hidden');
    this.registerOverlay.classList.add('hidden');
    this.mainApp.classList.remove('hidden');
  }

  /**
   * Clear all error messages
   */
  clearErrors() {
    const loginError = document.getElementById('login-error');
    const registerError = document.getElementById('register-error');
    if (loginError) {
      loginError.classList.add('hidden');
      loginError.textContent = '';
    }
    if (registerError) {
      registerError.classList.add('hidden');
      registerError.textContent = '';
    }
  }

  /**
   * Display user-friendly error message
   * @param {string} elementId - ID of error element
   * @param {string} userMessage - User-friendly message
   * @param {Error} originalError - Original error for console logging
   */
  showError(elementId, userMessage, originalError = null) {
    const errorElement = document.getElementById(elementId);
    if (errorElement) {
      errorElement.textContent = userMessage;
      errorElement.classList.remove('hidden');
    }

    // Log detailed error to console for debugging
    if (originalError) {
      console.error('Detailed error:', originalError);
    }
  }

  /**
   * Handle login form submission
   * @param {Event} event - Form submit event
   */
  async handleLogin(event) {
    event.preventDefault();
    this.clearErrors();

    const email = this.loginForm.email.value.trim();
    const password = this.loginForm.password.value;

    if (!email || !password) {
      this.showError('login-error', 'Please enter both email and password.');
      return;
    }

    this.setFormLoading(this.loginForm, true);

    try {
      const response = await window.api.auth.login({ email, password });

      if (!response.success) {
        console.error('Login failed:', response.error);
        let userMessage = 'Login failed. Please try again.';

        if (response.error.status === 401) {
          userMessage = 'Invalid email or password.';
        } else if (response.error.status === 429) {
          userMessage = 'Too many login attempts. Please try again later.';
        } else if (response.error.status >= 500) {
          userMessage = 'Server error. Please try again later.';
        } else if (
          response.error.message &&
          response.error.message.includes('network')
        ) {
          userMessage =
            'Unable to connect to server. Please check your internet connection.';
        }

        this.showError('login-error', userMessage, response.error);
        return;
      }

      // Load user data and show main app
      await this.loadUserData();
      this.showMainApp();
      this.setupLogoutEventListener();

      // Trigger loading of initial data
      this.loadInitialData();
    } catch (error) {
      console.error('Login error:', error);
      this.showError(
        'login-error',
        'An unexpected error occurred. Please try again.',
        error
      );
    } finally {
      this.setFormLoading(this.loginForm, false);
    }
  }

  /**
   * Handle register form submission
   * @param {Event} event - Form submit event
   */
  async handleRegister(event) {
    event.preventDefault();
    this.clearErrors();

    const email = this.registerForm.email.value.trim();
    const password = this.registerForm.password.value;
    const confirmPassword = this.registerForm.confirmPassword.value;

    if (!email || !password || !confirmPassword) {
      this.showError('register-error', 'Please fill out all fields.');
      return;
    }

    if (password !== confirmPassword) {
      this.showError('register-error', 'Passwords do not match.');
      return;
    }

    this.setFormLoading(this.registerForm, true);

    try {
      const response = await window.api.auth.register({ email, password });

      if (!response.success) {
        let userMessage = 'Registration failed. Please try again.';

        if (response.error.status === 409) {
          userMessage =
            'This email is already registered. Please use a different email or try logging in.';
        } else if (response.error.status === 422) {
          userMessage = 'Invalid email or password format.';
        } else if (response.error.status === 429) {
          userMessage =
            'Too many registration attempts. Please try again later.';
        } else if (response.error.status >= 500) {
          userMessage = 'Server error. Please try again later.';
        } else if (
          response.error.message &&
          response.error.message.includes('network')
        ) {
          userMessage =
            'Unable to connect to server. Please check your internet connection.';
        }

        this.showError('register-error', userMessage, response.error);
        return;
      }

      // Clear form and show success
      this.registerForm.reset();
      this.showLoginOverlay();

      // Show success in login form
      setTimeout(() => {
        this.showError(
          'login-error',
          'Registration successful! Please log in with your credentials.'
        );
        const loginErrorElement = document.getElementById('login-error');
        if (loginErrorElement) {
          loginErrorElement.style.backgroundColor = '#d4edda';
          loginErrorElement.style.color = '#155724';
        }
      }, 100);
    } catch (error) {
      console.error('Registration error:', error);
      this.showError(
        'register-error',
        'An unexpected error occurred. Please try again.',
        error
      );
    } finally {
      this.setFormLoading(this.registerForm, false);
    }
  }

  /**
   * Load user data from API and update UI
   */
  async loadUserData() {
    const response = await window.api.auth.getUser();
    if (!response.success) {
      console.error('Load user data error:', response.error);
      throw response.error;
    }
    this.updateUserInfo(response.data);
    return response.data;
  }

  /**
   * Handle logout button click
   */
  async handleLogout() {
    const response = await window.api.auth.clearTokens();
    if (!response.success) {
      console.error('Logout error:', response.error);
      this.showError(
        'login-error',
        'An error occurred during logout. Please try again.'
      );
      return;
    }

    // Reset UI to login overlay
    this.showLoginOverlay();

    // Clear user info
    const userNameElement = document.querySelector('.user-name');
    if (userNameElement) {
      userNameElement.textContent = 'Guest';
    }

    // Clear any form data
    this.loginForm.reset();
    this.registerForm.reset();
    this.clearErrors();
  }

  /**
   * Get the current authenticated user
   * @returns {Promise<Object>} User data
   */
  async getCurrentUser() {
    const response = await window.api.auth.getUser();
    if (!response.success) {
      console.error('Get user error:', response.error);
      throw response.error;
    }
    return response.data;
  }

  /**
   * Check if a user is currently logged in
   * @returns {Promise<boolean>} True if logged in
   */
  async isLoggedIn() {
    try {
      const tokenResponse = await window.api.auth.getAccessToken();
      if (!tokenResponse.success || !tokenResponse.data) return false;

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
    // Update user name in header
    const userNameElement = document.querySelector('.user-name');
    if (userNameElement && user.email) {
      userNameElement.textContent = user.email.split('@')[0]; // Display username part of email
    }

    // Update subscription status if element exists
    const subscriptionElement = document.querySelector('.subscription-status');
    if (subscriptionElement && user.is_active !== undefined) {
      subscriptionElement.textContent = user.is_active ? 'Active' : 'Inactive';
      subscriptionElement.className = `subscription-status ${
        user.is_active ? 'active' : 'inactive'
      }`;
    }

    // Update full email if element exists
    const emailElement = document.querySelector('.user-email');
    if (emailElement && user.email) {
      emailElement.textContent = user.email;
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
      submitButton.textContent = 'Loading...';
    } else {
      submitButton.disabled = false;
      submitButton.textContent =
        form.id === 'login-form' ? 'Login' : 'Register';
    }
  }

  /**
   * Trigger loading of initial data after login
   */
  loadInitialData() {
    // Dispatch custom event for other controllers to listen to
    const event = new CustomEvent('user:loggedin');
    document.dispatchEvent(event);
  }
}
