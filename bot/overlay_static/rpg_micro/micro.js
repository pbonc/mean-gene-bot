(() => {
  "use strict";

  const LOGICAL_WIDTH = 1920;
  const LOGICAL_HEIGHT = 96;
  const canvas = document.getElementById("micro-strip");
  const ctx = canvas.getContext("2d", { alpha: true });
  ctx.imageSmoothingEnabled = false;

  const palette = {
    ink: "#fff7d6",
    shadow: "rgba(4, 8, 18, 0.78)",
    hp: "#7cf29a",
    hpLow: "#ff6b6b",
    hpBack: "rgba(18, 23, 34, 0.88)",
    gold: "#ffd76a",
    blue: "#6fb5ff",
    purple: "#c08cff",
    green: "#7fe0a3",
    red: "#ff806f",
  };

  const friendlies = [
    actor("warrior", "Bulwark", 128, "friendly", 42, 42),
    actor("mage", "Hexa", 190, "friendly", 35, 35),
    actor("healer", "Mendly", 252, "friendly", 38, 38),
    actor("ranger", "Fletch", 314, "friendly", 36, 36),
  ];

  const enemies = [
    actor("slime", "Slime", 1662, "enemy", 30, 30),
    actor("goblin", "Goblin", 1720, "enemy", 38, 38),
    actor("ogre", "Ogre", 1792, "enemy", 92, 92),
  ];

  const state = {
    phase: "wander",
    startedAt: performance.now(),
    announcement: null,
    announcementUntil: 0,
    floaters: [],
    effects: [],
    encounter: 0,
  };

  function actor(kind, name, homeX, side, hp, maxHp) {
    return {
      kind, name, homeX, x: homeX, y: 78, side, hp, maxHp,
      visible: side === "friendly", defeated: false, action: null,
      flashUntil: 0, labelUntil: 0, walkOffset: Math.random() * Math.PI * 2,
    };
  }

  function resetBattle() {
    friendlies.forEach((item) => Object.assign(item, {
      hp: item.maxHp, defeated: false, visible: true, x: item.homeX, action: null,
    }));
    enemies.forEach((item) => Object.assign(item, {
      hp: item.maxHp, defeated: false, visible: false, x: item.homeX + 120, action: null,
    }));
    state.floaters = [];
    state.effects = [];
  }

  function announce(text, tone = "normal", duration = 2600) {
    state.announcement = { text, tone };
    state.announcementUntil = performance.now() + duration;
  }

  function setPhase(phase) {
    state.phase = phase;
    state.startedAt = performance.now();
  }

  function damage(target, amount) {
    target.hp = Math.max(0, target.hp - amount);
    target.flashUntil = performance.now() + 180;
    state.floaters.push({ x: target.x, y: 40, text: `-${amount}`, color: "#ff786d", born: performance.now() });
    if (target.hp === 0) target.defeated = true;
  }

  function heal(target, amount) {
    target.hp = Math.min(target.maxHp, target.hp + amount);
    state.floaters.push({ x: target.x, y: 40, text: `+${amount}`, color: "#8effad", born: performance.now() });
    state.effects.push({ kind: "sparkle", x: target.x, y: 58, born: performance.now(), color: "#8effad" });
  }

  function projectile(from, target, color) {
    state.effects.push({
      kind: "projectile", fromX: from.x, toX: target.x, x: from.x,
      y: 58, born: performance.now(), duration: 420, color,
    });
  }

  function runDemo(now) {
    const elapsed = now - state.startedAt;

    if (state.phase === "wander" && elapsed > 5200) {
      setPhase("arrival");
      state.encounter += 1;
      enemies.forEach((item) => { item.visible = true; });
      announce(state.encounter % 3 === 0 ? "A HEAVY FOOTSTEP SHAKES THE ROAD..." : "MONSTERS BLOCK THE ROAD", "danger");
    } else if (state.phase === "arrival") {
      enemies.forEach((item) => { item.x += (item.homeX - item.x) * 0.08; });
      if (elapsed > 3000) setPhase("warrior");
    } else if (state.phase === "warrior" && elapsed > 250) {
      setPhase("warrior-hit");
      friendlies[0].labelUntil = now + 1300;
      friendlies[0].action = { from: friendlies[0].homeX, to: enemies[0].x - 34, born: now, duration: 700 };
    } else if (state.phase === "warrior-hit" && elapsed > 420) {
      if (!state.didWarriorHit) {
        state.didWarriorHit = true;
        damage(enemies[0], 12);
      }
      if (elapsed > 1100) { state.didWarriorHit = false; setPhase("mage"); }
    } else if (state.phase === "mage" && elapsed > 300) {
      setPhase("mage-hit");
      friendlies[1].labelUntil = now + 1300;
      projectile(friendlies[1], enemies[1], palette.purple);
    } else if (state.phase === "mage-hit" && elapsed > 430) {
      if (!state.didMageHit) { state.didMageHit = true; damage(enemies[1], 14); }
      if (elapsed > 1050) { state.didMageHit = false; setPhase("enemy"); }
    } else if (state.phase === "enemy" && elapsed > 300) {
      setPhase("enemy-hit");
      enemies[2].labelUntil = now + 1300;
      enemies[2].action = { from: enemies[2].homeX, to: friendlies[0].x + 42, born: now, duration: 760 };
    } else if (state.phase === "enemy-hit" && elapsed > 460) {
      if (!state.didEnemyHit) { state.didEnemyHit = true; damage(friendlies[0], 19); }
      if (elapsed > 1150) { state.didEnemyHit = false; setPhase("healer"); }
    } else if (state.phase === "healer" && elapsed > 300) {
      setPhase("healer-hit");
      friendlies[2].labelUntil = now + 1300;
      heal(friendlies[0], 11);
    } else if (state.phase === "healer-hit" && elapsed > 1050) {
      setPhase("ranger");
    } else if (state.phase === "ranger" && elapsed > 300) {
      setPhase("ranger-hit");
      friendlies[3].labelUntil = now + 1300;
      projectile(friendlies[3], enemies[0], palette.gold);
    } else if (state.phase === "ranger-hit" && elapsed > 430) {
      if (!state.didRangerHit) { state.didRangerHit = true; damage(enemies[0], 18); }
      if (elapsed > 1150) { state.didRangerHit = false; setPhase("victory"); announce("VICTORY!  THE ROAD IS CLEAR", "victory", 3200); }
    } else if (state.phase === "victory" && elapsed > 3400) {
      announce("LOOT FOUND  •  18 XP  •  SLIME JELLY", "loot", 3400);
      state.effects.push({ kind: "loot", x: 960, y: 55, born: now, color: palette.gold });
      setPhase("loot");
    } else if (state.phase === "loot" && elapsed > 3900) {
      resetBattle();
      setPhase("wander");
    }
  }

  function updateActors(now) {
    const seconds = now / 1000;
    friendlies.forEach((item, index) => {
      if (state.phase === "wander") {
        item.x = item.homeX + Math.sin(seconds * 1.7 + item.walkOffset) * 5;
      } else if (!item.action) {
        item.x += (item.homeX - item.x) * 0.16;
      }
      item.y = 78 + Math.round(Math.sin(seconds * 3.2 + index) * (state.phase === "wander" ? 1.5 : 0.7));
      applyAction(item, now);
    });
    enemies.forEach((item, index) => {
      if (!item.action && state.phase !== "arrival") item.x += (item.homeX - item.x) * 0.16;
      item.y = 78 + Math.round(Math.sin(seconds * 2.7 + index) * 0.8);
      applyAction(item, now);
    });
  }

  function applyAction(item, now) {
    if (!item.action) return;
    const progress = Math.min(1, (now - item.action.born) / item.action.duration);
    const thereAndBack = Math.sin(progress * Math.PI);
    item.x = item.action.from + (item.action.to - item.action.from) * thereAndBack;
    if (progress >= 1) item.action = null;
  }

  function draw(now) {
    ctx.clearRect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT);
    drawGround();
    [...friendlies, ...enemies].forEach((item) => drawActor(item, now));
    drawEffects(now);
    drawFloaters(now);
    drawAnnouncement(now);
  }

  function drawGround() {
    ctx.save();
    ctx.globalAlpha = state.phase === "wander" ? 0.22 : 0.32;
    ctx.fillStyle = "rgba(135, 191, 173, 0.55)";
    for (let x = 28; x < LOGICAL_WIDTH; x += 46) {
      const height = 2 + ((x / 46) % 3);
      ctx.fillRect(x, 91 - height, 2, height);
    }
    ctx.fillStyle = "rgba(10, 20, 26, 0.4)";
    ctx.fillRect(0, 92, LOGICAL_WIDTH, 2);
    ctx.restore();
  }

  function drawActor(item, now) {
    if (!item.visible) return;
    ctx.save();
    ctx.translate(Math.round(item.x), Math.round(item.y));
    if (item.side === "enemy") ctx.scale(-1, 1);
    if (item.defeated) {
      ctx.globalAlpha = 0.35;
      ctx.rotate(item.side === "enemy" ? -Math.PI / 2 : Math.PI / 2);
    }
    if (item.flashUntil > now) ctx.globalCompositeOperation = "screen";
    drawSprite(item.kind);
    ctx.restore();
    drawHealth(item);
    if (item.labelUntil > now) drawName(item);
  }

  function block(x, y, width, height, color) {
    ctx.fillStyle = color;
    ctx.fillRect(x, y, width, height);
  }

  function drawSprite(kind) {
    const skin = "#f2bd83";
    const dark = "#172033";
    const boot = "#121725";
    if (kind === "slime") {
      block(-14, -18, 28, 16, "#64d6ba"); block(-10, -22, 20, 4, "#8ff0d6");
      block(-9, -13, 3, 4, dark); block(6, -13, 3, 4, dark); block(-14, -3, 7, 3, "#42a995"); block(7, -3, 7, 3, "#42a995");
      return;
    }
    if (kind === "goblin") {
      block(-11, -34, 22, 13, "#76b65d"); block(-18, -31, 7, 5, "#76b65d"); block(11, -31, 7, 5, "#76b65d");
      block(-8, -29, 3, 3, dark); block(5, -29, 3, 3, dark); block(-10, -21, 20, 15, "#8a4f3c");
      block(-9, -6, 7, 6, boot); block(2, -6, 7, 6, boot); block(11, -28, 3, 27, "#d0a75e"); block(10, -30, 10, 3, "#d0a75e");
      return;
    }
    if (kind === "ogre") {
      block(-18, -46, 36, 17, "#a379c4"); block(-15, -41, 4, 4, dark); block(11, -41, 4, 4, dark);
      block(-22, -29, 44, 23, "#75528f"); block(-16, -6, 12, 6, boot); block(4, -6, 12, 6, boot);
      block(20, -43, 7, 39, "#76512f"); block(17, -47, 20, 8, "#a57a45");
      return;
    }
    block(-8, -38, 16, 13, skin);
    block(-6, -34, 3, 3, dark); block(3, -34, 3, 3, dark);
    block(-9, -25, 18, 18, classColor(kind));
    block(-8, -7, 6, 7, boot); block(2, -7, 6, 7, boot);
    if (kind === "warrior") {
      block(-11, -43, 22, 6, "#9abce8"); block(9, -25, 12, 18, "#537eb8"); block(12, -22, 6, 12, "#8eb7e7");
      block(-14, -24, 3, 23, "#d9e5f2"); block(-18, -24, 11, 3, "#d9e5f2");
    } else if (kind === "mage") {
      block(-14, -43, 28, 5, "#8655bd"); block(-7, -51, 14, 9, "#a776da"); block(12, -28, 3, 27, "#8c6845"); block(10, -32, 7, 7, palette.purple);
    } else if (kind === "healer") {
      block(-9, -43, 18, 5, "#f1f0d4"); block(12, -28, 3, 27, "#9d7549"); block(9, -34, 9, 9, palette.green); block(-2, -22, 4, 10, "#f3f1d6"); block(-5, -19, 10, 4, "#f3f1d6");
    } else if (kind === "ranger") {
      block(-11, -42, 22, 5, "#547f55"); block(12, -30, 3, 28, "#b37942"); block(8, -28, 10, 3, "#d5a45c");
    } else {
      block(12, -27, 3, 26, "#b7bdc8"); block(8, -27, 11, 3, "#dce2ea");
    }
  }

  function classColor(kind) {
    return { warrior: "#4e7fbd", mage: "#7646a8", healer: "#4e9b72", ranger: "#8b5342", adventurer: "#9b744e" }[kind] || "#8b6a4b";
  }

  function drawHealth(item) {
    if (item.defeated || !item.visible) return;
    const width = item.kind === "ogre" ? 48 : 30;
    const x = Math.round(item.x - width / 2);
    const y = item.kind === "ogre" ? 24 : 31;
    block(x - 1, y - 1, width + 2, 5, palette.shadow);
    block(x, y, width, 3, palette.hpBack);
    const ratio = item.maxHp ? item.hp / item.maxHp : 0;
    block(x, y, Math.round(width * ratio), 3, ratio < 0.35 ? palette.hpLow : palette.hp);
  }

  function drawName(item) {
    ctx.save();
    ctx.font = "bold 11px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    const width = Math.ceil(ctx.measureText(item.name).width) + 10;
    const x = Math.round(item.x);
    block(x - width / 2, 3, width, 16, palette.shadow);
    ctx.fillStyle = palette.ink;
    ctx.fillText(item.name.toUpperCase(), x, 17);
    ctx.restore();
  }

  function drawFloaters(now) {
    state.floaters = state.floaters.filter((item) => now - item.born < 900);
    state.floaters.forEach((item) => {
      const progress = (now - item.born) / 900;
      ctx.save();
      ctx.globalAlpha = 1 - progress;
      ctx.font = "bold 14px monospace";
      ctx.textAlign = "center";
      ctx.lineWidth = 3;
      ctx.strokeStyle = palette.shadow;
      ctx.strokeText(item.text, item.x, item.y - progress * 18);
      ctx.fillStyle = item.color;
      ctx.fillText(item.text, item.x, item.y - progress * 18);
      ctx.restore();
    });
  }

  function drawEffects(now) {
    state.effects = state.effects.filter((item) => now - item.born < (item.kind === "loot" ? 3200 : 800));
    state.effects.forEach((item) => {
      const age = now - item.born;
      ctx.save();
      if (item.kind === "projectile") {
        const progress = Math.min(1, age / item.duration);
        item.x = item.fromX + (item.toX - item.fromX) * progress;
        ctx.globalAlpha = 1 - Math.max(0, progress - 0.8) * 5;
        block(Math.round(item.x) - 4, item.y - 2, 9, 4, item.color);
        block(Math.round(item.x) - 2, item.y - 5, 4, 10, "rgba(255,255,255,.7)");
      } else {
        const radius = item.kind === "loot" ? 12 + age / 90 : 4 + age / 60;
        ctx.globalAlpha = Math.max(0, 1 - age / (item.kind === "loot" ? 3200 : 800));
        ctx.strokeStyle = item.color;
        ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(item.x, item.y, radius, 0, Math.PI * 2); ctx.stroke();
        for (let angle = 0; angle < Math.PI * 2; angle += Math.PI / 4) {
          block(item.x + Math.cos(angle) * radius - 1, item.y + Math.sin(angle) * radius - 1, 3, 3, item.color);
        }
      }
      ctx.restore();
    });
  }

  function drawAnnouncement(now) {
    if (!state.announcement || state.announcementUntil <= now) return;
    const text = state.announcement.text;
    const tone = state.announcement.tone;
    ctx.save();
    ctx.font = "bold 14px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const width = Math.min(660, Math.ceil(ctx.measureText(text).width) + 38);
    const x = LOGICAL_WIDTH / 2 - width / 2;
    block(x, 4, width, 24, "rgba(6, 10, 20, 0.88)");
    block(x, 4, width, 2, tone === "danger" ? palette.red : tone === "victory" || tone === "loot" ? palette.gold : palette.blue);
    ctx.fillStyle = tone === "loot" ? palette.gold : palette.ink;
    ctx.fillText(text, LOGICAL_WIDTH / 2, 17);
    ctx.restore();
  }

  function frame(now) {
    runDemo(now);
    updateActors(now);
    draw(now);
    requestAnimationFrame(frame);
  }

  resetBattle();
  window.rpgMicroDemo = { state, friendlies, enemies, announce, setPhase, resetBattle };
  requestAnimationFrame(frame);
})();
