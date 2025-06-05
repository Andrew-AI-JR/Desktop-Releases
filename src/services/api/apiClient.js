const { app } = require('electron');
const path = require('path');
const axios = require('axios');
const tokenManager = require('../auth/tokenManager');
require('dotenv').config({
  path: app.isPackaged
    ? path.join(process.resourcesPath, '.env')
    : path.resolve(process.cwd(), '.env'),
});

// Create base axios instance
const apiClient = axios.create({
  baseURL: process.env.API_URL, // TODO: Is there a default we need?
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

apiClient.interceptors.request.use(
  async config => {
    // Check if we need to refresh the token
    if (await tokenManager.isTokenExpired()) {
      try {
        const refreshToken = await tokenManager.getRefreshToken();
        if (refreshToken) {
          // Create a new axios instance to avoid interceptor loop
          const refreshClient = axios.create({
            baseURL: config.baseURL,
            timeout: config.timeout,
            headers: {
              'Content-Type': 'application/json',
              Accept: 'application/json',
            },
          });

          // Attempt to refresh token
          const response = await refreshClient.post(
            '/api/users/token/refresh',
            {
              refresh_token: refreshToken,
            }
          );

          if (response.data && response.data.access_token) {
            await tokenManager.storeTokens(response.data);
          }
        }
      } catch (error) {
        console.error('Token refresh failed in interceptor:', error);
        // Clear tokens if refresh fails
        await tokenManager.clearTokens();
      }
    }

    // Add auth header if we have a token
    const token = await tokenManager.getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },
  error => {
    return Promise.reject(error);
  }
);

module.exports = apiClient;
