const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('api', {
  // Authentication
  auth: {
    login: (credentials) => ipcRenderer.invoke('auth:login', credentials),
    register: (userData) => ipcRenderer.invoke('auth:register', userData),
    refreshToken: (refreshToken) =>
      ipcRenderer.invoke('auth:refreshToken', refreshToken),
    getUser: () => ipcRenderer.invoke('auth:getUser'),
    updateBio: (bio) => ipcRenderer.invoke('auth:updateBio', bio),
    getBio: () => ipcRenderer.invoke('auth:getBio'),
  },

  // Profile
  profile: {
    getProfile: () => ipcRenderer.invoke('profile:get'),
    updateProfile: (profileData) =>
      ipcRenderer.invoke('profile:update', profileData),
  },

  // Payments
  payments: {
    createCustomer: () => ipcRenderer.invoke('payments:createCustomer'),
    createSubscription: (priceId) =>
      ipcRenderer.invoke('payments:createSubscription', priceId),
  },

  // Resumes
  resumes: {
    upload: (filePath) => ipcRenderer.invoke('resumes:upload', filePath),
    list: () => ipcRenderer.invoke('resumes:list'),
    download: (resumeId) => ipcRenderer.invoke('resumes:download', resumeId),
    delete: (resumeId) => ipcRenderer.invoke('resumes:delete', resumeId),
  },

  // Comments
  comments: {
    generate: (request) => ipcRenderer.invoke('comments:generate', request),
  },

  // Prompts
  prompts: {
    create: (promptData) => ipcRenderer.invoke('prompts:create', promptData),
    list: (filters) => ipcRenderer.invoke('prompts:list', filters),
    get: (promptId) => ipcRenderer.invoke('prompts:get', promptId),
    update: (promptId, promptData) =>
      ipcRenderer.invoke('prompts:update', promptId, promptData),
    delete: (promptId) => ipcRenderer.invoke('prompts:delete', promptId),
  },

  // Automation
  automation: {
    runLinkedInAutomation: (config) =>
      ipcRenderer.invoke('automation:runLinkedIn', config),
    stopAutomation: () => ipcRenderer.invoke('automation:stop'),
    loadPersistentConfig: () => ipcRenderer.invoke('automation:loadConfig'),
    onLog: (callback) => ipcRenderer.on('automation-log', callback),
  },
});
