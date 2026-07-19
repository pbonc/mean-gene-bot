(() => {
  "use strict";
  const root = document.getElementById("battle");
  const friendlyEl = document.getElementById("friendlies");
  const enemyEl = document.getElementById("enemies");
  const promptEl = document.getElementById("prompt");
  const params = new URLSearchParams(location.search);
  let snapshot = null;

  const palettes = { adventurer: "#a87949", warrior: "#4f78bd", mage: "#7b4db5", healer: "#e9e1bd", ranger: "#4e8053", slime: "#55cfba", goblin: "#72a74d", ogre: "#8658a5" };
  const skills = { adventurer: ["Strike","Brace","Rally"], warrior: ["Slash","Guard Ally","Shield Slam"], mage: ["Arcane Bolt","Fireball","Focus"], healer: ["Smite","Heal","Group Heal"], ranger: ["Quick Shot","Mark Target","Volley"] };

  function actor(id, name, kind, side, hp = 30) { return { actor_id:id, name, kind, side, hp, max_hp:hp, shield:0, alive:true }; }
  function fixture(size) {
    const counts = size === "crowded" ? [30, 14] : size === "medium" ? [10, 7] : [4, 3];
    const kinds = ["warrior","mage","healer","ranger","adventurer"];
    const foes = ["slime","goblin","ogre"];
    const friendlies = Array.from({length:counts[0]}, (_,i) => actor(`f${i}`, ["Iamdar","Mira","Thorn","Pip","Nova"][i%5] + (i > 4 ? ` ${i+1}` : ""), kinds[i%5], "friendly", 30 + i%3*8));
    const enemies = Array.from({length:counts[1]}, (_,i) => actor(`e${i}`, `${foes[i%3][0].toUpperCase()+foes[i%3].slice(1)} ${i+1}`, foes[i%3], "enemy", 24 + i%3*20));
    return { type:"rpg_v2_battle_snapshot", battle_id:"demo-battle", phase:"actor_choice", round:2, friendlies, enemies, pending_turn:{ actor_id:"f0", choices:skills.warrior.map((label,i)=>({number:i+1,label})), waits_for_viewer:true }, last_event_sequence:0, result:null };
  }

  function layout(container, count) {
    const cols = Math.max(2, Math.ceil(Math.sqrt(count * 1.45)));
    const rows = Math.max(1, Math.ceil(count / cols));
    container.style.setProperty("--cols", cols);
    container.style.setProperty("--rows", rows);
    container.style.setProperty("--size", `${Math.max(2.2, Math.min(4.2, 11 / Math.sqrt(Math.max(1, count))))}vw`);
  }

  function actorNode(data) {
    const node = document.createElement("div");
    node.className = `actor ${data.side}${data.hp <= 0 ? " ko" : ""}`;
    node.dataset.actorId = data.actor_id;
    node.style.setProperty("--color", palettes[data.kind] || "#79859c");
    node.innerHTML = `<span class="hp"><i style="--hp:${Math.max(0, data.hp/data.max_hp*100)}%"></i></span><span class="name"></span>`;
    node.querySelector(".name").textContent = data.name;
    return node;
  }

  function render(data) {
    if (!data || data.type !== "rpg_v2_battle_snapshot" || !data.battle_id) return;
    snapshot = data;
    root.classList.remove("dormant");
    document.getElementById("round").textContent = `ROUND ${data.round}`;
    document.getElementById("encounter").textContent = "ENCOUNTER";
    document.getElementById("pace").textContent = data.friendlies.length + data.enemies.length > 24 ? "QUICK PACE" : "NORMAL PACE";
    friendlyEl.replaceChildren(...data.friendlies.map(actorNode));
    enemyEl.replaceChildren(...data.enemies.map(actorNode));
    layout(friendlyEl, data.friendlies.length); layout(enemyEl, data.enemies.length);
    showPrompt(data.pending_turn);
    document.getElementById("result").textContent = data.result ? data.result.toUpperCase() : "";
  }

  function showPrompt(turn) {
    document.querySelectorAll(".crowd .actor.acting, .crowd .actor.on-stage").forEach(node => node.classList.remove("acting", "on-stage"));
    const friendlyStage = document.getElementById("friendly-action");
    const enemyStage = document.getElementById("enemy-action");
    friendlyStage.replaceChildren(); enemyStage.replaceChildren();
    if (!turn) { promptEl.hidden = true; return; }
    promptEl.hidden = false;
    const acting = [...(snapshot?.friendlies || []), ...(snapshot?.enemies || [])].find(a => a.actor_id === turn.actor_id);
    const crowdNode = document.querySelector(`[data-actor-id="${CSS.escape(turn.actor_id)}"]`);
    if (crowdNode && acting) {
      crowdNode.classList.add("acting", "on-stage");
      const stageNode = actorNode(acting);
      stageNode.classList.add("acting");
      stageNode.querySelector(".name").remove();
      (acting.side === "friendly" ? friendlyStage : enemyStage).append(stageNode);
    }
    document.getElementById("actor-name").textContent = acting?.name || "Current actor";
    document.getElementById("instruction").textContent = turn.waits_for_viewer ? "TYPE 1, 2, OR 3 IN CHAT" : "DEFAULT ACTION";
    document.getElementById("skills").replaceChildren(...(turn.choices || []).map(choice => {
      const li = document.createElement("li"); li.innerHTML = `<b>${choice.number}</b>`; li.append(document.createTextNode(choice.label)); return li;
    }));
  }

  function connect() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${location.host}/ws`);
    socket.addEventListener("open", () => socket.send(JSON.stringify({type:"request_rpg_v2_battle"})));
    socket.addEventListener("message", event => { try { render(JSON.parse(event.data)); } catch (_) {} });
    socket.addEventListener("close", () => setTimeout(connect, 1500));
  }

  const demo = params.get("demo");
  if (["small","medium","crowded"].includes(demo)) render(fixture(demo));
  else connect();
})();
