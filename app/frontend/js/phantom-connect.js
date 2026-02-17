/* ============================================
   WORLDBINDER — Phantom Wallet Integration
   Direct Phantom wallet connection (no SDK dependency)
   ============================================ */

console.log('PhantomConnect.js loaded successfully');

// Use external base58 library
const base58 = window.base58;

if (!base58) {
  console.error('Base58 library not loaded! Please check script loading order.');
}

class PhantomConnectManager {
  constructor() {
    this.user = null;
    this.isConnected = false;
    this.API_BASE_URL = window.WORLDBINDER_CONFIG?.API_BASE_URL || '/api';
    
    // Initialize immediately
    this.init();
  }

  async init() {
    Debug.log('Using direct Phantom wallet connection');
    
    // Check for existing session
    const storedToken = localStorage.getItem('wb_token');
    if (storedToken && this.isPhantomInstalled()) {
      await this.validateSession(storedToken);
    }
  }

  isPhantomInstalled() {
    return window.solana && window.solana.isPhantom;
  }

  async tryAutoConnect() {
    try {
      if (this.isPhantomInstalled()) {
        try {
          const resp = await window.solana.connect({ onlyIfTrusted: true });
          if (resp.publicKey) {
            this.isConnected = true;
            this.user = {
              publicKey: resp.publicKey.toString()
            };
            
            const storedToken = localStorage.getItem('wb_token');
            if (storedToken) {
              await this.validateSession(storedToken);
            }
          }
        } catch (error) {
          Debug.log('Auto-connect failed, manual connection required');
        }
      }
    } catch (error) {
      Debug.log('Auto-connect failed, manual connection required');
    }
  }

  async connect() {
    try {
      return await this.connectDirect();
    } catch (error) {
      Debug.error('Phantom connection error:', error);
      this.disconnect();
      throw error;
    }
  }

  async connectDirect() {
    if (!this.isPhantomInstalled()) {
      throw new Error('Phantom wallet not installed. Please install Phantom from https://phantom.app/');
    }

    // Connect to Phantom wallet
    const resp = await window.solana.connect();
    const publicKey = resp.publicKey.toString();

    this.isConnected = true;
    this.user = {
      publicKey: publicKey
    };

    // Get challenge from backend
    const challenge = await this.getChallenge(publicKey);
    
    Debug.log('Challenge received:', challenge);
    
    // Sign the challenge message
    const encodedMessage = new TextEncoder().encode(challenge.message);
    const signatureResp = await window.solana.signMessage(encodedMessage, 'utf8');
    
    Debug.log('Signature response:', signatureResp);
    Debug.log('Signature type:', typeof signatureResp.signature);
    Debug.log('Signature length:', signatureResp.signature.length);
    
    // Convert signature Uint8Array to base64 string for backend (временно)
    const signatureBase64 = btoa(String.fromCharCode(...signatureResp.signature));
    Debug.log('Signature base64:', signatureBase64);
    
    // Verify signature with backend and get token
    const authResult = await this.verifySignature(
      publicKey,
      signatureBase64,
      challenge.message
    );

    if (authResult.token) {
      // Save session
      localStorage.setItem('wb_wallet', publicKey);
      localStorage.setItem('wb_token', authResult.token);
      localStorage.setItem('wb_user', JSON.stringify(authResult.user));
      
      return {
        publicKey: publicKey,
        user: authResult.user
      };
    } else {
      throw new Error('Authentication failed');
    }
  }

  async getChallenge(publicKey) {
    try {
      const response = await fetch(`${this.API_BASE_URL}/auth/challenge`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ publicKey })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to get challenge');
      }

      return await response.json();
    } catch (error) {
      Debug.error('Challenge request error:', error);
      throw error;
    }
  }

  async verifySignature(publicKey, signature, message) {
    try {
      Debug.log('Verifying signature:', { publicKey, signature, message });
      
      const response = await fetch(`${this.API_BASE_URL}/auth/verify`, {
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

      Debug.log('Verification response status:', response.status);
      
      if (!response.ok) {
        const errorData = await response.json();
        Debug.error('Verification failed:', errorData);
        throw new Error(errorData.detail || 'Signature verification failed');
      }

      const result = await response.json();
      Debug.log('Verification success:', result);
      return result;
    } catch (error) {
      Debug.error('Signature verification error:', error);
      throw error;
    }
  }

  async validateSession(token) {
    try {
      // Try to get user profile with existing token
      const response = await fetch(`${this.API_BASE_URL}/user/profile`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const userData = await response.json();
        this.user = {
          publicKey: userData.wallet_address,
          ...userData
        };
        return true;
      } else {
        // Token invalid, clear session
        this.clearSession();
        return false;
      }
    } catch (error) {
      Debug.error('Session validation error:', error);
      this.clearSession();
      return false;
    }
  }

  disconnect() {
    if (window.solana && window.solana.isPhantom) {
      // Disconnect from Phantom
      window.solana.disconnect().catch(Debug.error);
    }
    
    this.isConnected = false;
    this.user = null;
    this.clearSession();
  }

  clearSession() {
    localStorage.removeItem('wb_wallet');
    localStorage.removeItem('wb_token');
    localStorage.removeItem('wb_user');
  }

  // Getters
  getStoredWallet() {
    return localStorage.getItem('wb_wallet');
  }

  getStoredToken() {
    return localStorage.getItem('wb_token');
  }

  getUser() {
    const raw = localStorage.getItem('wb_user');
    return raw ? JSON.parse(raw) : null;
  }

  isLoggedIn() {
    return !!this.getStoredWallet() && !!this.getStoredToken() && !!this.getUser();
  }

  // API methods
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
      if (response.status === 401) {
        // Token expired, clear session
        this.clearSession();
      }
      
      // Обработка ошибок валидации
      if (response.status === 422 && errorData.errors) {
        const errors = errorData.errors.map(err => {
          const field = err.loc ? err.loc[err.loc.length - 1] : 'field';
          return `${field}: ${err.msg}`;
        }).join(', ');
        throw new Error(`Validation error: ${errors}`);
      }
      
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    return await response.json();
  }

  async getUserProfile() {
    return await this.apiRequest('/user/profile');
  }

  async updateProfile(profileData) {
    return await this.apiRequest('/user/profile', {
      method: 'PATCH',
      body: JSON.stringify(profileData)
    });
  }

  async addNFT(nftData) {
    return await this.apiRequest('/user/nfts', {
      method: 'POST',
      body: JSON.stringify(nftData)
    });
  }

  async getSkills() {
    return await this.apiRequest('/skills');
  }

  async getTokenBalance(tokenMint = '8AFshqbDiPtFYe8KUNXa4F88DFh8yD8J5MXyeREopump') {
    try {
      if (!window.solana || !window.solana.publicKey) {
        console.error('No solana or publicKey found');
        return 0;
      }

      console.log('Getting token balance for:', window.solana.publicKey.toString());
      console.log('Token mint:', tokenMint);

      // Use direct API call for reliability
      return await this.getTokenBalanceDirect(tokenMint);
    } catch (error) {
      console.error('Failed to get token balance:', error);
      return 0;
    }
  }

  async getTokenBalanceDirect(tokenMint) {
    try {
      const HELIUS_RPC = 'https://mainnet.helius-rpc.com/?api-key=2b51d0c8-c911-4ffe-a74a-15c2633620b3';
      
      const requestBody = {
        jsonrpc: "2.0",
        id: 1,
        method: "getTokenAccountsByOwner",
        params: [
          window.solana.publicKey.toString(),
          {
            mint: tokenMint
          },
          {
            encoding: "jsonParsed"
          }
        ]
      };

      console.log('Fetching token balance via direct API for:', window.solana.publicKey.toString());

      const response = await fetch(HELIUS_RPC, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody)
      });

      if (!response.ok) {
        console.error('Helius API HTTP error:', response.status, response.statusText);
        return 0;
      }

      const data = await response.json();
      
      if (data.error) {
        console.error('Helius API error:', data.error);
        return 0;
      }

      if (!data.result || !data.result.value || data.result.value.length === 0) {
        console.log('No token accounts found for this token');
        return 0;
      }

      let totalBalance = 0;
      for (const account of data.result.value) {
        const balance = account.account.data.parsed.info.tokenAmount.uiAmount || 0;
        totalBalance += balance;
        console.log('Account balance (direct API):', balance);
      }

      console.log('Total balance (direct API):', totalBalance);
      return totalBalance;
    } catch (error) {
      console.error('Failed to get token balance via direct API:', error);
      return 0;
    }
  }

  async getLeaderboard() {
    return await this.apiRequest('/leaderboard');
  }
}

// Global instance
window.PhantomConnect = new PhantomConnectManager();
