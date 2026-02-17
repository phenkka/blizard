/* ============================================
   WORLDBINDER — Wallet Module
   Handles Phantom wallet connection & authentication
   ============================================ */

const WalletManager = {

  publicKey: null,
  authToken: null,
  API_BASE_URL: 'http://localhost:3000/api',

  /** Check if Phantom is installed */
  isPhantomInstalled() {
    return window.solana && window.solana.isPhantom;
  },

  /** Generate authentication message */
  generateAuthMessage() {
    const timestamp = new Date().toISOString();
    return `Sign this message to authenticate with WORLDBINDER at ${timestamp}`;
  },

  /** Connect to Phantom wallet and authenticate */
  async connect() {
    if (!this.isPhantomInstalled()) {
      window.open('https://phantom.app/', '_blank');
      throw new Error('Phantom wallet not installed');
    }

    try {
      // Connect to wallet
      const resp = await window.solana.connect();
      this.publicKey = resp.publicKey.toString();

      // Generate and sign authentication message
      const message = this.generateAuthMessage();
      const encodedMessage = new TextEncoder().encode(message);
      const signature = await window.solana.signMessage(encodedMessage, 'utf8');

      // Authenticate with backend
      const authResponse = await this.authenticateWithBackend(
        this.publicKey, 
        Base58.encode(signature.signature),
        message
      );

      if (authResponse.token) {
        this.authToken = authResponse.token;
        sessionStorage.setItem('wb_wallet', this.publicKey);
        sessionStorage.setItem('wb_token', this.authToken);
        sessionStorage.setItem('wb_user', JSON.stringify(authResponse.user));
        
        return {
          publicKey: this.publicKey,
          user: authResponse.user
        };
      } else {
        throw new Error('Authentication failed');
      }

    } catch (err) {
      console.error('Wallet connection error:', err);
      throw err;
    }
  },

  /** Authenticate with backend API */
  async authenticateWithBackend(publicKey, signature, message) {
    try {
      const response = await fetch(`${this.API_BASE_URL}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          publicKey,
          signature,
          message
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Authentication failed');
      }

      return await response.json();
    } catch (error) {
      console.error('Backend authentication error:', error);
      throw error;
    }
  },

  /** Disconnect wallet */
  async disconnect() {
    if (window.solana && window.solana.isPhantom) {
      await window.solana.disconnect();
    }
    this.publicKey = null;
    this.authToken = null;
    sessionStorage.removeItem('wb_wallet');
    sessionStorage.removeItem('wb_token');
    sessionStorage.removeItem('wb_user');
  },

  /** Get stored wallet address */
  getStoredWallet() {
    return sessionStorage.getItem('wb_wallet');
  },

  /** Get stored auth token */
  getStoredToken() {
    return sessionStorage.getItem('wb_token');
  },

  /** Get stored user data */
  getUser() {
    const raw = sessionStorage.getItem('wb_user');
    return raw ? JSON.parse(raw) : null;
  },

  /** Save user data */
  saveUser(data) {
    sessionStorage.setItem('wb_user', JSON.stringify(data));
  },

  /** Check if logged in */
  isLoggedIn() {
    return !!this.getStoredWallet() && !!this.getStoredToken() && !!this.getUser();
  },

  /** Make authenticated API request */
  async apiRequest(endpoint, options = {}) {
    const token = this.getStoredToken();
    if (!token) {
      throw new Error('Not authenticated');
    }

    const defaultOptions = {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      }
    };

    const response = await fetch(`${this.API_BASE_URL}${endpoint}`, {
      ...defaultOptions,
      ...options,
      headers: {
        ...defaultOptions.headers,
        ...options.headers
      }
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    return await response.json();
  },

  /** Get user profile from backend */
  async getUserProfile() {
    return await this.apiRequest('/user/profile');
  },

  /** Update user profile */
  async updateProfile(profileData) {
    return await this.apiRequest('/user/profile', {
      method: 'PUT',
      body: JSON.stringify(profileData)
    });
  },

  /** Add NFT to user collection */
  async addNFT(nftData) {
    return await this.apiRequest('/user/nfts', {
      method: 'POST',
      body: JSON.stringify(nftData)
    });
  },

  /** Get available skills */
  async getSkills() {
    return await this.apiRequest('/skills');
  },

  /** Get leaderboard */
  async getLeaderboard() {
    return await this.apiRequest('/leaderboard');
  },

  /** Initialize session from storage */
  initializeFromStorage() {
    this.publicKey = this.getStoredWallet();
    this.authToken = this.getStoredToken();
    return this.isLoggedIn();
  }
};
