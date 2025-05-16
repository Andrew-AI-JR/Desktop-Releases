const paymentService = require("../../services/payments/paymentService");

/**
 * Handlers for payment-related IPC calls
 */
module.exports = {
  /**
   * Create a Stripe customer for the current user
   * @param {Electron.IpcMainInvokeEvent} event
   * @returns {Promise<Object>} Success status
   */
  createCustomer: async (event) => {
    try {
      return await paymentService.createCustomer();
    } catch (error) {
      console.error("Create customer error:", error);
      throw {
        message: error.message || "Failed to create customer",
        status: error.status || 500,
      };
    }
  },

  /**
   * Create a subscription for the current user
   * @param {Electron.IpcMainInvokeEvent} event
   * @param {Object} subscriptionData - Subscription data with price_id
   * @returns {Promise<Object>} Subscription data
   */
  createSubscription: async (event, subscriptionData) => {
    try {
      return await paymentService.createSubscription(subscriptionData);
    } catch (error) {
      console.error("Create subscription error:", error);
      throw {
        message: error.message || "Failed to create subscription",
        status: error.status || 500,
      };
    }
  },
};
