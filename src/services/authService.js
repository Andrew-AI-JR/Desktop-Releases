const { ipcMain } = require('electron');
const APIClient = require('./apiClient');
const TokenManager = require('./tokenManager');

class AuthService {
  constructor() {
    this.apiClient = new APIClient();
    this.tokenManager = new TokenManager();
    this.initialize();
  }

  initialize() {
    this.apiClient.setBaseUrl(process.env.API_URL);
    this.apiClient.setTokenManager(this.tokenManager);
  }

  formatError(error) {
    if (error.response) {
      return {
        message: error.response.data.detail || 'An error occurred',
        status: error.response.status,
      };
    }
    return {
      message: error.message,
      status: null,
    };
  }

  async login(credentials) {
    try {
      const response = await this.apiClient.post('/api/users/token', {
        username: credentials.email,
        password: credentials.password,
      });
      const { access_token, refresh_token } = response.data;
      this.tokenManager.setTokens(access_token, refresh_token);
      this.apiClient.setAuthHeader(access_token);
      return { success: true, data: response.data };
    } catch (error) {
      console.error('Login error in authService:', error.response ? error.response.data : error.message);
      return { success: false, error: this.formatError(error) };
    }
  }

  async register(credentials) {
    try {
      const response = await this.apiClient.post('/api/users/register', {
        email: credentials.email,
        password: credentials.password,
      });
      return { success: true, data: response.data };
    } catch (error) {
      console.error('Registration error in authService:', error.response ? error.response.data : error.message);
      return { success: false, error: this.formatError(error) };
    }
  }

  async forgotPassword(data) {
    try {
      // NOTE: This endpoint does not exist yet and needs to be created in the backend.
      const response = await this.apiClient.post('/api/users/forgot-password', data);
      return { success: true, data: response.data };
    } catch (error) {
      console.error('Forgot password error in authService:', error.response ? error.response.data : error.message);
      return { success: false, error: this.formatError(error) };
    }
  }

  async logout() {
    this.tokenManager.clearTokens();
    return { success: true };
  }

  async getCurrentUser() {
    try {
        const response = await this.apiClient.get('/api/users/me');
        return { success: true, data: response.data };
    } catch (error) {
        console.error('Get current user error in authService:', error.response ? error.response.data : error.message);
        return { success: false, error: this.formatError(error) };
    }
  }

  registerEventHandlers() {
    ipcMain.handle('auth:login', async (event, credentials) => this.login(credentials));
    ipcMain.handle('auth:register', async (event, credentials) => this.register(credentials));
    ipcMain.handle('auth:forgot-password', async (event, data) => this.forgotPassword(data));
    ipcMain.handle('auth:logout', async () => this.logout());
    ipcMain.handle('auth:get-current-user', async () => this.getCurrentUser());
    ipcMain.handle('auth:getAccessToken', () => this.tokenManager.getAccessToken());
  }
}

module.exports = AuthService; 