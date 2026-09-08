let csrf = '';
const cards = document.querySelector('#cards');
const names = {'dashboard':'Dashboard','commands':'Commands','wheel':'Wheel','raffle':'Raffle','lore':'Lore','hermes':'Hermes','audio-media':'Audio/Media','logs':'Logs','settings':'Settings'};
function page() {
  const key = location.hash.slice(1) || 'dashboard';
  document.querySelector('#title').textContent = names[key] || 'Dashboard';
  const dashboard = !names[key] || key === 'dashboard';
  cards.hidden = !dashboard;
  document.querySelector('#notice').textContent = dashboard ? 'Observed runtime evidence; no provider health probes.' : 'Sprint 1 placeholder · Read-only. No controls are available on this page.';
  document.querySelectorAll('nav a').forEach(a => a.setAttribute('aria-current', a.hash === '#' + key ? 'page' : 'false'));
}
async function refresh() {
  try {
    const response = await fetch('/control/api/status');
    if (response.status === 401) { location.replace('/control/login'); return; }
    if (!response.ok) throw new Error();
    const data = await response.json(); csrf = data.csrf;
    document.querySelector('#status').textContent = `MeanGene: ${data.status.meangene} · Channel: ${data.status.channels.join(', ') || 'unknown'}`;
    cards.replaceChildren();
    for (const service of data.status.services) {
      const card = document.createElement('article');
      for (const [tag, value] of [['h2', service.name], ['strong', service.state.replaceAll('_',' ')], ['p', service.detail]]) {
        const element = document.createElement(tag); element.textContent = value; card.append(element);
      }
      if (service.reconnect) {
        const button = document.createElement('button'); button.textContent = 'Reconnect'; button.disabled = true;
        const reason = document.createElement('p'); reason.textContent = service.reconnect.reason;
        card.append(button, reason);
      }
      cards.append(card);
    }
  } catch { document.querySelector('#status').textContent = 'MeanGene: unknown · Channel: unknown · Status unavailable'; cards.replaceChildren(); }
}
document.querySelector('#logout').addEventListener('click', async () => {
  try {
    const response = await fetch('/control/logout', {method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:'{}'});
    if (response.ok || response.status === 401) location.replace('/control/login');
    else document.querySelector('#notice').textContent = 'Sign out failed. Refresh and retry.';
  } catch { document.querySelector('#notice').textContent = 'Sign out unavailable. Refresh and retry.'; }
});
addEventListener('hashchange', page); page(); refresh(); setInterval(refresh, 10000);
