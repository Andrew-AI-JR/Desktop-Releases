import { AuthController } from './controllers/authController.js';
import { AutomationController } from './controllers/automationController.js';

import { ViewManager } from './utils/viewManager.js';
import { ModalManager } from './utils/modalManager.js';

/**
 * Main application class
 */
class App {
  constructor() {
    this.viewManager = new ViewManager();
    this.modalManager = new ModalManager();

    // Initialize controllers
    this.authController = new AuthController(
      this.viewManager,
      this.modalManager
    );
    this.automationController = new AutomationController(
      this.viewManager,
      this.modalManager
    );

    // Setup navigation
    this.setupNavigation();

    // Check auth state and show appropriate view
    this.checkAuthState();
  }

  /**
   * Setup navigation between views
   */
  setupNavigation() {
    const navLinks = document.querySelectorAll('.main-nav a');
    console.log('Setting up navigation links:', navLinks);
    navLinks.forEach(link => {
      link.addEventListener('click', event => {
        event.preventDefault();

        const viewName = link.getAttribute('data-view');
        if (viewName) {
          this.viewManager.showView(viewName);

          // Update active nav link
          navLinks.forEach(l => l.classList.remove('active'));
          link.classList.add('active');
        }
      });
    });
  }

  /**
   * Check authentication state and show appropriate view
   */
  async checkAuthState() {
    try {
      // Check if user is logged in
      const isLoggedIn = await this.authController.isLoggedIn();

      if (isLoggedIn) {
        // Load user data and show main app
        await this.authController.loadUserData();
        this.authController.showMainApp();
        this.authController.setupLogoutEventListener();
      } else {
        // Show login overlay
        this.authController.showLoginOverlay();
      }
    } catch (error) {
      console.error('Error checking auth state:', error);
      this.authController.showLoginOverlay();
    }
  }

  /**
   * Update user information in UI
   * @param {Object} user - User data
   */
  updateUserInfo(user) {
    const userNameElement = document.querySelector('.user-name');
    if (userNameElement && user.email) {
      userNameElement.textContent = user.email.split('@')[0]; // Display username part of email
    }
  }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  window.app = new App();
});
