/**
 * Manages modal dialogs in the application
 */
export class ModalManager {
  constructor() {
    this.modalOverlay = document.getElementById('modal-overlay');
    this.modalTitle = document.getElementById('modal-title');
    this.modalContent = document.getElementById('modal-content');
    this.modalCloseButton = document.getElementById('modal-close');

    this.setupEventListeners();
  }

  /**
   * Setup event listeners for the modal
   */
  setupEventListeners() {
    // Close modal when clicking the close button
    this.modalCloseButton.addEventListener('click', () => {
      this.closeModal();
    });

    // Close modal when clicking outside the modal
    this.modalOverlay.addEventListener('click', (event) => {
      if (event.target === this.modalOverlay) {
        this.closeModal();
      }
    });

    // Close modal when pressing ESC key
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && this.isModalOpen()) {
        this.closeModal();
      }
    });
  }

  /**
   * Show a modal with the specified title and content
   * @param {string} title - Modal title
   * @param {string|HTMLElement} content - Modal content (HTML string or element)
   * @param {Object} options - Additional options for the modal
   */
  showModal(title, content, options = {}) {
    // Set modal title
    this.modalTitle.textContent = title;

    // Set modal content
    if (typeof content === 'string') {
      this.modalContent.innerHTML = content;
    } else if (content instanceof HTMLElement) {
      this.modalContent.innerHTML = '';
      this.modalContent.appendChild(content);
    }

    // Apply custom classes if specified
    if (options.customClass) {
      this.modalContent.classList.add(options.customClass);
    }

    // Show the modal
    this.modalOverlay.classList.remove('hidden');

    // Return a promise that resolves when the modal is closed
    return new Promise((resolve) => {
      this._modalResolve = resolve;
    });
  }

  /**
   * Close the modal
   * @param {any} result - Result to pass to the promise resolve
   */
  closeModal(result) {
    // Hide the modal
    this.modalOverlay.classList.add('hidden');

    // Reset content
    this.modalContent.innerHTML = '';

    // Remove any custom classes
    this.modalContent.className = 'modal-content';

    // Resolve the promise if one exists
    if (this._modalResolve) {
      this._modalResolve(result);
      this._modalResolve = null;
    }
  }

  /**
   * Check if the modal is currently open
   * @returns {boolean} True if the modal is open
   */
  isModalOpen() {
    return !this.modalOverlay.classList.contains('hidden');
  }

  /**
   * Show a simple confirmation dialog
   * @param {string} message - Confirmation message
   * @param {string} title - Dialog title
   * @returns {Promise<boolean>} Promise resolving to true (confirm) or false (cancel)
   */
  async confirm(message, title = 'Confirmation') {
    const content = document.createElement('div');
    content.classList.add('confirm-dialog');

    // Add message
    const messageElement = document.createElement('p');
    messageElement.textContent = message;
    content.appendChild(messageElement);

    // Add buttons
    const buttonContainer = document.createElement('div');
    buttonContainer.classList.add('modal-actions');

    const cancelButton = document.createElement('button');
    cancelButton.textContent = 'Cancel';
    cancelButton.classList.add('btn');
    cancelButton.addEventListener('click', () => this.closeModal(false));

    const confirmButton = document.createElement('button');
    confirmButton.textContent = 'Confirm';
    confirmButton.classList.add('btn', 'btn-primary');
    confirmButton.addEventListener('click', () => this.closeModal(true));

    buttonContainer.appendChild(cancelButton);
    buttonContainer.appendChild(confirmButton);
    content.appendChild(buttonContainer);

    return this.showModal(title, content);
  }

  /**
   * Show an alert dialog
   * @param {string} message - Alert message
   * @param {string} title - Dialog title
   * @returns {Promise<void>} Promise resolving when the dialog is closed
   */
  async alert(message, title = 'Alert') {
    const content = document.createElement('div');
    content.classList.add('alert-dialog');

    // Add message
    const messageElement = document.createElement('p');
    messageElement.textContent = message;
    content.appendChild(messageElement);

    // Add button
    const buttonContainer = document.createElement('div');
    buttonContainer.classList.add('modal-actions');

    const okButton = document.createElement('button');
    okButton.textContent = 'OK';
    okButton.classList.add('btn', 'btn-primary');
    okButton.addEventListener('click', () => this.closeModal());

    buttonContainer.appendChild(okButton);
    content.appendChild(buttonContainer);

    return this.showModal(title, content);
  }
}
