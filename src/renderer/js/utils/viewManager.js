/**
 * Manages view transitions in the application
 */
export class ViewManager {
  constructor() {
    this.views = Array.from(document.querySelectorAll(".view"));
    this.currentView = null;
  }

  /**
   * Show a specific view and hide all others
   * @param {string} viewId - ID of the view to show (without the '-view' suffix)
   * @returns {HTMLElement} The shown view element
   */
  showView(viewId) {
    if (!viewId.endsWith("-view")) {
      viewId = `${viewId}-view`;
    }

    const targetView = document.getElementById(viewId);

    if (!targetView) {
      console.error(`View not found: ${viewId}`);
      return null;
    }

    // Hide all views
    this.views.forEach((view) => view.classList.add("hidden"));

    // Show target view
    targetView.classList.remove("hidden");
    this.currentView = targetView;

    return targetView;
  }

  /**
   * Get the currently active view
   * @returns {HTMLElement} The current view element
   */
  getCurrentView() {
    return this.currentView;
  }

  /**
   * Get the ID of the currently active view
   * @returns {string} The current view ID (without the '-view' suffix)
   */
  getCurrentViewId() {
    if (!this.currentView) return null;

    const fullId = this.currentView.id;
    return fullId.replace("-view", "");
  }

  /**
   * Register a new view dynamically
   * @param {HTMLElement} viewElement - The view element to register
   */
  registerView(viewElement) {
    if (viewElement && !this.views.includes(viewElement)) {
      this.views.push(viewElement);
    }
  }
}
