const form = document.querySelector('form');
form.addEventListener('submit', async event => {
  event.preventDefault();
  const password = form.elements.password.value;
  form.reset();
  try {
    const response = await fetch('/control/login', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':form.dataset.csrf}, body:JSON.stringify({password})});
    if (response.ok) location.replace('/control/');
    else { document.querySelector('#message').textContent = 'Sign in failed. Reload this page to try again.'; }
  } catch { document.querySelector('#message').textContent = 'Control Center unavailable.'; }
});
