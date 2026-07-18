(() => {
  "use strict";

  const WIDTH = 1920;
  const HEIGHT = 96;
  const TRAVEL_SPEED_PX_PER_SECOND = 26;
  const EVENT_APPROACH_DISTANCE = 140;
  const EVENT_APPROACH_SECONDS = EVENT_APPROACH_DISTANCE / TRAVEL_SPEED_PX_PER_SECOND;
  const canvas = document.getElementById("micro-strip");
  const ctx = canvas.getContext("2d", { alpha: true });
  ctx.imageSmoothingEnabled = false;

  const params = new URLSearchParams(window.location.search);
  const initialMode = ["normal", "quiet", "hidden"].includes(params.get("mode"))
    ? params.get("mode")
    : "normal";

  const colors = {
    ink: "#fff7d6",
    shadow: "rgba(4, 8, 18, 0.82)",
    gold: "#ffd76a",
    blue: "#6fb5ff",
    purple: "#c08cff",
    green: "#7fe0a3",
    red: "#ff806f",
    ground: "rgba(90, 142, 126, 0.32)",
  };

  const expedition = [
    member("adventurer", "Newblood"),
    member("healer", "Mendly"),
    member("mage", "Hexa"),
    member("adventurer", "Wayfarer"),
    member("ranger", "Fletch"),
    member("adventurer", "Pip"),
    member("mage", "Ember"),
    member("healer", "Moss"),
    member("ranger", "Quill"),
    member("warrior", "Bulwark"),
  ];

  const state = {
    mode: initialMode,
    ambient: "journey",
    ambientStartedAt: performance.now(),
    cycleStartedAt: performance.now(),
    lastFrameAt: performance.now(),
    announcement: null,
    announcementUntil: 0,
    joinHighlight: null,
    joinHighlightUntil: 0,
    background: [
      backgroundItem("tree", 760),
      backgroundItem("rock", 1100),
      backgroundItem("ruin", 1490),
      backgroundItem("tree", 1870),
    ],
  };

  function backgroundItem(kind, x) {
    return { kind, x };
  }

  function member(kind, name) {
    return {
      actor_id: name.toLowerCase(),
      kind,
      name,
      x: 0,
      y: 88,
      scale: 1,
      row: 0,
      phaseOffset: Math.random() * Math.PI * 2,
    };
  }

  function classPriority(kind) {
    return { healer: 0, mage: 1, adventurer: 2, ranger: 3, warrior: 4 }[kind] ?? 2;
  }

  function layoutExpedition() {
    const ordered = [...expedition].sort((a, b) => classPriority(a.kind) - classPriority(b.kind));
    const count = ordered.length;
    const rows = Math.min(3, Math.max(1, Math.ceil(count / 14)));
    const columns = Math.max(1, Math.ceil(count / rows));
    const scale = count <= 12 ? 1 : count <= 28 ? 0.78 : 0.58;
    const availableWidth = 610;
    const spacing = columns === 1 ? 0 : Math.min(48 * scale, availableWidth / (columns - 1));

    ordered.forEach((actor, index) => {
      const row = index % rows;
      const column = Math.floor(index / rows);
      actor.row = row;
      actor.scale = scale * (1 - row * 0.06);
      actor.x = 60 + column * spacing + row * 11;
      actor.y = 91 - row * 24 * scale;
    });
  }

  function addMember(kind, name) {
    const cleanName = String(name || "Traveler").trim().slice(0, 24) || "Traveler";
    const actor = member(kind, cleanName);
    expedition.push(actor);
    state.joinHighlight = actor.actor_id;
    state.joinHighlightUntil = performance.now() + 3200;
    announce(`${cleanName.toUpperCase()} JOINS THE EXPEDITION`, "join", 3200);
    layoutExpedition();
    return actor;
  }

  function removeMember(actorId) {
    const index = expedition.findIndex((actor) => actor.actor_id === actorId);
    if (index < 0) return false;
    expedition.splice(index, 1);
    layoutExpedition();
    return true;
  }

  function announce(text, tone = "normal", duration = 3200) {
    if (state.mode === "quiet" || state.mode === "hidden") return;
    state.announcement = { text, tone };
    state.announcementUntil = performance.now() + duration;
  }

  function setAmbientState(next, options = {}) {
    const allowed = ["journey", "treasure", "camp", "merchant", "encounter_ready"];
    if (!allowed.includes(next)) throw new Error(`Unknown ambient state: ${next}`);
    if (state.ambient === next && !options.force) return;
    state.ambient = next;
    state.ambientStartedAt = performance.now();

    if (options.announce === false) return;
    const messages = {
      treasure: ["A TREASURE CHEST APPEARS", "loot"],
      camp: ["THE EXPEDITION MAKES CAMP", "camp"],
      merchant: ["A TRAVELING MERCHANT PASSES BY", "merchant"],
      encounter_ready: ["ENCOUNTER READY  •  WAITING FOR THE STREAMER", "danger"],
    };
    if (messages[next]) announce(messages[next][0], messages[next][1], next === "encounter_ready" ? 5200 : 3400);
  }

  function setMode(mode) {
    if (!["normal", "quiet", "hidden"].includes(mode)) throw new Error(`Unknown display mode: ${mode}`);
    state.mode = mode;
    if (mode !== "normal") {
      state.announcement = null;
      state.announcementUntil = 0;
    }
  }

  function runPlaceholderCycle(now) {
    if (state.mode === "hidden") return;
    const elapsed = (now - state.cycleStartedAt) % 90000;
    let next = "journey";
    if (elapsed >= 30000 && elapsed < 37000) next = "treasure";
    else if (elapsed >= 52000 && elapsed < 65000) next = "camp";
    else if (elapsed >= 70000 && elapsed < 77000) next = "merchant";
    else if (elapsed >= 80000) next = "encounter_ready";
    setAmbientState(next);
  }

  function draw(now) {
    ctx.clearRect(0, 0, WIDTH, HEIGHT);
    if (state.mode === "hidden") return;

    drawGround();
    drawBackground();
    drawProp(now);
    drawExpedition(now);
    drawAnnouncement(now);
  }

  function updateBackground(now) {
    const elapsedSeconds = Math.min(0.05, Math.max(0, (now - state.lastFrameAt) / 1000));
    state.lastFrameAt = now;
    const eventAge = (now - state.ambientStartedAt) / 1000;
    const approachingEvent = ["treasure", "merchant", "encounter_ready"].includes(state.ambient)
      && eventAge < EVENT_APPROACH_SECONDS;
    if (state.mode !== "normal" || (state.ambient !== "journey" && !approachingEvent)) return;
    state.background.forEach((item) => {
      item.x -= TRAVEL_SPEED_PX_PER_SECOND * elapsedSeconds;
      if (item.x < -70) item.x = WIDTH + 120 + Math.random() * 340;
    });
  }

  function drawGround() {
    ctx.save();
    ctx.fillStyle = colors.ground;
    ctx.fillRect(0, 92, WIDTH, 2);
    ctx.globalAlpha = 0.22;
    for (let x = 22; x < WIDTH; x += 52) {
      block(x, 88, 2, 4, "#72aa83");
      block(x - 3, 90, 3, 2, "#72aa83");
      block(x + 2, 89, 3, 2, "#72aa83");
    }
    ctx.restore();
  }

  function drawBackground() {
    if (state.mode !== "normal") return;
    ctx.save();
    state.background.forEach((item) => {
      const x = Math.round(item.x);
      if (item.kind === "tree") {
        block(x - 3, 91 - 30, 6, 30, "#5e432e");
        block(x - 12, 91 - 42, 24, 15, "#397452");
        block(x - 8, 91 - 50, 16, 10, "#56a070");
        block(x - 5, 91 - 47, 10, 3, "#75bd89");
      } else if (item.kind === "ruin") {
        block(x - 21, 91 - 28, 8, 28, "#697572");
        block(x + 12, 91 - 20, 8, 20, "#697572");
        block(x - 23, 91 - 32, 44, 6, "#a4b0ac");
        block(x - 18, 91 - 27, 4, 25, "#8e9a96");
        block(x - 7, 91 - 14, 19, 14, "#394443");
      } else {
        block(x - 10, 91 - 7, 20, 7, "#65716f");
        block(x - 6, 91 - 11, 12, 5, "#a6b1ad");
        block(x - 3, 91 - 10, 7, 2, "#c1cac6");
      }
    });
    ctx.restore();
  }

  function drawExpedition(now) {
    const seconds = now / 1000;
    const ordered = [...expedition].sort((a, b) => a.row - b.row || a.x - b.x);
    ordered.forEach((actor) => {
      let bob = 0;
      if (state.ambient === "journey") bob = Math.round(Math.sin(seconds * 3.1 + actor.phaseOffset) * 1.4);
      else if (state.ambient === "treasure" || state.ambient === "merchant") bob = Math.round(Math.sin(seconds * 2.2 + actor.phaseOffset) * 0.6);

      ctx.save();
      ctx.translate(Math.round(actor.x), Math.round(actor.y + bob));
      ctx.scale(actor.scale, actor.scale);
      drawSprite(actor.kind);
      ctx.restore();

      if (state.joinHighlight === actor.actor_id && state.joinHighlightUntil > now) {
        drawNameplate(actor, now);
      }
    });
  }

  function drawProp(now) {
    if (state.mode === "quiet") return;
    const age = (now - state.ambientStartedAt) / 1000;
    if (state.ambient === "treasure") drawEnteringEvent(age, 940, 6.4, (x) => drawChest(x, 90, age));
    else if (state.ambient === "camp") drawCamp(870, 92, age);
    else if (state.ambient === "merchant") drawEnteringEvent(age, 930, 6.3, (x) => drawMerchant(x, 90, age));
    else if (state.ambient === "encounter_ready") drawEnteringEvent(age, 1560, Infinity, (x) => drawEncounter(x, 92, age));
  }

  function drawEnteringEvent(age, stopX, fadeAt, renderer) {
    const x = Math.max(stopX, stopX + EVENT_APPROACH_DISTANCE - TRAVEL_SPEED_PX_PER_SECOND * age);
    ctx.save();
    if (age > fadeAt) ctx.globalAlpha = Math.max(0, 1 - (age - fadeAt) / 0.6);
    renderer(x);
    ctx.restore();
  }

  function drawChest(x, y, age) {
    const bob = Math.round(Math.sin(age * 3) * 1.5);
    block(x - 16, y - 18 + bob, 32, 16, "#8c592f");
    block(x - 18, y - 20 + bob, 36, 7, "#b47738");
    block(x - 3, y - 16 + bob, 6, 9, colors.gold);
    if (age < 3.5) {
      block(x - 24, y - 28 + bob, 3, 3, colors.gold);
      block(x + 21, y - 31 + bob, 3, 3, colors.gold);
    }
  }

  function drawCamp(x, y, age) {
    const flame = Math.round(Math.sin(age * 9) * 2);
    block(x - 28, y - 5, 56, 3, "rgba(86, 63, 46, 0.76)");
    block(x - 7, y - 14 - flame, 14, 11 + flame, "#ff9b4f");
    block(x - 4, y - 11 - flame, 8, 8 + flame, "#ffe06a");
    block(x - 36, y - 25, 3, 22, "#9a7653");
    block(x - 36, y - 27, 38, 3, "#9a7653");
    block(x - 31, y - 24, 28, 14, "rgba(76, 117, 92, 0.82)");
  }

  function drawMerchant(x, y, age) {
    const bob = Math.round(Math.sin(age * 2.4) * 1);
    ctx.save();
    ctx.translate(x, y + bob);
    drawSprite("merchant");
    ctx.restore();
    block(x + 18, y - 18, 22, 16, "#76502f");
    block(x + 15, y - 20, 28, 5, "#b47a3e");
    block(x + 24, y - 15, 6, 6, colors.gold);
  }

  function drawEncounter(x, y, age) {
    const pulse = 0.68 + Math.sin(age * 3) * 0.12;
    ctx.save();
    ctx.globalAlpha = pulse;
    ctx.translate(x - 35, y);
    ctx.scale(-1, 1);
    drawSprite("slime");
    ctx.restore();
    ctx.save();
    ctx.globalAlpha = pulse;
    ctx.translate(x + 30, y);
    ctx.scale(-1, 1);
    drawSprite("goblin");
    ctx.restore();
    ctx.font = "bold 16px monospace";
    ctx.textAlign = "center";
    ctx.fillStyle = colors.red;
    ctx.fillText("!", x, 42);
  }

  function drawNameplate(actor) {
    ctx.save();
    ctx.font = "bold 11px monospace";
    ctx.textAlign = "center";
    const label = actor.name.toUpperCase();
    const width = Math.ceil(ctx.measureText(label).width) + 12;
    const x = actor.x;
    block(x - width / 2, 4, width, 17, colors.shadow);
    block(x - width / 2, 19, width, 2, classColor(actor.kind));
    ctx.fillStyle = colors.ink;
    ctx.fillText(label, x, 17);
    ctx.restore();
  }

  function drawAnnouncement(now) {
    if (!state.announcement || state.announcementUntil <= now || state.mode !== "normal") return;
    const text = state.announcement.text;
    const tone = state.announcement.tone;
    ctx.save();
    ctx.font = "bold 14px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const width = Math.min(720, Math.ceil(ctx.measureText(text).width) + 40);
    const x = WIDTH / 2 - width / 2;
    block(x, 4, width, 24, colors.shadow);
    block(x, 4, width, 2, toneColor(tone));
    ctx.fillStyle = tone === "loot" ? colors.gold : colors.ink;
    ctx.fillText(text, WIDTH / 2, 17);
    ctx.restore();
  }

  function toneColor(tone) {
    return { danger: colors.red, loot: colors.gold, camp: colors.green, merchant: colors.purple, join: colors.blue }[tone] || colors.blue;
  }

  function block(x, y, width, height, color) {
    ctx.fillStyle = color;
    ctx.fillRect(Math.round(x), Math.round(y), Math.round(width), Math.round(height));
  }

  function drawSprite(kind) {
    const skin = "#f2bd83";
    const dark = "#172033";
    const boot = "#121725";

    if (kind === "slime") {
      block(-14, -18, 28, 16, "#64d6ba"); block(-10, -22, 20, 4, "#8ff0d6");
      block(-9, -13, 3, 4, dark); block(6, -13, 3, 4, dark);
      return;
    }
    if (kind === "goblin") {
      block(-11, -34, 22, 13, "#76b65d"); block(-18, -31, 7, 5, "#76b65d"); block(11, -31, 7, 5, "#76b65d");
      block(-8, -29, 3, 3, dark); block(5, -29, 3, 3, dark); block(-10, -21, 20, 15, "#8a4f3c");
      block(-9, -6, 7, 6, boot); block(2, -6, 7, 6, boot); block(11, -28, 3, 27, "#d0a75e");
      return;
    }
    if (kind === "merchant") {
      block(-8, -38, 16, 13, skin); block(-6, -34, 3, 3, dark); block(3, -34, 3, 3, dark);
      block(-12, -25, 24, 18, "#9d6bb5"); block(-9, -7, 7, 7, boot); block(2, -7, 7, 7, boot);
      block(-12, -42, 24, 5, "#69477a");
      return;
    }

    block(-8, -38, 16, 13, skin);
    block(-6, -34, 3, 3, dark); block(3, -34, 3, 3, dark);
    block(-9, -25, 18, 18, classColor(kind));
    block(-8, -7, 6, 7, boot); block(2, -7, 6, 7, boot);
    if (kind === "warrior") {
      block(-11, -43, 22, 6, "#9abce8"); block(9, -25, 12, 18, "#537eb8"); block(12, -22, 6, 12, "#8eb7e7");
    } else if (kind === "mage") {
      block(-14, -43, 28, 5, "#8655bd"); block(-7, -51, 14, 9, "#a776da"); block(12, -28, 3, 27, "#8c6845"); block(10, -32, 7, 7, colors.purple);
    } else if (kind === "healer") {
      block(-9, -43, 18, 5, "#f1f0d4"); block(12, -28, 3, 27, "#9d7549"); block(9, -34, 9, 9, colors.green); block(-2, -22, 4, 10, "#f3f1d6"); block(-5, -19, 10, 4, "#f3f1d6");
    } else if (kind === "ranger") {
      block(-11, -42, 22, 5, "#547f55"); block(12, -30, 3, 28, "#b37942"); block(8, -28, 10, 3, "#d5a45c");
    } else {
      block(12, -27, 3, 26, "#b7bdc8"); block(8, -27, 11, 3, "#dce2ea");
    }
  }

  function classColor(kind) {
    return { warrior: "#4e7fbd", mage: "#7646a8", healer: "#4e9b72", ranger: "#8b5342", adventurer: "#9b744e" }[kind] || "#8b6a4b";
  }

  function frame(now) {
    runPlaceholderCycle(now);
    updateBackground(now);
    draw(now);
    requestAnimationFrame(frame);
  }

  layoutExpedition();
  window.rpgMicro = {
    state,
    expedition,
    addMember,
    removeMember,
    setAmbientState,
    setMode,
    announce,
    relayout: layoutExpedition,
  };
  requestAnimationFrame(frame);
})();
