'use strict';

/* ============================================
   WORLDBINDER — Landing Page Logic
   NFT gate + registration flow
   ============================================ */

console.log('Landing.js loaded successfully');

// Check if required libraries are loaded
if (typeof base58 === 'undefined') {
  console.error('Base58 library not loaded!');
}
if (typeof solana === 'undefined') {
  console.error('Solana library not loaded!');
}

(function () {
  'use strict';

  /* --- DOM Refs --- */
  const btnConnect   = document.getElementById('btn-connect-wallet');
  const modalReg     = document.getElementById('modal-register');
  const modalNoNFT   = document.getElementById('modal-no-nft');
  const photoUpload  = document.getElementById('photo-upload');
  const photoInput   = document.getElementById('photo-input');
  const photoPreview = document.getElementById('photo-preview');
  const photoHolder  = document.getElementById('photo-placeholder');
  const inputName    = document.getElementById('input-username');
  const btnRegister  = document.getElementById('btn-register');
  const onlineCount  = document.getElementById('online-count');
  const btnCloseNoNFT = document.getElementById('btn-close-no-nft');
  const scanStatus   = document.getElementById('scan-status');

  let avatarDataURL = null;
  let scannedNFTs = [];

  /* --- If already logged in, go to game --- */
  if (window.PhantomConnect && window.PhantomConnect.isLoggedIn()) {
    window.location.href = 'app.html';
    return;
  }

  /* --- Wait for Phantom Connect to initialize --- */
  function waitForPhantomConnect() {
    console.log('Waiting for PhantomConnect...', {
      hasPhantomConnect: !!window.PhantomConnect,
      hasSolana: !!window.solana,
      hasConfig: !!window.WORLDBINDER_CONFIG
    });
    
    if (window.PhantomConnect) {
      console.log('PhantomConnect found, initializing app...');
      initializeApp();
    } else {
      setTimeout(waitForPhantomConnect, 100);
    }
  }

  function initializeApp() {
    /* --- Online counter animation --- */
    function animateOnline() {
      const base = 159;
      const delta = Math.floor(Math.random() * 7) - 3;
      onlineCount.textContent = Math.max(140, base + delta);
    }
    setInterval(animateOnline, 4000);

    /* --- Connect Wallet --- */
    btnConnect.addEventListener('click', async () => {
      console.log('Connect wallet button clicked');
      console.log('PhantomConnect available:', !!window.PhantomConnect);
      console.log('Phantom installed:', !!(window.solana && window.solana.isPhantom));
      
      btnConnect.textContent = 'CONNECTING...';
      btnConnect.disabled = true;

      try {
        Debug.log('Starting wallet connection...');
        Debug.log('PhantomConnect available:', !!window.PhantomConnect);
        Debug.log('Phantom installed:', window.PhantomConnect ? window.PhantomConnect.isPhantomInstalled() : 'N/A');
        Debug.log('Using fallback:', window.PhantomConnect ? window.PhantomConnect.useFallback : 'N/A');
        
        const authResult = await window.PhantomConnect.connect();
        const walletAddr = authResult.publicKey;

        Debug.log('Wallet connected successfully:', walletAddr);

        /* Check if user already has profile with NFTs */
        try {
          const profile = await window.PhantomConnect.getUserProfile();
          if (profile.nfts && profile.nfts.length > 0) {
            window.location.href = 'app.html';
            return;
          }
        } catch (error) {
          Debug.log('Profile not found, proceeding with registration');
        }

        /* ====== ACCESS GATE CHECK ====== */
        btnConnect.textContent = 'CHECKING ACCESS...';

        // Check NFTs
        scannedNFTs = await NFTScanner.scan(walletAddr);
        Debug.log('NFT scan result:', scannedNFTs.length, 'NFTs found');

        // Check token balance
        console.log('Getting token balance...');
        
        // Wait for Solana Web3 to be available
        let retries = 0;
        while (typeof solana === 'undefined' && retries < 10) {
            console.log('Waiting for Solana Web3 to load...');
            await new Promise(resolve => setTimeout(resolve, 500));
            retries++;
        }
        
        if (typeof solana === 'undefined') {
            console.error('Solana Web3 failed to load');
        }
        
        const tokenBalance = await window.PhantomConnect.getTokenBalance();
        console.log('Token balance result:', tokenBalance);

        const hasNFTs = scannedNFTs.length > 0;
        const hasTokens = tokenBalance >= 20000;
        const hasAccess = hasNFTs || hasTokens;

        console.log('Access check:', { 
          hasNFTs, 
          hasTokens, 
          hasAccess,
          nftCount: scannedNFTs.length,
          tokenBalance: tokenBalance,
          requiredTokens: 20000
        });

        if (!hasAccess) {
          /* No access - show requirements modal */
          modalNoNFT.classList.remove('hidden');
          
          // Update modal content to show both requirements
          const modalContent = modalNoNFT.querySelector('.modal-box');
          modalContent.innerHTML = `
            <div class="no-nft-icon">🔒</div>
            <h2 style="margin-bottom: 12px;">Access Required</h2>
            <p style="color: var(--sand); margin-bottom: 8px;">To enter WORLDBINDER, you need either:</p>
            
            <div class="access-requirements">
              <div class="requirement-option">
                <div class="option-header">
                  <span class="option-icon">🎴</span>
                  <span class="option-title">Option 1: NFT Holder</span>
                </div>
                <div class="option-description">
                  At least 1 WORLDBINDER NFT in your wallet
                </div>
                <div class="option-detail">
                  NFTs give you warrior characters with unique abilities
                </div>
              </div>
              
              <div class="requirement-option">
                <div class="option-header">
                  <span class="option-icon">🪙</span>
                  <span class="option-title">Option 2: Token Holder</span>
                </div>
                <div class="option-description">
                  At least 20,000 WORLDBINDER tokens
                </div>
                <div class="option-detail">
                  Token address:<br>
                  <span class="token-address">8AFshqbDiPtFYe8KUNXa4F88DFh8yD8J5MXyeREopump</span>
                </div>
                <div class=\"current-balance ${tokenBalance >= 20000 ? 'success' : ''}\">
                  Current balance: ${tokenBalance.toLocaleString()} tokens ${tokenBalance >= 20000 ? '✓' : '✗'}
                </div>
              </div>
            </div>
            
            <a href="https://magiceden.io/" target="_blank" class="btn-gold" style="display:inline-block;text-decoration:none;margin-bottom:12px">
              BUY ON MAGIC EDEN
            </a>
            <br>
            <button class="btn-back" id="btn-close-no-nft">← TRY AGAIN</button>
          `;
          
          // Re-attach event listener for the new button
          document.getElementById('btn-close-no-nft').addEventListener('click', () => {
            modalNoNFT.classList.add('hidden');
            btnConnect.textContent = 'CONNECT WALLET';
            btnConnect.disabled = false;
          });
          
          return;
        }

        /* Access granted - show what user has */
        if (scanStatus) {
          let accessMessage = '';
          if (hasNFTs && hasTokens) {
            accessMessage = `${scannedNFTs.length} warrior(s) and ${tokenBalance.toLocaleString()} tokens found!`;
          } else if (hasNFTs) {
            accessMessage = `${scannedNFTs.length} warrior(s) found in your wallet!`;
          } else {
            accessMessage = `${tokenBalance.toLocaleString()} tokens found - Welcome warrior!`;
          }
          scanStatus.textContent = accessMessage;
          scanStatus.classList.remove('hidden');
        }

        /* Show registration modal */
        modalReg.classList.remove('hidden');

      } catch (err) {
        Debug.error('Connection error:', err);
        
        // Provide better error messages
        if (err.message.includes('not installed')) {
          alert('Phantom wallet not found. Please install Phantom from https://phantom.app/');
        } else if (err.message.includes('User rejected')) {
          alert('Connection cancelled by user.');
        } else {
          alert('Could not connect wallet: ' + err.message);
        }
      } finally {
        btnConnect.textContent = 'CONNECT WALLET';
        btnConnect.disabled = false;
      }
    });

    /* --- Close No-NFT Modal --- */
    if (btnCloseNoNFT) {
      btnCloseNoNFT.addEventListener('click', () => {
        modalNoNFT.classList.add('hidden');
      });
    }

    /* --- Photo Upload --- */
    photoUpload.addEventListener('click', () => photoInput.click());

    photoInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;

      // Проверка типа файла
      if (!file.type.startsWith('image/')) {
        alert('Please select an image file');
        photoInput.value = '';
        return;
      }

      // Проверка размера (2MB = 2097152 bytes)
      const maxSize = 2 * 1024 * 1024; // 2MB
      if (file.size > maxSize) {
        alert(`Image size exceeds 2MB limit. Your image: ${(file.size / 1024 / 1024).toFixed(2)}MB`);
        photoInput.value = '';
        return;
      }

      const reader = new FileReader();
      reader.onload = (ev) => {
        avatarDataURL = ev.target.result;
        photoPreview.src = avatarDataURL;
        photoPreview.classList.remove('hidden');
        photoHolder.classList.add('hidden');
        validateForm();
      };
      reader.onerror = () => {
        alert('Failed to read image file');
        photoInput.value = '';
      };
      reader.readAsDataURL(file);
    });

    /* --- Username Input --- */
    inputName.addEventListener('input', (e) => {
      // Удалить недопустимые символы в реальном времени
      let value = e.target.value;
      // Разрешены только буквы, цифры, подчеркивание и дефис
      value = value.replace(/[^a-zA-Z0-9_-]/g, '');
      // Максимум 20 символов
      if (value.length > 20) {
        value = value.slice(0, 20);
      }
      if (e.target.value !== value) {
        e.target.value = value;
      }
      validateForm();
    });

    function validateForm() {
      const username = inputName.value.trim();
      // Минимум 2 символа, должно начинаться с буквы
      const nameOk = username.length >= 2 && /^[a-zA-Z]/.test(username);
      btnRegister.disabled = !(nameOk && avatarDataURL);
      
      // Показать подсказку если имя невалидно
      if (username.length > 0 && !nameOk) {
        if (!/^[a-zA-Z]/.test(username)) {
          inputName.style.borderColor = 'var(--red)';
          inputName.title = 'Username must start with a letter';
        }
      } else {
        inputName.style.borderColor = '';
        inputName.title = '';
      }
    }

    /* --- Register --- */
    btnRegister.addEventListener('click', async () => {
      try {
        btnRegister.disabled = true;
        btnRegister.textContent = 'REGISTERING...';

        // Финальная валидация перед отправкой
        const username = inputName.value.trim();
        if (username.length < 2 || username.length > 20) {
          throw new Error('Username must be 2-20 characters');
        }
        if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(username)) {
          throw new Error('Username must start with a letter and contain only letters, numbers, _ and -');
        }
        if (!avatarDataURL) {
          throw new Error('Please upload an avatar');
        }

        // Update user profile with username and avatar
        const result = await window.PhantomConnect.updateProfile({
          username: username,
          avatarUrl: avatarDataURL
        });

        if (!result || result.error) {
          throw new Error(result?.error || 'Failed to update profile');
        }

        // Add scanned NFTs to user collection
        for (const nft of scannedNFTs) {
          await window.PhantomConnect.addNFT({
            mintAddress: nft.mint,
            name: nft.name || 'Unknown Warrior',
            imageUrl: nft.image || '',
            rarity: nft.rarity || 'Common'
          });
        }

        window.location.href = 'app.html';
      } catch (error) {
        console.error('Registration error:', error);
        
        // Показать понятное сообщение об ошибке
        let errorMessage = 'Registration failed. Please try again.';
        
        if (error.message) {
          if (error.message.includes('Validation error')) {
            // Ошибка валидации от сервера
            if (error.message.includes('username')) {
              errorMessage = 'Invalid username. Use only letters, numbers, _ and - (2-20 characters, must start with a letter)';
            } else if (error.message.includes('avatarUrl') || error.message.includes('avatar')) {
              errorMessage = 'Avatar size exceeds 2MB limit or invalid format.';
            } else {
              errorMessage = error.message.replace('Validation error: ', '');
            }
          } else if (error.message.includes('Username already taken')) {
            errorMessage = 'This username is already taken. Please choose another one.';
          } else if (error.message.includes('Username')) {
            errorMessage = error.message;
          } else if (error.message.includes('Avatar') || error.message.includes('2MB')) {
            errorMessage = 'Avatar size exceeds 2MB limit. Please use a smaller image.';
          } else if (error.message.includes('401') || error.message.includes('Unauthorized')) {
            errorMessage = 'Authentication failed. Please reconnect your wallet.';
          } else if (!error.message.includes('HTTP')) {
            errorMessage = error.message;
          }
        }
        
        alert(errorMessage);
        btnRegister.disabled = false;
        btnRegister.textContent = 'ENTER THE WORLD';
      }
    });
  }

  /* --- Start initialization --- */
  waitForPhantomConnect();

})();
