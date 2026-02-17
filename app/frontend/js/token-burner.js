/* ============================================
   WORLDBINDER — Token Burner Module
   Burns SPL tokens for skill upgrades
   ============================================ */

console.log('=== TOKEN BURNER LOADING ===');

// Check if SPL Token library is loaded
if (typeof splToken === 'undefined' && typeof window.splToken !== 'undefined') {
  var splToken = window.splToken;
  console.log('Using window.splToken');
}

if (typeof splToken === 'undefined') {
  console.error('SPL Token library not loaded! Please check if the script is included in HTML.');
  console.error('Expected global variable: splToken or window.splToken');
} else {
  console.log('SPL Token library loaded successfully');
  console.log('TOKEN_PROGRAM_ID:', splToken.TOKEN_PROGRAM_ID?.toString());
}

window.TokenBurner = {

  /* --- CONFIG --- */

  /*
   * SPL Token mint address — update once the token is deployed.
   * This is the mint address of the game's fungible token.
   */
  TOKEN_MINT: '8AFshqbDiPtFYe8KUNXa4F88DFh8yD8J5MXyeREopump',

  /* Cost per skill level upgrade (in whole tokens, not lamports) */
  UPGRADE_COST: 10000,

  /* Token decimals — standard SPL = 6 or 9, update to match your token */
  TOKEN_DECIMALS: 6, // Tired token uses 6 decimals

  /**
   * Check player's token balance.
   * @param {string} walletAddress
   * @returns {Promise<number>} balance in whole tokens
   */
  async getBalance(walletAddress) {
    try {
      console.log('TokenBurner.getBalance called with wallet:', walletAddress);
      console.log('Token mint:', this.TOKEN_MINT);
      console.log('RPC URL:', NFTScanner.RPC_URL);
      
      const connection = new solanaWeb3.Connection(
        NFTScanner.RPC_URL,
        'confirmed'
      );

      const owner = new solanaWeb3.PublicKey(walletAddress);
      const mint  = new solanaWeb3.PublicKey(this.TOKEN_MINT);

      console.log('Fetching token accounts for owner...');
      
      /* First, let's see ALL token accounts */
      const allAccounts = await connection.getParsedTokenAccountsByOwner(owner, {
        programId: splToken.TOKEN_PROGRAM_ID
      });
      
      console.log('=== ALL TOKEN ACCOUNTS IN WALLET ===');
      allAccounts.value.forEach((account, idx) => {
        const info = account.account.data.parsed.info;
        console.log(`Token ${idx + 1}:`, {
          mint: info.mint,
          balance: info.tokenAmount.uiAmount,
          decimals: info.tokenAmount.decimals
        });
      });
      console.log('====================================');
      
      /* Find associated token account for our specific mint */
      const accounts = await connection.getParsedTokenAccountsByOwner(owner, {
        mint: mint
      });

      console.log('Token accounts found for our mint:', accounts.value.length);

      if (accounts.value.length === 0) {
        console.log('No token accounts found for mint:', this.TOKEN_MINT);
        console.log('Please copy the correct mint address from the logs above');
        return 0;
      }

      const info = accounts.value[0].account.data.parsed.info;
      const amount = info.tokenAmount.uiAmount || 0;
      
      console.log('Token account info:', info);
      console.log('Raw amount:', info.tokenAmount.amount);
      console.log('UI amount:', amount);
      
      return amount;

    } catch (err) {
      console.error('TokenBurner: Balance check failed', err);
      return 0;
    }
  },

  /* Destination wallet for token transfers (game treasury) */
  TREASURY_WALLET: 'Fqd19aFbZc6SHf9ifVU1SmounsFTjBEqkfJVLD51fa47',

  /**
   * Transfer tokens to treasury (instead of burning).
   * Sends tokens to game treasury wallet via Phantom.
   * @param {number} amount — amount of tokens to transfer (whole tokens)
   * @returns {Promise<string|null>} — tx signature or null on failure
   */
  async burn(amount) {
    try {
      console.log('TokenBurner: Starting transfer of', amount, 'tokens to treasury');
      
      if (!window.solana || !window.solana.isPhantom) {
        throw new Error('Phantom wallet not connected');
      }

      // Check if wallet is connected
      if (!window.solana.publicKey) {
        console.log('Wallet not connected, attempting to connect...');
        
        try {
          const resp = await window.solana.connect();
          console.log('Wallet connected:', resp.publicKey.toString());
        } catch (connectErr) {
          throw new Error('Wallet connection failed: ' + connectErr.message);
        }
      }

      const connection = new solanaWeb3.Connection(
        NFTScanner.RPC_URL,
        'confirmed'
      );

      const owner = window.solana.publicKey;
      
      if (!owner) {
        throw new Error('Wallet public key is null after connection attempt');
      }
      
      const mint  = new solanaWeb3.PublicKey(this.TOKEN_MINT);
      const destination = new solanaWeb3.PublicKey(this.TREASURY_WALLET);

      console.log('From wallet:', owner.toString());
      console.log('To treasury:', destination.toString());

      /* Find the sender's token account */
      const senderAccounts = await connection.getParsedTokenAccountsByOwner(owner, {
        mint: mint
      });

      console.log('Found token accounts:', senderAccounts.value.length);

      if (senderAccounts.value.length === 0) {
        console.error('No token account found for mint:', this.TOKEN_MINT);
        console.error('Wallet:', owner.toString());
        throw new Error(
          `You don't have a token account for this token. ` +
          `Please make sure you have ${this.TOKEN_MINT} tokens in your wallet.`
        );
      }

      const senderTokenAccount = senderAccounts.value[0].pubkey;
      const senderBalance = senderAccounts.value[0].account.data.parsed.info.tokenAmount;
      
      console.log('Sender token account:', senderTokenAccount.toString());
      console.log('Current balance:', senderBalance.uiAmount, 'tokens');
      
      // Calculate raw amount with decimals
      const rawAmount = BigInt(Math.floor(amount * Math.pow(10, this.TOKEN_DECIMALS)));
      console.log('Raw amount:', rawAmount.toString());
      
      // Check if user has enough tokens
      if (BigInt(senderBalance.amount) < rawAmount) {
        throw new Error(
          `Insufficient balance. You have ${senderBalance.uiAmount} tokens, ` +
          `but need ${amount} tokens.`
        );
      }

      /* Get or create associated token account for treasury */
      const treasuryTokenAccount = await splToken.getAssociatedTokenAddress(
        mint,
        destination,
        false, // allowOwnerOffCurve
        splToken.TOKEN_PROGRAM_ID,
        splToken.ASSOCIATED_TOKEN_PROGRAM_ID
      );

      console.log('Treasury token account:', treasuryTokenAccount.toString());

      /* Check if treasury token account exists */
      const treasuryAccountInfo = await connection.getAccountInfo(treasuryTokenAccount);
      const instructions = [];

      if (!treasuryAccountInfo) {
        console.log('Treasury token account does not exist, creating...');
        /* Create associated token account for treasury */
        const createAccountInstruction = splToken.createAssociatedTokenAccountInstruction(
          owner, // payer
          treasuryTokenAccount,
          destination, // owner
          mint,
          splToken.TOKEN_PROGRAM_ID,
          splToken.ASSOCIATED_TOKEN_PROGRAM_ID
        );
        instructions.push(createAccountInstruction);
      }

      /* Build transfer instruction */
      const transferInstruction = splToken.createTransferInstruction(
        senderTokenAccount,     /* source account */
        treasuryTokenAccount,   /* destination account */
        owner,                  /* owner authority */
        rawAmount,              /* amount in raw units */
        [],                     /* signers */
        splToken.TOKEN_PROGRAM_ID
      );
      instructions.push(transferInstruction);

      const transaction = new solanaWeb3.Transaction().add(...instructions);
      transaction.feePayer = owner;

      const { blockhash } = await connection.getLatestBlockhash();
      transaction.recentBlockhash = blockhash;

      console.log('Requesting signature from Phantom...');
      /* Sign and send via Phantom */
      const signed = await window.solana.signTransaction(transaction);
      const txSig = await connection.sendRawTransaction(signed.serialize());

      console.log('Transaction sent, signature:', txSig);
      console.log('Transaction submitted to blockchain. Backend will verify once it\'s confirmed.');

      console.log('TokenBurner: Transfer successful, tx:', txSig);
      return txSig;

    } catch (err) {
      console.error('TokenBurner: Burn failed', err);
      return null;
    }
  },

  /**
   * Check if player can afford an upgrade.
   * @param {string} walletAddress
   * @returns {Promise<boolean>}
   */
  async canAffordUpgrade(walletAddress) {
    const balance = await this.getBalance(walletAddress);
    return balance >= this.UPGRADE_COST;
  }
};

console.log('=== TOKEN BURNER LOADED ===');
console.log('TokenBurner object:', window.TokenBurner);
console.log('TOKEN_MINT:', window.TokenBurner.TOKEN_MINT);
console.log('Available globally:', typeof TokenBurner !== 'undefined');
