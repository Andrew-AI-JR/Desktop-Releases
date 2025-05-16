const apiClient = require("../api/apiClient");

/**
 * Service for payment-related operations
 */
const paymentService = {
  /**
   * Create a Stripe customer for the current user
   * @returns {Promise<Object>} Success status
   */
  async createCustomer() {
    try {
      const response = await apiClient.post("/api/payments/create-customer");
      return response.data;
    } catch (error) {
      console.error(
        "Create customer error:",
        error.response?.data || error.message
      );
      throw {
        message: error.response?.data?.detail || "Failed to create customer",
        status: error.response?.status || 500,
      };
    }
  },

  /**
   * Create a subscription for the current user
   * @param {Object} subscriptionData - Subscription data with price_id
   * @returns {Promise<Object>} Subscription data
   */
  async createSubscription(subscriptionData) {
    try {
      const response = await apiClient.post(
        "/api/payments/create-subscription",
        subscriptionData
      );
      return response.data;
    } catch (error) {
      console.error(
        "Create subscription error:",
        error.response?.data || error.message
      );
      throw {
        message:
          error.response?.data?.detail || "Failed to create subscription",
        status: error.response?.status || 500,
      };
    }
  },
};

module.exports = paymentService;
