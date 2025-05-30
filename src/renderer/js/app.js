import { AuthController } from './controllers/authController.js';
import { AutomationController } from './controllers/automationController.js';
import { ProfileController } from './controllers/profileController.js';
import { SettingsController } from './controllers/settingsController.js';
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

    this.profileController = new ProfileController(
      this.viewManager,
      this.modalManager
    );
    this.settingsController = new SettingsController(
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
    navLinks.forEach((link) => {
      link.addEventListener('click', (event) => {
        event.preventDefault();

        const viewName = link.getAttribute('data-view');
        if (viewName) {
          this.viewManager.showView(viewName);

          // Update active nav link
          navLinks.forEach((l) => l.classList.remove('active'));
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
        // Get user info
        const user = await this.authController.getCurrentUser();
        this.updateUserInfo(user);

        // Show dashboard
        this.viewManager.showView('dashboard');

        // Load initial data
        await this.loadInitialData();
      } else {
        // Show login view
        this.viewManager.showView('login');
      }
    } catch (error) {
      console.error('Error checking auth state:', error);
      this.viewManager.showView('login');
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

  /**
   * Load initial data for authenticated user
   */
  async loadInitialData() {
    try {
      // Load profile data
      this.profileController.loadProfileData();

      // Load subscription status
      this.settingsController.loadSubscriptionInfo();

      // Load custom prompts
      this.settingsController.loadPrompts();
    } catch (error) {
      console.error('Error loading initial data:', error);
    }
  }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  window.app = new App();
});
