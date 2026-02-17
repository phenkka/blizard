/* ============================================
   WORLDBINDER — Token Burner Module
   Burns SPL tokens for skill upgrades
   ============================================ */

const TokenBurner = {

  /* --- CONFIG --- */

  /*
   * SPL Token mint address — update once the token is deployed.
   * This is the mint address of the game's fungible token.
   */
  TOKEN_MINT: 'PASTE_YOUR_TOKEN_MINT_ADDRESS_HERE',

  /* Cost per skill level upgrade (in whole tokens, not lamports) */
  UPGRADE_COST: 50000,

  /* Token decimals — standard SPL = 6 or 9, update to match your token */
  TOKEN_DECIMALS: 6,

  /**
   * Check player's token balance.
   * @param {string} walletAddress
   * @returns {Promise<number>} balance in whole tokens
   */
  async getBalance(walletAddress) {
    try {
      const connection = new solanaWeb3.Connection(
        NFTScanner.RPC_URL,
        'confirmed'
      );

      const owner = new solanaWeb3.PublicKey(walletAddress);
      const mint  = new solanaWeb3.PublicKey(this.TOKEN_MINT);

      /* Find associated token account */
      const accounts = await connection.getParsedTokenAccountsByOwner(owner, {
        mint: mint
      });

      if (accounts.value.length === 0) return 0;

      const info = accounts.value[0].account.data.parsed.info;
      const amount = info.tokenAmount.uiAmount || 0;
      return amount;

    } catch (err) {
      console.error('TokenBurner: Balance check failed', err);
      return 0;
    }
  },

  /**
   * Burn tokens for a skill upgrade.
   * Sends a burn transaction via Phantom.
   * @param {number} amount — amount of tokens to burn (whole tokens)
   * @returns {Promise<string|null>} — tx signature or null on failure
   */
  async burn(amount) {
    try {
      if (!window.solana || !window.solana.isPhantom) {
        throw new Error('Phantom wallet not connected');
      }

      const connection = new solanaWeb3.Connection(
        NFTScanner.RPC_URL,
        'confirmed'
      );

      const owner = window.solana.publicKey;
      const mint  = new solanaWeb3.PublicKey(this.TOKEN_MINT);

      /* Find the token account */
      const accounts = await connection.getParsedTokenAccountsByOwner(owner, {
        mint: mint
      });

      if (accounts.value.length === 0) {
        throw new Error('No token account found');
      }

      const tokenAccount = accounts.value[0].pubkey;
      const rawAmount = amount * Math.pow(10, this.TOKEN_DECIMALS);

      /* Build burn instruction using SPL Token program */
      const burnInstruction = splToken.createBurnInstruction(
        tokenAccount,   /* account to burn from */
        mint,           /* token mint */
        owner,          /* owner authority */
        rawAmount       /* amount in raw units */
      );

      const transaction = new solanaWeb3.Transaction().add(burnInstruction);
      transaction.feePayer = owner;

      const { blockhash } = await connection.getLatestBlockhash();
      transaction.recentBlockhash = blockhash;

      /* Sign and send via Phantom */
      const signed = await window.solana.signTransaction(transaction);
      const txSig = await connection.sendRawTransaction(signed.serialize());

      await connection.confirmTransaction(txSig, 'confirmed');

      console.log('TokenBurner: Burn successful, tx:', txSig);
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
