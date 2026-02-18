/* ============================================
   WORLDBINDER — NFT Scanner Module
   Scans wallet via Helius DAS API
   Filters by specific collection address
   ============================================ */

const NFTScanner = {

  /* --- CONFIG --- */
  RPC_URL: 'https://mainnet.helius-rpc.com/?api-key=2b51d0c8-c911-4ffe-a74a-15c2633620b3',

  /*
   * Collection mint address — update this once the collection is live.
   * This is the Verified Collection address from on-chain metadata.
   */
  COLLECTION_ADDRESS: 'BeFtLwLtS9Rva12KrHKRMY1H5WoeM1Y2ULMnNJKopump',

  /* Max NFTs allowed in backpack */
  MAX_NFTS: 3,

  /**
   * Scan a wallet for NFTs belonging to the collection.
   * @param {string} walletAddress — Solana public key
   * @returns {Promise<Array>} — Array of parsed NFT objects
   */
  async scan(walletAddress) {
    try {
      const token = localStorage.getItem('wb_token');
      if (!token) {
        console.warn('NFTScanner: No auth token available');
        return [];
      }

      const response = await fetch('/api/wallet/scan', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ walletAddress: walletAddress })
      });

      if (!response.ok) {
        const errText = await response.text().catch(() => '');
        console.warn('NFTScanner: Backend scan failed', response.status, errText);
        return [];
      }

      const data = await response.json();
      const nfts = Array.isArray(data.nfts) ? data.nfts : [];
      return nfts.slice(0, this.MAX_NFTS);

    } catch (err) {
      console.error('NFTScanner: Scan failed', err);
      return [];
    }
  },

  /**
   * Parse a raw DAS asset into a game NFT object.
   */
  _parseNFT(item) {
    const content = item.content || {};
    const metadata = content.metadata || {};
    const files = content.files || [];
    const links = content.links || {};
    const attributes = metadata.attributes || [];

    /* Extract image URL */
    let image = links.image || '';
    if (!image && files.length > 0) {
      image = files[0].uri || files[0].cdn_uri || '';
    }

    /* Extract traits from attributes */
    const traits = { strength: 0, agility: 0, magic: 0 };
    attributes.forEach(attr => {
      const key = (attr.trait_type || '').toLowerCase();
      const val = parseInt(attr.value, 10);
      if (key === 'strength' && !isNaN(val)) traits.strength = val;
      if (key === 'agility' && !isNaN(val))  traits.agility = val;
      if (key === 'magic' && !isNaN(val))    traits.magic = val;
    });

    /* Determine rarity from attributes or fallback */
    let rarity = 'common';
    const rarityAttr = attributes.find(a =>
      (a.trait_type || '').toLowerCase() === 'rarity'
    );
    if (rarityAttr) {
      rarity = rarityAttr.value.toLowerCase();
    }

    /* Determine level from attributes or fallback */
    let level = 1;
    const levelAttr = attributes.find(a =>
      (a.trait_type || '').toLowerCase() === 'level'
    );
    if (levelAttr) {
      level = parseInt(levelAttr.value, 10) || 1;
    }

    return {
      id: item.id,                           /* mint address */
      name: metadata.name || 'Unknown NFT',
      image: image,
      rarity: rarity,
      level: level,
      traits: traits
    };
  },

  /**
   * Get attack bonus based on NFT count.
   * 1 NFT = +10%, 2 NFTs = +15%, 3 NFTs = +20%
   */
  getAttackBonus(nftCount) {
    if (nftCount >= 3) return 20;
    if (nftCount >= 2) return 15;
    if (nftCount >= 1) return 10;
    return 0;
  }
};

window.NFTScanner = NFTScanner;
