/* ============================================
   WORLDBINDER — Battle Engine
   Reads upgraded skill stats from session.
   Applies NFT count attack bonus.
   Uses frame.png for NFT display.
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

  const player = JSON.parse(localStorage.getItem('wb_user') || '{}');
  const wallet = localStorage.getItem('wb_wallet');

  if (!player || !wallet) {
    console.error('No user data found, redirecting to login...');
    window.location.href = 'index.html';
    return;
  }
  const selectedNFT = JSON.parse(sessionStorage.getItem('wb_selected_nft'));

  if (!selectedNFT) {
    window.location.href = 'app.html';
    return;
  }

  /* ======================
     LOAD SKILL STATS FROM SESSION
     (damage/cooldown already calculated by game.js)
     ====================== */
  const savedSkills = JSON.parse(sessionStorage.getItem('wb_skills_battle') || '{}');

  const SKILLS = [
    {
      key: 'bladeStrike', name: 'Blade Strike', emoji: '⚔️',
      damage: (savedSkills.bladeStrike || {}).damage || 18,
      cooldown: (savedSkills.bladeStrike || {}).cooldown || 1.3,
      type: 'damage', vfx: 'blade'
    },
    {
      key: 'energyBurst', name: 'Energy Burst', emoji: '💥',
      damage: (savedSkills.energyBurst || {}).damage || 55,
      cooldown: (savedSkills.energyBurst || {}).cooldown || 3.4,
      type: 'damage', vfx: 'energy'
    },
    {
      key: 'meteorRain', name: 'Meteor Rain', emoji: '☄️',
      damage: (savedSkills.meteorRain || {}).damage || 83,
      cooldown: (savedSkills.meteorRain || {}).cooldown || 8,
      type: 'damage', vfx: 'meteor'
    },
    {
      key: 'defense', name: 'Defense', emoji: '🛡️',
      damage: 0,
      cooldown: (savedSkills.defense || {}).cooldown || 8,
      type: 'shield', vfx: 'shield'
    },
    {
      key: 'healing', name: 'Healing', emoji: '💚',
      damage: 0,
      cooldown: (savedSkills.healing || {}).cooldown || 11,
      type: 'heal', vfx: 'heal'
    }
  ];

  /* ======================
     NFT ATTACK BONUS
     ====================== */
  const attackBonus = parseInt(sessionStorage.getItem('wb_attack_bonus') || '0', 10);
  const bonusMultiplier = 1 + attackBonus / 100; /* e.g. 1.20 for 20% */

  /* ======================
     OPPONENT GENERATION
     ====================== */
  const OPP_NAMES = ['DarkReaper', 'CrystalFang', 'VoidWalker', 'StormBringer', 'NightShade'];
  const OPP_NFT_NAMES = ['Bone Sentinel', 'Frost Wyrm', 'Lava Titan'];

  function generateOpponent() {
    const name = OPP_NAMES[Math.floor(Math.random() * OPP_NAMES.length)];
    const nftName = OPP_NFT_NAMES[Math.floor(Math.random() * OPP_NFT_NAMES.length)];
    const nftCount = Math.floor(Math.random() * 5) + 1;
    return { name, nftName, nftCount };
  }

  /* ======================
     BATTLE STATE
     ====================== */
  const MAX_HP = 300;
  const MATCH_TIME = 20;

  let state = {
    playerHP: MAX_HP,
    oppHP: MAX_HP,
    timer: MATCH_TIME,
    cooldowns: {},
    shieldActive: false,
    shieldTimer: null,
    healTimer: null,
    running: false,
    oppActionTimer: null,
    timerInterval: null,
    tickInterval: null
  };

  const opponent = generateOpponent();

  /* ======================
     DOM REFS
     ====================== */
  const $ = (id) => document.getElementById(id);

  const arenaPlayerPhoto = $('arena-player-photo');
  const arenaPlayerName  = $('arena-player-name');
  const arenaPlayerHP    = $('arena-player-hp');
  const arenaPlayerHPTxt = $('arena-player-hp-text');
  const arenaOppPhoto    = $('arena-opp-photo');
  const arenaOppName     = $('arena-opp-name');
  const arenaOppHP       = $('arena-opp-hp');
  const arenaOppHPTxt    = $('arena-opp-hp-text');
  const arenaTimer       = $('arena-timer');
  const skillBarEl       = $('skill-bar');
  const arenaContainer   = document.querySelector('.arena-container');
  const bonusBadge       = $('arena-bonus-badge');

  const playerCapsule = $('player-capsule');
  const oppCapsule    = $('opp-capsule');
  const playerBattleImg   = $('player-battle-img');
  const oppBattleImg      = $('opp-battle-img');
  const playerBattleLabel = $('player-battle-label');
  const oppBattleLabel    = $('opp-battle-label');

  const playerNftBattle = $('player-nft-battle');
  const oppNftBattle    = $('opp-nft-battle');

  const overlayResult = $('overlay-result');
  const resultTitle   = $('result-title');
  const resultSub     = $('result-sub');
  const btnPlayAgain  = $('btn-play-again');
  const btnBackBP     = $('btn-back-backpack');

  const overlayBet = $('overlay-bet');
  const betAmountInput = $('bet-amount');
  const betBalanceEl = $('bet-balance');
  const betErrorEl = $('bet-error');
  const btnBetConfirm = $('btn-bet-confirm');
  const btnBetCancel = $('btn-bet-cancel');

  const overlayWait = $('overlay-wait');
  const waitSecondsEl = $('wait-seconds');

  /* ======================
     INIT
     ====================== */
  function init() {
    setupUI();
    renderSkillBar();
    startPreBattleFlow();
  }

  let betAmount = 0;
  let waitTimer = null;
  let battleId = null;
  let battlePollTimer = null;
  let serverResolution = null;

  function startPreBattleFlow() {
    showBetOverlay();
  }

  function showBetOverlay() {
    if (!overlayBet) {
      // Fallback: if overlay missing, start immediately
      startWaitingPhase();
      return;
    }

    betAmount = 0;
    if (betErrorEl) betErrorEl.classList.add('hidden');
    if (betAmountInput) betAmountInput.value = '';

    const points = Number(player.points || 0);
    if (betBalanceEl) betBalanceEl.textContent = `Balance: ${points}`;

    overlayBet.classList.remove('hidden');
  }

  function hideBetOverlay() {
    if (overlayBet) overlayBet.classList.add('hidden');
  }

  function showBetError(msg) {
    if (!betErrorEl) return;
    betErrorEl.textContent = msg;
    betErrorEl.classList.remove('hidden');
  }

  function startWaitingPhase() {
    hideBetOverlay();

    // Waiting is server-authoritative now.
    // We display the server-provided wait time and poll for resolution.
    startServerBattle();
  }

  async function startServerBattle() {
    const token = localStorage.getItem('wb_token');
    if (!token) {
      showBetError('Not authenticated');
      return;
    }

    const mintAddress = selectedNFT && (selectedNFT.mintAddress || selectedNFT.mint || selectedNFT.id);
    if (!mintAddress) {
      showBetError('NFT is missing mint address');
      return;
    }

    try {
      const resp = await fetch('/api/battle/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ mintAddress, bet: betAmount })
      });

      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        const msg = (data && data.detail) ? data.detail : 'Failed to start battle';
        overlayWait && overlayWait.classList.add('hidden');
        showBetOverlay();
        showBetError(msg);
        return;
      }

      battleId = data.battle_id;
      serverResolution = null;

      let remaining = Number(data.wait_seconds || 60);
      if (overlayWait) overlayWait.classList.remove('hidden');
      if (waitSecondsEl) waitSecondsEl.textContent = String(remaining);

      if (waitTimer) clearInterval(waitTimer);
      waitTimer = setInterval(() => {
        remaining -= 1;
        if (waitSecondsEl) waitSecondsEl.textContent = String(Math.max(0, remaining));
        if (remaining <= 0) {
          clearInterval(waitTimer);
          waitTimer = null;
          if (overlayWait) overlayWait.classList.add('hidden');
          startBattle();
        }
      }, 1000);

      startPollingBattleStatus();
    } catch (e) {
      overlayWait && overlayWait.classList.add('hidden');
      showBetOverlay();
      showBetError('Network error');
    }
  }

  function startPollingBattleStatus() {
    if (!battleId) return;
    const token = localStorage.getItem('wb_token');
    if (!token) return;

    if (battlePollTimer) clearInterval(battlePollTimer);
    battlePollTimer = setInterval(async () => {
      try {
        const resp = await fetch(`/api/battle/${encodeURIComponent(battleId)}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) return;

        if (data.status === 'resolved' && data.result) {
          serverResolution = data.result;
          clearInterval(battlePollTimer);
          battlePollTimer = null;
          if (state.running) {
            endBattle();
          }
        }
      } catch (_e) {
        // ignore transient errors
      }
    }, 1000);
  }

  function setupUI() {
    arenaPlayerName.textContent = player.username;
    if (player.photo) arenaPlayerPhoto.src = player.photo;

    /* Player NFT — framed */
    if (selectedNFT.image) {
      playerBattleImg.src = selectedNFT.image;
      playerBattleImg.style.display = 'block';
    } else {
      playerBattleImg.style.display = 'none';
    }
    playerBattleLabel.textContent = selectedNFT.name;

    /* Opponent NFT */
    arenaOppName.textContent = opponent.name;
    arenaOppPhoto.style.display = 'none';
    oppBattleLabel.textContent = opponent.nftName;

    /* Bonus badge */
    if (bonusBadge && attackBonus > 0) {
      bonusBadge.textContent = `+${attackBonus}% ATK`;
      bonusBadge.classList.remove('hidden');
    }

    updateHPBars();
  }

  /* ======================
     SKILL BAR
     ====================== */
  function renderSkillBar() {
    skillBarEl.innerHTML = SKILLS.map(sk => {
      const pSkill = player.skills[sk.key];
      const unlocked = pSkill && pSkill.level > 0;

      return `
        <button class="skill-btn ${unlocked ? '' : 'on-cooldown'}"
                data-skill="${sk.key}"
                ${unlocked ? '' : 'disabled'}
                title="${sk.name} (DMG: ${sk.damage} | CD: ${sk.cooldown}s)">
          <span class="skill-emoji">${sk.emoji}</span>
          <span class="skill-label">${sk.name}</span>
          <div class="cooldown-overlay hidden" data-cd="${sk.key}"></div>
        </button>
      `;
    }).join('');

    skillBarEl.querySelectorAll('.skill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        if (!state.running) return;
        useSkill(btn.dataset.skill);
      });
    });
  }

  /* ======================
     BATTLE LOOP
     ====================== */
  function startBattle() {
    state.running = true;
    state.timer = MATCH_TIME;

    state.timerInterval = setInterval(() => {
      state.timer--;
      arenaTimer.textContent = state.timer;
      if (state.timer <= 5) arenaTimer.style.color = '#e74c3c';
      if (state.timer <= 0) endBattle();
    }, 1000);

    state.tickInterval = setInterval(() => {
      Object.keys(state.cooldowns).forEach(key => {
        if (state.cooldowns[key] > 0) {
          state.cooldowns[key] = Math.max(0, state.cooldowns[key] - 0.1);
          updateCooldownUI(key);
        }
        if (state.cooldowns[key] <= 0) clearCooldownUI(key);
      });
    }, 100);

    scheduleOppAction();
  }

  function endBattle() {
    state.running = false;
    clearInterval(state.timerInterval);
    clearInterval(state.tickInterval);
    if (state.shieldTimer) clearTimeout(state.shieldTimer);
    if (state.healTimer) clearInterval(state.healTimer);
    if (state.oppActionTimer) clearTimeout(state.oppActionTimer);
    if (battlePollTimer) {
      clearInterval(battlePollTimer);
      battlePollTimer = null;
    }

    // Result is server-authoritative if it arrived.
    if (serverResolution && typeof serverResolution.player_wins === 'boolean') {
      determineWinnerFromServer(serverResolution);
    } else {
      determineWinner();
    }
  }

  function determineWinnerFromServer(res) {
    // Sync local cached player for UI only
    if (typeof res.points === 'number') player.points = res.points;
    if (typeof res.wins === 'number') player.wins = res.wins;
    if (typeof res.losses === 'number') player.losses = res.losses;
    WalletManager.savePlayer(player);

    showResult(!!res.player_wins);
  }

  /* ======================
     PLAYER SKILL USE
     ====================== */
  function useSkill(key) {
    if (state.cooldowns[key] > 0) return;

    const skill = SKILLS.find(s => s.key === key);
    if (!skill) return;

    const pSkill = player.skills[key];
    if (!pSkill || pSkill.level <= 0) return;

    switch (skill.vfx) {
      case 'blade':
        vfxBladeStrike(oppCapsule);
        dealDamageToOpp(applyBonus(skill.damage));
        spawnDamageFloat(oppCapsule, `-${applyBonus(skill.damage)}`, 'blade');
        break;

      case 'energy':
        vfxEnergyBurst(oppCapsule);
        dealDamageToOpp(applyBonus(skill.damage));
        spawnDamageFloat(oppCapsule, `-${applyBonus(skill.damage)}`, 'energy');
        break;

      case 'meteor':
        vfxMeteorRain(oppCapsule, oppNftBattle);
        setTimeout(() => {
          if (!state.running) return;
          const dmg = applyBonus(skill.damage);
          dealDamageToOpp(dmg);
          spawnDamageFloat(oppCapsule, `-${dmg}`, 'meteor');
          if (state.oppHP <= 0) endBattle();
        }, 700);
        break;

      case 'shield':
        vfxShieldActivate(playerCapsule);
        activateShield();
        spawnDamageFloat(playerCapsule, 'SHIELD', 'shield');
        break;

      case 'heal':
        vfxHealStart(playerCapsule, playerNftBattle);
        activateHeal();
        break;
    }

    state.cooldowns[key] = skill.cooldown;
    setCooldownUI(key, skill.cooldown);

    if (skill.vfx !== 'meteor' && state.oppHP <= 0) endBattle();
  }

  /** Apply NFT attack bonus to damage */
  function applyBonus(baseDmg) {
    return Math.floor(baseDmg * bonusMultiplier);
  }

  /* ====================================================
     VFX FUNCTIONS
     ==================================================== */

  function vfxBladeStrike(capsule) {
    capsule.classList.add('hit', 'vfx-blade');
    setTimeout(() => capsule.classList.remove('hit', 'vfx-blade'), 500);
  }

  function vfxEnergyBurst(capsule) {
    capsule.classList.add('hit', 'vfx-energy');
    setTimeout(() => capsule.classList.remove('hit', 'vfx-energy'), 700);
  }

  function vfxMeteorRain(capsule, container) {
    const meteorBox = document.createElement('div');
    meteorBox.className = 'vfx-meteor-container';
    for (let i = 0; i < 5; i++) {
      const m = document.createElement('div');
      m.className = 'vfx-meteor';
      meteorBox.appendChild(m);
    }
    container.style.position = 'relative';
    container.appendChild(meteorBox);

    setTimeout(() => {
      capsule.classList.add('hit', 'vfx-meteor-impact');
      if (arenaContainer) {
        arenaContainer.classList.add('screen-shake');
        setTimeout(() => arenaContainer.classList.remove('screen-shake'), 500);
      }
    }, 600);

    setTimeout(() => {
      meteorBox.remove();
      capsule.classList.remove('hit', 'vfx-meteor-impact');
    }, 1500);
  }

  function vfxShieldActivate(capsule) {
    capsule.classList.add('vfx-shield-activate');
    setTimeout(() => capsule.classList.remove('vfx-shield-activate'), 500);
    capsule.classList.add('vfx-shield');
  }

  function vfxShieldRemove(capsule) {
    capsule.classList.remove('vfx-shield');
  }

  function vfxHealStart(capsule, container) {
    capsule.classList.add('vfx-heal');
    const pBox = document.createElement('div');
    pBox.className = 'vfx-heal-particle-container';
    for (let i = 0; i < 8; i++) {
      const p = document.createElement('div');
      p.className = 'vfx-heal-particle';
      pBox.appendChild(p);
    }
    container.style.position = 'relative';
    container.appendChild(pBox);

    setTimeout(() => {
      capsule.classList.remove('vfx-heal');
      pBox.remove();
    }, 3500);
  }

  function vfxHealTick(capsule) {
    capsule.classList.add('vfx-heal-tick');
    setTimeout(() => capsule.classList.remove('vfx-heal-tick'), 300);
  }

  /* ======================
     OPPONENT ACTIONS
     ====================== */
  function scheduleOppAction() {
    if (!state.running) return;
    const delay = 1500 + Math.random() * 2500;
    state.oppActionTimer = setTimeout(() => {
      if (!state.running) return;
      oppAttack();
      scheduleOppAction();
    }, delay);
  }

  function oppAttack() {
    const attackSkills = SKILLS.filter(s => s.type === 'damage');
    const skill = attackSkills[Math.floor(Math.random() * attackSkills.length)];
    let dmg = skill.damage;

    // Opponent advantage: tuned so the opponent wins more often on average.
    // Keep it subtle to preserve gameplay feel.
    const opponentDmgMultiplier = 1.12;
    dmg = Math.floor(dmg * opponentDmgMultiplier);

    switch (skill.vfx) {
      case 'blade':  vfxBladeStrike(playerCapsule); break;
      case 'energy': vfxEnergyBurst(playerCapsule); break;
      case 'meteor': vfxMeteorRain(playerCapsule, playerNftBattle); break;
    }

    if (state.shieldActive) dmg = Math.floor(dmg * 0.3);

    const applyDelay = skill.vfx === 'meteor' ? 700 : 0;

    setTimeout(() => {
      if (!state.running && state.playerHP > 0) return;
      state.playerHP = Math.max(0, state.playerHP - dmg);
      updateHPBars();
      spawnDamageFloat(playerCapsule, `-${dmg}`, skill.vfx);
      if (state.playerHP <= 0) endBattle();
    }, applyDelay);
  }

  /* ======================
     COMBAT HELPERS
     ====================== */
  function dealDamageToOpp(dmg) {
    state.oppHP = Math.max(0, state.oppHP - dmg);
    updateHPBars();
  }

  function activateShield() {
    state.shieldActive = true;
    if (state.shieldTimer) clearTimeout(state.shieldTimer);
    state.shieldTimer = setTimeout(() => {
      state.shieldActive = false;
      vfxShieldRemove(playerCapsule);
    }, 10000);
  }

  function activateHeal() {
    let ticks = 0;
    if (state.healTimer) clearInterval(state.healTimer);
    state.healTimer = setInterval(() => {
      ticks++;
      state.playerHP = Math.min(MAX_HP, state.playerHP + 20);
      updateHPBars();
      vfxHealTick(playerCapsule);
      spawnDamageFloat(playerCapsule, '+20', 'heal');
      if (ticks >= 3) clearInterval(state.healTimer);
    }, 1000);
  }

  function updateHPBars() {
    const pPct = Math.max(0, (state.playerHP / MAX_HP) * 100);
    const oPct = Math.max(0, (state.oppHP / MAX_HP) * 100);

    arenaPlayerHP.style.width = pPct + '%';
    arenaOppHP.style.width = oPct + '%';
    arenaPlayerHPTxt.textContent = `${Math.max(0, state.playerHP)} / ${MAX_HP}`;
    arenaOppHPTxt.textContent = `${Math.max(0, state.oppHP)} / ${MAX_HP}`;

    if (pPct < 30) arenaPlayerHP.classList.add('low');
    else arenaPlayerHP.classList.remove('low');
    if (oPct < 30) arenaOppHP.classList.add('low');
    else arenaOppHP.classList.remove('low');
  }

  /* ======================
     DAMAGE FLOATS
     ====================== */
  function spawnDamageFloat(capsule, text, type) {
    const el = document.createElement('div');
    el.className = 'damage-float' + (type ? ` ${type}` : '');
    el.textContent = text;

    const rect = capsule.getBoundingClientRect();
    const offsetX = (Math.random() - 0.5) * 40;
    el.style.left = (rect.left + rect.width / 2 - 30 + offsetX) + 'px';
    el.style.top = (rect.top - 10) + 'px';

    document.body.appendChild(el);
    setTimeout(() => el.remove(), 1200);
  }

  /* ======================
     COOLDOWN UI
     ====================== */
  function setCooldownUI(key, total) {
    const btn = skillBarEl.querySelector(`[data-skill="${key}"]`);
    if (!btn) return;
    const overlay = btn.querySelector('.cooldown-overlay');
    btn.classList.add('on-cooldown');
    overlay.classList.remove('hidden');
    overlay.textContent = Math.ceil(total) + 's';
  }

  function updateCooldownUI(key) {
    const overlay = skillBarEl.querySelector(`[data-cd="${key}"]`);
    if (!overlay) return;
    const r = state.cooldowns[key];
    if (r > 0) overlay.textContent = r.toFixed(1) + 's';
  }

  function clearCooldownUI(key) {
    const btn = skillBarEl.querySelector(`[data-skill="${key}"]`);
    if (!btn) return;
    const overlay = btn.querySelector('.cooldown-overlay');
    btn.classList.remove('on-cooldown');
    overlay.classList.add('hidden');
    delete state.cooldowns[key];
  }

  /* ======================
     DETERMINE WINNER
     ====================== */
  function determineWinner() {
    let playerWins;

    if (state.playerHP <= 0 && state.oppHP <= 0) {
      playerWins = Math.random() < getPlayerAdvantage();
    } else if (state.oppHP <= 0) {
      playerWins = true;
    } else if (state.playerHP <= 0) {
      playerWins = false;
    } else {
      if (state.playerHP > state.oppHP) playerWins = true;
      else if (state.oppHP > state.playerHP) playerWins = false;
      else playerWins = Math.random() < getPlayerAdvantage();
    }

    showResult(playerWins);
  }

  function getPlayerAdvantage() {
    const myNFTs = player.nfts ? player.nfts.length : 1;
    const oppNFTs = opponent.nftCount;
    const ratio = myNFTs / (myNFTs + oppNFTs);
    return 0.3 + ratio * 0.4;
  }

  function showResult(won) {
    overlayResult.classList.remove('hidden');

    if (won) {
      resultTitle.textContent = 'FLAWLESS VICTORY';
      resultTitle.className = 'result-title win';
      resultSub.textContent = 'THE ARENA BOWS BEFORE YOU';
    } else {
      resultTitle.textContent = 'YOU ARE A LOSER';
      resultTitle.className = 'result-title lose';
      resultSub.textContent = 'KEEP TRAINING';
    }
  }

  /* ======================
     RESULT BUTTONS
     ====================== */
  btnPlayAgain.addEventListener('click', () => window.location.href = 'arena.html');
  btnBackBP.addEventListener('click', () => window.location.href = 'app.html');

  if (btnBetConfirm) {
    btnBetConfirm.addEventListener('click', () => {
      const points = Number(player.points || 0);
      const raw = betAmountInput ? betAmountInput.value : '';
      const amt = Math.floor(Number(raw));

      if (!Number.isFinite(amt) || amt <= 0) {
        showBetError('Enter a valid bet amount');
        return;
      }
      if (amt > points) {
        showBetError('Not enough points for this bet');
        return;
      }

      betAmount = amt;
      startWaitingPhase();
    });
  }

  if (btnBetCancel) {
    btnBetCancel.addEventListener('click', () => window.location.href = 'app.html');
  }

  /* --- Start --- */
  init();

})();
