/* ============================================
   WORLDBINDER — Configuration
   Loads configuration from server
   ============================================ */

// Default configuration
const DEFAULT_CONFIG = {
  DEBUG_MODE: false,
  API_BASE_URL: '/api'
};

// Ensure Debug exists before any other scripts use it
window.Debug = window.Debug || {
  log: function () {},
  error: function () {},
  warn: function () {},
  info: function () {},
};

// Initialize configuration
window.WORLDBINDER_CONFIG = { ...DEFAULT_CONFIG };

// Load configuration from server
async function loadConfig() {
  try {
    const response = await fetch('/api/config');
    if (response.ok) {
      const config = await response.json();
      window.WORLDBINDER_CONFIG = { ...DEFAULT_CONFIG, ...config };

      if (window.TokenBurner && window.WORLDBINDER_CONFIG.TOKEN_MINT) {
        window.TokenBurner.TOKEN_MINT = window.WORLDBINDER_CONFIG.TOKEN_MINT;
      }

      if (window.WORLDBINDER_CONFIG.SOLANA_RPC && window.NFTScanner) {
        window.NFTScanner.RPC_URL = window.WORLDBINDER_CONFIG.SOLANA_RPC;
      }
    }
  } catch (error) {
    console.warn('Failed to load config from server, using defaults');
  }
  
  // Setup debug logger based on loaded configuration
  window.Debug = {
    log: function(...args) {
      if (window.WORLDBINDER_CONFIG.DEBUG_MODE) {
        console.log(...args);
      }
    },
    
    error: function(...args) {
      if (window.WORLDBINDER_CONFIG.DEBUG_MODE) {
        console.error(...args);
      }
    },
    
    warn: function(...args) {
      if (window.WORLDBINDER_CONFIG.DEBUG_MODE) {
        console.warn(...args);
      }
    },
    
    info: function(...args) {
      if (window.WORLDBINDER_CONFIG.DEBUG_MODE) {
        console.info(...args);
      }
    }
  };
}

// Load configuration immediately
loadConfig();

// Base58 is now loaded dynamically, no need to check here
console.log('Config loaded successfully');
