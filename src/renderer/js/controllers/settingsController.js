export class SettingsController {
  constructor(viewManager, modalManager) {
    this.viewManager = viewManager;
    this.modalManager = modalManager;

    // Element references
    this.subscriptionInfo = document.getElementById("subscription-info");
    this.manageSubscriptionButton = document.getElementById(
      "manage-subscription"
    );
    this.promptsContainer = document.getElementById("prompts-container");
    this.addPromptButton = document.getElementById("add-prompt");

    // State
    this.subscription = null;
    this.prompts = [];

    // Setup event listeners
    this.setupEventListeners();
  }

  /**
   * Set up event listeners for settings-related elements
   */
  setupEventListeners() {
    this.manageSubscriptionButton.addEventListener(
      "click",
      this.showManageSubscriptionModal.bind(this)
    );
    this.addPromptButton.addEventListener(
      "click",
      this.showAddPromptModal.bind(this)
    );

    // Listen for user login event to load settings data
    document.addEventListener("user:loggedin", () => {
      this.loadSubscriptionInfo();
      this.loadPrompts();
    });
  }

  /**
   * Load subscription information
   */
  async loadSubscriptionInfo() {
    try {
      // In a real implementation, you would fetch subscription data from API
      // For demo purposes, we'll simulate a subscription
      this.subscription = {
        plan: "Basic",
        status: "active",
        current_period_end: new Date(
          Date.now() + 30 * 24 * 60 * 60 * 1000
        ).toISOString(), // 30 days from now
      };

      this.renderSubscriptionInfo();
    } catch (error) {
      console.error("Error loading subscription info:", error);
      this.renderSubscriptionInfo();
    }
  }

  /**
   * Render subscription information
   */
  renderSubscriptionInfo() {
    if (!this.subscription) {
      this.subscriptionInfo.innerHTML = `
        <div class="subscription-empty">
          <p>You don't have an active subscription.</p>
          <p>Subscribe to unlock all features!</p>
        </div>
      `;
      return;
    }

    const endDate = new Date(
      this.subscription.current_period_end
    ).toLocaleDateString();

    this.subscriptionInfo.innerHTML = `
      <div class="subscription-details">
        <div class="subscription-plan">
          <span class="label">Plan:</span>
          <span class="value">${this.subscription.plan}</span>
        </div>
        <div class="subscription-status">
          <span class="label">Status:</span>
          <span class="value status-${this.subscription.status.toLowerCase()}">${
      this.subscription.status
    }</span>
        </div>
        <div class="subscription-period">
          <span class="label">Renews:</span>
          <span class="value">${endDate}</span>
        </div>
      </div>
    `;
  }

  /**
   * Show modal for managing subscription
   */
  async showManageSubscriptionModal() {
    const content = document.createElement("div");
    content.classList.add("subscription-modal");

    if (!this.subscription || this.subscription.status !== "active") {
      // Show subscription plans
      content.innerHTML = `
        <div class="subscription-plans">
          <div class="plan-option">
            <h4>Basic Plan</h4>
            <div class="plan-price">$9.99 / month</div>
            <ul class="plan-features">
              <li>Generate up to 50 comments per month</li>
              <li>Basic automation tools</li>
              <li>Standard support</li>
            </ul>
            <button class="btn btn-primary select-plan" data-plan-id="price_basic">Select Plan</button>
          </div>
          <div class="plan-option highlighted">
            <h4>Pro Plan</h4>
            <div class="plan-price">$19.99 / month</div>
            <ul class="plan-features">
              <li>Generate unlimited comments</li>
              <li>Advanced automation tools</li>
              <li>Priority support</li>
              <li>Custom prompt management</li>
            </ul>
            <button class="btn btn-primary select-plan" data-plan-id="price_pro">Select Plan</button>
          </div>
        </div>
      `;
    } else {
      // Show current subscription details
      const endDate = new Date(
        this.subscription.current_period_end
      ).toLocaleDateString();

      content.innerHTML = `
        <div class="current-subscription">
          <div class="subscription-details">
            <div class="detail-row">
              <span class="label">Current Plan:</span>
              <span class="value">${this.subscription.plan}</span>
            </div>
            <div class="detail-row">
              <span class="label">Status:</span>
              <span class="value status-${this.subscription.status.toLowerCase()}">${
        this.subscription.status
      }</span>
            </div>
            <div class="detail-row">
              <span class="label">Current Period Ends:</span>
              <span class="value">${endDate}</span>
            </div>
          </div>
          <div class="subscription-actions">
            <button class="btn btn-danger cancel-subscription">Cancel Subscription</button>
            <button class="btn btn-secondary upgrade-subscription">Upgrade Plan</button>
          </div>
        </div>
      `;
    }

    // Show the modal
    this.modalManager.showModal("Manage Subscription", content);

    // Handle button clicks
    if (!this.subscription || this.subscription.status !== "active") {
      const planButtons = content.querySelectorAll(".select-plan");

      planButtons.forEach((button) => {
        button.addEventListener("click", async () => {
          const planId = button.getAttribute("data-plan-id");
          await this.createSubscription(planId);
        });
      });
    } else {
      const cancelButton = content.querySelector(".cancel-subscription");
      const upgradeButton = content.querySelector(".upgrade-subscription");

      if (cancelButton) {
        cancelButton.addEventListener("click", async () => {
          const confirmed = await this.modalManager.confirm(
            "Are you sure you want to cancel your subscription? You will lose access to premium features at the end of your current billing period."
          );

          if (confirmed) {
            await this.cancelSubscription();
          }
        });
      }

      if (upgradeButton) {
        upgradeButton.addEventListener("click", () => {
          this.showUpgradePlanOptions();
        });
      }
    }
  }

  /**
   * Create a new subscription
   * @param {string} priceId - Stripe price ID
   */
  async createSubscription(priceId) {
    try {
      // Show loading state
      this.modalManager.showModal(
        "Creating Subscription",
        '<div class="loading-indicator">Processing your subscription...</div>'
      );

      // Create Stripe customer if needed
      await window.api.payments.createCustomer();

      // Create subscription
      const result = await window.api.payments.createSubscription({
        price_id: priceId,
      });

      if (result) {
        // Update local subscription data
        this.subscription = result;
        this.renderSubscriptionInfo();

        // Show success message
        this.modalManager.alert(
          "Subscription created successfully!",
          "Success"
        );
      }
    } catch (error) {
      console.error("Create subscription error:", error);
      this.modalManager.alert(
        error.message || "Failed to create subscription. Please try again.",
        "Subscription Error"
      );
    }
  }

  /**
   * Cancel the current subscription
   */
  async cancelSubscription() {
    try {
      // In a real implementation, this would call the API to cancel the subscription
      // For demo purposes, we'll just update the local state

      this.subscription.status = "canceling";
      this.renderSubscriptionInfo();

      // Show success message
      this.modalManager.alert(
        "Your subscription has been cancelled. You will have access until the end of your current billing period.",
        "Subscription Cancelled"
      );

      // Close the modal
      this.modalManager.closeModal();
    } catch (error) {
      console.error("Cancel subscription error:", error);
      this.modalManager.alert(
        error.message || "Failed to cancel subscription. Please try again.",
        "Subscription Error"
      );
    }
  }

  /**
   * Show plan upgrade options
   */
  showUpgradePlanOptions() {
    // In a real implementation, this would show available upgrade options
    // For demo purposes, we'll just show a message
    this.modalManager.alert(
      "Upgrade options are not available in this demo.",
      "Upgrade Options"
    );
  }

  /**
   * Load user prompts
   */
  async loadPrompts() {
    try {
      // Get all prompts from API
      const prompts = await window.api.prompts.list({});
      this.prompts = prompts || [];

      this.renderPromptsContainer();
    } catch (error) {
      console.error("Error loading prompts:", error);
      this.renderPromptsContainer();
    }
  }

  /**
   * Render the prompts container
   */
  renderPromptsContainer() {
    // Clear current content
    this.promptsContainer.innerHTML = "";

    if (!this.prompts || this.prompts.length === 0) {
      this.promptsContainer.innerHTML =
        '<p class="empty-state">No custom prompts created</p>';
      return;
    }

    // Create a list of prompts
    const promptList = document.createElement("div");
    promptList.classList.add("prompt-list");

    for (const prompt of this.prompts) {
      const promptItem = document.createElement("div");
      promptItem.classList.add("prompt-item");

      promptItem.innerHTML = `
        <div class="prompt-header">
          <h4 class="prompt-name">${prompt.name}</h4>
          <div class="prompt-meta">
            <span class="prompt-type">${prompt.prompt_type}</span>
            ${
              prompt.scope
                ? `<span class="prompt-scope">${prompt.scope}</span>`
                : ""
            }
          </div>
        </div>
        <div class="prompt-controls">
          <button class="btn btn-small edit-prompt" data-prompt-id="${
            prompt.id
          }">Edit</button>
          <button class="btn btn-small btn-danger delete-prompt" data-prompt-id="${
            prompt.id
          }">Delete</button>
        </div>
      `;

      // Add event listeners to buttons
      const editButton = promptItem.querySelector(".edit-prompt");
      editButton.addEventListener("click", () => {
        this.showEditPromptModal(prompt);
      });

      const deleteButton = promptItem.querySelector(".delete-prompt");
      deleteButton.addEventListener("click", () => {
        this.deletePrompt(prompt.id);
      });

      promptList.appendChild(promptItem);
    }

    this.promptsContainer.appendChild(promptList);
  }

  /**
   * Show modal for adding a new prompt
   */
  async showAddPromptModal() {
    const formContainer = document.createElement("div");
    formContainer.innerHTML = `
      <form id="prompt-form" class="prompt-form">
        <div class="form-group">
          <label for="prompt-name">Name</label>
          <input type="text" id="prompt-name" name="name" required>
        </div>
        <div class="form-group">
          <label for="prompt-type">Type</label>
          <select id="prompt-type" name="promptType" required>
            <option value="comment">Comment</option>
            <option value="response">Response</option>
            <option value="message">Message</option>
          </select>
        </div>
        <div class="form-group">
          <label for="prompt-scope">Scope (Optional)</label>
          <input type="text" id="prompt-scope" name="scope" placeholder="e.g. professional, casual, etc.">
        </div>
        <div class="form-group">
          <label for="prompt-text">Prompt Text</label>
          <textarea id="prompt-text" name="text" rows="6" required placeholder="Enter your prompt text here"></textarea>
        </div>
        <div class="form-group">
          <label>
            <input type="checkbox" id="prompt-default" name="isUserDefault">
            Set as default for this type
          </label>
        </div>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary">Save Prompt</button>
        </div>
      </form>
    `;

    // Show the modal
    this.modalManager.showModal("Add Custom Prompt", formContainer);

    // Handle form submission
    const form = formContainer.querySelector("#prompt-form");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const name = form.name.value.trim();
      const promptType = form.promptType.value;
      const scope = form.scope.value.trim() || null;
      const text = form.text.value.trim();
      const isUserDefault = form.isUserDefault.checked;

      if (!name || !promptType || !text) {
        this.modalManager.alert(
          "Please fill out all required fields.",
          "Validation Error"
        );
        return;
      }

      try {
        // Show loading state
        const submitButton = form.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        submitButton.textContent = "Saving...";

        // Create prompt
        const promptData = {
          name,
          prompt_type: promptType,
          scope,
          text,
          is_user_default: isUserDefault,
        };

        const result = await window.api.prompts.create(promptData);

        if (result) {
          // Close the modal
          this.modalManager.closeModal();

          // Add to prompts list
          this.prompts.push(result);
          this.renderPromptsContainer();

          // Show success message
          this.modalManager.alert("Prompt created successfully!", "Success");
        }
      } catch (error) {
        console.error("Create prompt error:", error);
        this.modalManager.alert(
          error.message || "Failed to create prompt. Please try again.",
          "Prompt Error"
        );

        // Reset button
        const submitButton = form.querySelector('button[type="submit"]');
        submitButton.disabled = false;
        submitButton.textContent = "Save Prompt";
      }
    });
  }

  /**
   * Show modal for editing an existing prompt
   * @param {Object} prompt - Prompt data
   */
  async showEditPromptModal(prompt) {
    const formContainer = document.createElement("div");
    formContainer.innerHTML = `
      <form id="prompt-edit-form" class="prompt-form">
        <div class="form-group">
          <label for="prompt-name">Name</label>
          <input type="text" id="prompt-name" name="name" value="${
            prompt.name
          }" required>
        </div>
        <div class="form-group">
          <label for="prompt-type">Type</label>
          <select id="prompt-type" name="promptType" required>
            <option value="comment" ${
              prompt.prompt_type === "comment" ? "selected" : ""
            }>Comment</option>
            <option value="response" ${
              prompt.prompt_type === "response" ? "selected" : ""
            }>Response</option>
            <option value="message" ${
              prompt.prompt_type === "message" ? "selected" : ""
            }>Message</option>
          </select>
        </div>
        <div class="form-group">
          <label for="prompt-scope">Scope (Optional)</label>
          <input type="text" id="prompt-scope" name="scope" placeholder="e.g. professional, casual, etc." value="${
            prompt.scope || ""
          }">
        </div>
        <div class="form-group">
          <label for="prompt-text">Prompt Text</label>
          <textarea id="prompt-text" name="text" rows="6" required>${
            prompt.text
          }</textarea>
        </div>
        <div class="form-group">
          <label>
            <input type="checkbox" id="prompt-default" name="isUserDefault" ${
              prompt.is_user_default ? "checked" : ""
            }>
            Set as default for this type
          </label>
        </div>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary">Update Prompt</button>
        </div>
      </form>
    `;

    // Show the modal
    this.modalManager.showModal("Edit Custom Prompt", formContainer);

    // Handle form submission
    const form = formContainer.querySelector("#prompt-edit-form");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const name = form.name.value.trim();
      const promptType = form.promptType.value;
      const scope = form.scope.value.trim() || null;
      const text = form.text.value.trim();
      const isUserDefault = form.isUserDefault.checked;

      if (!name || !promptType || !text) {
        this.modalManager.alert(
          "Please fill out all required fields.",
          "Validation Error"
        );
        return;
      }

      try {
        // Show loading state
        const submitButton = form.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        submitButton.textContent = "Updating...";

        // Update prompt
        const promptData = {
          name,
          prompt_type: promptType,
          scope,
          text,
          is_user_default: isUserDefault,
        };

        const result = await window.api.prompts.update(prompt.id, promptData);

        if (result) {
          // Close the modal
          this.modalManager.closeModal();

          // Update in prompts list
          const index = this.prompts.findIndex((p) => p.id === prompt.id);
          if (index !== -1) {
            this.prompts[index] = result;
          }
          this.renderPromptsContainer();

          // Show success message
          this.modalManager.alert("Prompt updated successfully!", "Success");
        }
      } catch (error) {
        console.error("Update prompt error:", error);
        this.modalManager.alert(
          error.message || "Failed to update prompt. Please try again.",
          "Prompt Error"
        );

        // Reset button
        const submitButton = form.querySelector('button[type="submit"]');
        submitButton.disabled = false;
        submitButton.textContent = "Update Prompt";
      }
    });
  }

  /**
   * Delete a prompt
   * @param {number} promptId - Prompt ID
   */
  async deletePrompt(promptId) {
    try {
      const confirmed = await this.modalManager.confirm(
        "Are you sure you want to delete this prompt?"
      );

      if (confirmed) {
        await window.api.prompts.delete(promptId);

        // Remove from local list
        this.prompts = this.prompts.filter((prompt) => prompt.id !== promptId);
        this.renderPromptsContainer();

        // Show success message
        this.modalManager.alert("Prompt deleted successfully!", "Success");
      }
    } catch (error) {
      console.error("Delete prompt error:", error);
      this.modalManager.alert(
        error.message || "Failed to delete prompt. Please try again.",
        "Prompt Error"
      );
    }
  }
}
