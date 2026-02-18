/* ============================================
   WORLDBINDER — Game Hub Logic
   Backpack, Leaderboard, Skill Tree (token burn),
   NFT bonuses, Matchmaking
   ============================================ */

(function () {
  'use strict';

  /* --- AUTH GUARD --- */
  function checkAuth() {
    const token = localStorage.getItem('wb_token');
    if (!token) {
      console.error('No auth token found, redirecting to login...');
      window.location.href = 'index.html';
      return false;
    }
    
    // Validate token format
    try {
      const parts = token.split('.');
      if (parts.length !== 3) {
        throw new Error('Invalid token format');
      }
      
      const payload = JSON.parse(atob(parts[1]));
      const now = Math.floor(Date.now() / 1000);
      
      if (payload.exp && payload.exp < now) {
        throw new Error('Token expired');
      }
      
      console.log('Token valid, user:', payload.sub);
      return true;
    } catch (error) {
      console.error('Invalid token:', error.message);
      localStorage.removeItem('wb_token');
      window.location.href = 'index.html';
      return false;
    }
  }

  // Check auth immediately
  if (!checkAuth()) {
    return;
  }

  /* --- Wait for Phantom Connect to initialize --- */
  function waitForPhantomConnect() {
    if (window.PhantomConnect) {
      initializeGame();
    } else {
      setTimeout(waitForPhantomConnect, 100);
    }
  }

  function checkAuth() {
    const token = localStorage.getItem('wb_token');
    if (!token) {
      console.error('No auth token found, redirecting to login...');
      window.location.href = 'index.html';
      return false;
    }
    
    // Validate token format
    try {
      const parts = token.split('.');
      if (parts.length !== 3) {
        throw new Error('Invalid token format');
      }
      
      const payload = JSON.parse(atob(parts[1]));
      const now = Math.floor(Date.now() / 1000);
      
      if (payload.exp && payload.exp < now) {
        throw new Error('Token expired');
      }
      
      console.log('Token valid, user:', payload.sub);
      return true;
    } catch (error) {
      console.error('Invalid token:', error.message);
      localStorage.removeItem('wb_token');
      localStorage.removeItem('wb_wallet');
      localStorage.removeItem('wb_user');
      window.location.href = 'index.html';
      return false;
    }
  }

  // Check auth immediately
  if (!checkAuth()) {
    return;
  }

  function initializeGame() {
    /* --- Load User Data --- */
    const user = JSON.parse(localStorage.getItem('wb_user') || '{}');
    const wallet = localStorage.getItem('wb_wallet');
    
    if (!user || !wallet) {
      console.error('No user data found, redirecting to login...');
      window.location.href = 'index.html';
      return;
    }
    
    console.log('User loaded:', user);
    console.log('Wallet loaded:', wallet);

    const player = {
      username: user.username || 'Warrior',
      points: user.points || 0,
      wins: user.wins || 0,
      losses: user.losses || 0,
      skills: user.skills || {
        bladeStrike: { level: 1, maxLevel: 5 },
        energyBurst: { level: 0, maxLevel: 5 },
        meteorRain: { level: 0, maxLevel: 3 },
        defense: { level: 0, maxLevel: 5 },
        healing: { level: 0, maxLevel: 5 }
      },
      nfts: Array.isArray(user.nfts) ? user.nfts : []
    };

    const WalletManager = window.PhantomConnect;

    function authHeaders() {
      const token = localStorage.getItem('wb_token');
      return token ? { 'Authorization': `Bearer ${token}` } : {};
    }

    async function refreshNFTs() {
      try {
        if (!window.NFTScanner || !wallet) return;
        const nfts = await window.NFTScanner.scan(wallet);
        player.nfts = Array.isArray(nfts) ? nfts : [];
        const stored = JSON.parse(localStorage.getItem('wb_user') || '{}');
        stored.nfts = player.nfts;
        localStorage.setItem('wb_user', JSON.stringify(stored));
      } catch (e) {
        console.warn('Failed to refresh NFTs:', e);
      }
    }

    /* ======================
       SKILL DEFINITIONS
       Base values — modified by level: +2 DMG, -0.5s CD per level
       ====================== */
  const SKILL_DEFS = {
    bladeStrike: {
      name: 'Blade Strike',
      emoji: '⚔️',
      desc: 'Basic melee attack',
      baseDamage: 18,
      baseCooldown: 1.3,
      type: 'damage'
    },
    energyBurst: {
      name: 'Energy Burst',
      emoji: '💥',
      desc: 'Powerful energy blast',
      baseDamage: 55,
      baseCooldown: 3.4,
      type: 'damage'
    },
    meteorRain: {
      name: 'Meteor Rain',
      emoji: '☄️',
      desc: 'Ultimate devastation from the sky',
      baseDamage: 83,
      baseCooldown: 8,
      type: 'damage'
    },
    defense: {
      name: 'Defense',
      emoji: '🛡️',
      desc: 'Magic shield for 10 seconds',
      baseDamage: 0,
      baseCooldown: 8,
      type: 'shield'
    },
    healing: {
      name: 'Healing',
      emoji: '💚',
      desc: 'Heals 20 HP/s for 3 seconds',
      baseDamage: 0,
      baseCooldown: 11,
      type: 'heal'
    }
  };

  /* Upgrade cost per level in tokens */
  const UPGRADE_TOKEN_COST = 50000;

  /** Calculate effective damage at current level */
  function getSkillDamage(key) {
    const def = SKILL_DEFS[key];
    const lvl = player.skills[key].level;
    if (def.type !== 'damage') return 0;
    return def.baseDamage + (lvl - 1) * 2;
  }

  /** Calculate effective cooldown at current level */
  function getSkillCooldown(key) {
    const def = SKILL_DEFS[key];
    const lvl = player.skills[key].level;
    const cd = def.baseCooldown - (lvl - 1) * 0.5;
    return Math.max(0.5, cd); /* minimum 0.5s */
  }

  /* ======================
     FAKE LEADERBOARD DATA
     ====================== */
  const LEADERBOARD = [
    { name: 'xDragonSlayer', pts: 2840 },
    { name: 'CryptoMage99', pts: 2310 },
    { name: 'ShadowBlade', pts: 1980 },
    { name: 'PhantomKing', pts: 1750 },
    { name: 'RuneHunter', pts: 1620 }
  ];

  const KOTH_TOP = [
    { name: 'xDragonSlayer', pts: 2840, medal: '🥇' },
    { name: 'CryptoMage99',  pts: 2310, medal: '🥈' },
    { name: 'ShadowBlade',   pts: 1980, medal: '🥉' }
  ];

  /* ======================
     DOM REFS
     ====================== */
  const $ = (id) => document.getElementById(id);

  const displayUsername = $('display-username');
  const displayPoints  = $('display-points');
  const statWins       = $('stat-wins');
  const statLosses     = $('stat-losses');
  const statWinrate    = $('stat-winrate');
  const statTotal      = $('stat-total');
  const leaderboardEl  = $('leaderboard-list');
  const nftGrid        = $('nft-grid');
  const nftDetail      = $('nft-detail');
  const detailName     = $('detail-name');
  const detailRarity   = $('detail-rarity');
  const detailImg      = $('detail-img');
  const detailTraits   = $('detail-traits');
  const btnEnterArena  = $('btn-enter-arena');
  const kothPodium     = $('koth-podium');
  const kothTimer      = $('koth-timer');
  const onlineCount    = $('online-count');
  const nftBonusTable  = $('nft-bonus-table');

  const btnUpgradeSkills = $('btn-upgrade-skills');
  const btnLogout        = $('btn-logout');

  const screenBackpack  = $('screen-backpack');
  const screenSkillTree = $('screen-skill-tree');
  const btnBackSkills   = $('btn-back-skills');
  const skillTreeGrid   = $('skill-tree-grid');
  const tokenBalanceEl  = $('token-balance');
  const upgradeCostEl   = $('upgrade-cost');

  const overlayMM     = $('overlay-matchmaking');
  const mmSearching   = $('mm-searching');
  const mmFound       = $('mm-found');
  const mmCountdown   = $('mm-countdown');
  const countdownNum  = $('countdown-num');
  const btnMMYes      = $('btn-mm-yes');
  const btnMMNo       = $('btn-mm-no');

  let selectedNFT = null;

  /* ======================
     INIT
     ====================== */
  function init() {
    renderPlayerInfo();
    renderLeaderboard();
    renderNFTs();
    renderBonusTable();
    renderKOTH();
    startKOTHTimer();
    startOnlineCounter();
  }

  (async () => {
    await refreshNFTs();
    init();
  })();

  /* --- Player Info --- */
  function renderPlayerInfo() {
    displayUsername.textContent = player.username;
    displayPoints.textContent = player.points;
    statWins.textContent = player.wins;
    statLosses.textContent = player.losses;
    const total = player.wins + player.losses;
    statTotal.textContent = total;
    statWinrate.textContent = total > 0
      ? Math.round((player.wins / total) * 100) + '%'
      : '0%';
  }

  /* --- Leaderboard --- */
  function renderLeaderboard() {
    leaderboardEl.innerHTML = LEADERBOARD.map((p, i) => `
      <div class="leaderboard-item">
        <span class="leaderboard-rank">#${i + 1}</span>
        <span class="leaderboard-name">${p.name}</span>
        <span class="leaderboard-pts">${p.pts}</span>
      </div>
    `).join('');
  }

  /* --- NFT Grid (real from wallet scan) --- */
  function renderNFTs() {
    if (!player.nfts || player.nfts.length === 0) {
      nftGrid.innerHTML = '<p style="color:var(--sand-dark);text-align:center;grid-column:1/-1">No NFTs in backpack</p>';
      return;
    }

    nftGrid.innerHTML = player.nfts.map((nft) => `
      <div class="nft-card" data-nft-id="${nft.id}">
        <div class="nft-frame-wrap">
          <img class="nft-frame-img" src="assets/frame.png" alt="frame">
          <div class="nft-frame-inner">
            ${nft.image
              ? `<img src="${nft.image}" alt="${nft.name}">`
              : `<span style="font-size:32px;color:#fff">?</span>`
            }
          </div>
        </div>
        <div class="nft-name">${nft.name}</div>
        <span class="nft-rarity rarity-${nft.rarity}">${nft.rarity}</span>
      </div>
    `).join('');

    document.querySelectorAll('.nft-card').forEach((card) => {
      card.addEventListener('click', () => selectNFT(card.dataset.nftId));
    });
  }

  function selectNFT(nftId) {
    const nft = player.nfts.find(n => n.id === nftId);
    if (!nft) return;

    selectedNFT = nft;

    document.querySelectorAll('.nft-card').forEach(c => c.classList.remove('selected'));
    document.querySelector(`[data-nft-id="${nftId}"]`).classList.add('selected');

    nftDetail.classList.remove('hidden');
    detailName.textContent = nft.name;
    detailRarity.textContent = nft.rarity;
    detailRarity.className = `nft-rarity rarity-${nft.rarity}`;

    if (nft.image) {
      detailImg.src = nft.image;
      detailImg.style.display = 'block';
    } else {
      detailImg.style.display = 'none';
    }

    const traits = nft.traits;
    if (Array.isArray(traits)) {
      const rows = traits.map(t => {
        const name = (t.trait_type || t.traitType || '').toString() || 'Trait';
        const value = (t.value ?? '').toString();
        return `
          <div class="trait-row">
            <span class="trait-name">${name}</span>
            <span class="trait-value">${value}</span>
          </div>
        `;
      }).join('');
      detailTraits.innerHTML = `
        <div class="trait-row">
          <span class="trait-name">Level</span>
          <span class="trait-value">${nft.level}</span>
        </div>
        ${rows}
      `;
    } else {
      const t = traits || {};
      detailTraits.innerHTML = `
        <div class="trait-row">
          <span class="trait-name">Level</span>
          <span class="trait-value">${nft.level}</span>
        </div>
        <div class="trait-row">
          <span class="trait-name">Strength</span>
          <span class="trait-value">${t.strength ?? 0}</span>
        </div>
        <div class="trait-row">
          <span class="trait-name">Agility</span>
          <span class="trait-value">${t.agility ?? 0}</span>
        </div>
        <div class="trait-row">
          <span class="trait-name">Magic</span>
          <span class="trait-value">${t.magic ?? 0}</span>
        </div>
      `;
    }
  }

  /* --- NFT Bonus Table --- */
  function renderBonusTable() {
    if (!nftBonusTable) return;
    const count = player.nfts ? player.nfts.length : 0;
    const bonus = NFTScanner.getAttackBonus(count);

    nftBonusTable.innerHTML = `
      <h3>NFT Attack Bonus</h3>
      <div class="bonus-row ${count >= 1 ? 'active' : ''}">
        <span>1 NFT</span><span>+10% ATK</span>
      </div>
      <div class="bonus-row ${count >= 2 ? 'active' : ''}">
        <span>2 NFTs</span><span>+15% ATK</span>
      </div>
      <div class="bonus-row ${count >= 3 ? 'active' : ''}">
        <span>3 NFTs</span><span>+20% ATK</span>
      </div>
      <div class="bonus-current">
        Your bonus: <strong>+${bonus}%</strong>
      </div>
    `;
  }

  /* --- KOTH --- */
  function renderKOTH() {
    kothPodium.innerHTML = KOTH_TOP.map(p => `
      <div class="koth-place">
        <div class="koth-medal">${p.medal}</div>
        <div class="koth-place-name">${p.name}</div>
        <div class="koth-place-pts">${p.pts} pts</div>
      </div>
    `).join('');
  }

  function startKOTHTimer() {
    let seconds = 86382;
    function tick() {
      const h = String(Math.floor(seconds / 3600)).padStart(2, '0');
      const m = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
      const s = String(seconds % 60).padStart(2, '0');
      kothTimer.textContent = `${h}:${m}:${s}`;
      seconds = seconds > 0 ? seconds - 1 : 86400;
    }
    tick();
    setInterval(tick, 1000);
  }

  function startOnlineCounter() {
    setInterval(() => {
      const base = 159;
      const delta = Math.floor(Math.random() * 7) - 3;
      onlineCount.textContent = Math.max(140, base + delta);
    }, 4000);
  }

  /* ======================
     SKILL TREE (Token Burn Upgrade)
     ====================== */
  btnUpgradeSkills.addEventListener('click', async () => {
    screenSkillTree.classList.remove('hidden');
    await renderSkillTree();
  });

  btnBackSkills.addEventListener('click', () => {
    screenSkillTree.classList.add('hidden');
  });

  async function renderSkillTree() {
    /* Fetch token balance */
    let tokenBalance = 0;
    const wallet = WalletManager.getStoredWallet();
    if (wallet && typeof TokenBurner !== 'undefined') {
      try {
        tokenBalance = await TokenBurner.getBalance(wallet);
      } catch (e) {
        tokenBalance = 0;
      }
    }

    if (tokenBalanceEl) tokenBalanceEl.textContent = tokenBalance.toLocaleString();
    if (upgradeCostEl) upgradeCostEl.textContent = UPGRADE_TOKEN_COST.toLocaleString();

    const keys = Object.keys(SKILL_DEFS);
    let html = '';

    keys.forEach((key, i) => {
      const def = SKILL_DEFS[key];
      const sk  = player.skills[key];
      const unlocked = sk.level > 0;
      const maxed = sk.level >= sk.maxLevel;
      const canAfford = tokenBalance >= UPGRADE_TOKEN_COST;
      const canUpgrade = !maxed && canAfford;

      /* Calculate current stats at this level */
      const currentDmg = def.type === 'damage'
        ? def.baseDamage + Math.max(0, sk.level - 1) * 2
        : 0;
      const currentCD = Math.max(0.5, def.baseCooldown - Math.max(0, sk.level - 1) * 0.5);

      /* Next level preview */
      const nextDmg = def.type === 'damage'
        ? def.baseDamage + sk.level * 2
        : 0;
      const nextCD = Math.max(0.5, def.baseCooldown - sk.level * 0.5);

      if (i > 0) {
        html += `<div class="skill-connector ${unlocked ? 'active' : ''}"></div>`;
      }

      html += `
        <div class="skill-node ${unlocked ? 'unlocked' : 'locked'}">
          <div class="skill-icon">${def.emoji}</div>
          <div class="skill-info">
            <h4>${def.name}</h4>
            <p>${def.desc}</p>
            <div class="skill-stats">
              ${def.type === 'damage' ? `DMG: ${currentDmg}` : ''}
              ${def.type === 'shield' ? 'Shield: 10s' : ''}
              ${def.type === 'heal' ? 'Heal: 20/s × 3s' : ''}
              &nbsp;|&nbsp; CD: ${currentCD.toFixed(1)}s
            </div>
            ${!maxed ? `
              <div class="skill-next-level">
                Next Lv: ${def.type === 'damage' ? `DMG ${nextDmg}` : ''}
                CD ${nextCD.toFixed(1)}s
                &nbsp;|&nbsp; Cost: ${UPGRADE_TOKEN_COST.toLocaleString()} tokens
              </div>
            ` : ''}
          </div>
          <div class="skill-level-display">
            Lv. ${sk.level}/${sk.maxLevel}
            <br>
            <button class="btn-skill-upgrade"
                    data-skill="${key}"
                    ${canUpgrade ? '' : 'disabled'}>
              ${maxed ? 'MAX' : (canAfford ? '🔥 BURN & UPGRADE' : 'NOT ENOUGH')}
            </button>
          </div>
        </div>
      `;
    });

    skillTreeGrid.innerHTML = html;

    /* Upgrade click handlers (token burn) */
    document.querySelectorAll('.btn-skill-upgrade').forEach(btn => {
      btn.addEventListener('click', async () => {
        const key = btn.dataset.skill;
        const sk = player.skills[key];
        if (sk.level >= sk.maxLevel) return;

        btn.textContent = 'BURNING...';
        btn.disabled = true;

        /* Attempt token burn */
        let burnSuccess = false;

        if (typeof TokenBurner !== 'undefined' &&
            TokenBurner.TOKEN_MINT !== 'PASTE_YOUR_TOKEN_MINT_ADDRESS_HERE') {
          const txSig = await TokenBurner.burn(UPGRADE_TOKEN_COST);
          burnSuccess = !!txSig;
        } else {
          burnSuccess = false;
          console.warn('TokenBurner: Token mint not set — upgrade disabled.');
        }

        if (burnSuccess) {
          sk.level++;
          WalletManager.savePlayer(player);
          await renderSkillTree();
        } else {
          btn.textContent = 'BURN FAILED';
          setTimeout(() => renderSkillTree(), 2000);
        }
      });
    });
  }

  /* ======================
     ENTER ARENA / MATCHMAKING
     ====================== */
  btnEnterArena.addEventListener('click', () => {
    if (!selectedNFT) return;

    /* Store selected NFT + player + bonus for arena */
    const nftCount = player.nfts ? player.nfts.length : 0;
    const bonus = NFTScanner.getAttackBonus(nftCount);

    sessionStorage.setItem('wb_selected_nft', JSON.stringify(selectedNFT));
    sessionStorage.setItem('wb_attack_bonus', bonus);

    /* Store current skill levels for battle engine */
    const skillsForBattle = {};
    Object.keys(SKILL_DEFS).forEach(key => {
      const def = SKILL_DEFS[key];
      const sk = player.skills[key];
      skillsForBattle[key] = {
        level: sk.level,
        damage: def.type === 'damage'
          ? def.baseDamage + Math.max(0, sk.level - 1) * 2
          : 0,
        cooldown: Math.max(0.5, def.baseCooldown - Math.max(0, sk.level - 1) * 0.5)
      };
    });
    sessionStorage.setItem('wb_skills_battle', JSON.stringify(skillsForBattle));

    /* Show matchmaking */
    overlayMM.classList.remove('hidden');
    mmSearching.classList.remove('hidden');
    mmFound.classList.add('hidden');
    mmCountdown.classList.add('hidden');

    const delay = 3000 + Math.random() * 3000;
    setTimeout(() => {
      mmSearching.classList.add('hidden');
      mmFound.classList.remove('hidden');
    }, delay);
  });

  btnMMYes.addEventListener('click', () => {
    mmFound.classList.add('hidden');
    mmCountdown.classList.remove('hidden');

    let count = 3;
    countdownNum.textContent = count;

    const interval = setInterval(() => {
      count--;
      if (count > 0) {
        countdownNum.textContent = count;
        countdownNum.style.animation = 'none';
        void countdownNum.offsetHeight;
        countdownNum.style.animation = 'countdown-pulse 1s ease-in-out';
      } else {
        clearInterval(interval);
        window.location.href = 'arena.html';
      }
    }, 1000);
  });

  btnMMNo.addEventListener('click', () => {
    overlayMM.classList.add('hidden');
  });

  /* ======================
     LOGOUT
     ====================== */
  btnLogout.addEventListener('click', async () => {
    if (window.PhantomConnect && window.PhantomConnect.disconnect) {
      await window.PhantomConnect.disconnect();
    }
    window.location.href = 'index.html';
  });

  } // end of initializeGame function

  /* --- Start initialization --- */
  waitForPhantomConnect();

})();
