/* ============================================
   WORLDBINDER — Environment Configuration Loader
   Loads .env file and provides configuration
   ============================================ */

// Default configuration
const DEFAULT_CONFIG = {
  DEBUG_MODE: false,
  API_BASE_URL: 'http://localhost:3000/api'
};

// Load environment variables from .env file
async function loadEnvConfig() {
  try {
    const response = await fetch('./.env');
    if (!response.ok) {
      console.warn('Could not load .env file, using defaults');
      return DEFAULT_CONFIG;
    }
    
    const envText = await response.text();
    const envLines = envText.split('\n');
    
    const config = { ...DEFAULT_CONFIG };
    
    envLines.forEach(line => {
      // Skip comments and empty lines
      if (line.trim() === '' || line.trim().startsWith('#')) {
        return;
      }
      
      // Parse KEY=VALUE format
      const [key, ...valueParts] = line.split('=');
      if (key && valueParts.length > 0) {
        const value = valueParts.join('=').trim();
        // Convert string values to appropriate types
        if (value === 'true') {
          config[key.trim()] = true;
        } else if (value === 'false') {
          config[key.trim()] = false;
        } else {
          config[key.trim()] = value;
        }
      }
    });
    
    return config;
  } catch (error) {
    console.warn('Error loading .env file:', error);
    return DEFAULT_CONFIG;
  }
}

// Initialize configuration
window.WORLDBINDER_CONFIG = DEFAULT_CONFIG;

// Load environment configuration and set up debug logger
loadEnvConfig().then(config => {
  window.WORLDBINDER_CONFIG = config;
  
  // Setup debug logger based on DEBUG_MODE
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
  
  console.log('Configuration loaded:', { 
    DEBUG_MODE: config.DEBUG_MODE, 
    API_BASE_URL: config.API_BASE_URL 
  });
}).catch(error => {
  console.error('Failed to load configuration:', error);
});
