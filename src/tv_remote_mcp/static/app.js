'use strict';
const icons = {
  tv: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>',
  network: '<path d="M3 8a15 15 0 0 1 18 0M6 12a10 10 0 0 1 12 0m-9 4a5 5 0 0 1 6 0"/><circle cx="12" cy="20" r=".6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', minus: '<path d="M5 12h14"/>',
  up: '<path d="m6 15 6-6 6 6"/>', down: '<path d="m6 9 6 6 6-6"/>',
  left: '<path d="m15 6-6 6 6 6"/>', right: '<path d="m9 6 6 6-6 6"/>',
  power: '<path d="M12 3v9m-5-7a8 8 0 1 0 10 0"/>',
  moon: '<path d="M20 14a8 8 0 0 1-10-10 8.2 8.2 0 1 0 10 10Z"/>',
  home: '<path d="m3 10 9-7 9 7M5 9v12h5v-7h4v7h5V9"/>',
  input: '<path d="M13 4h7v16h-7M3 12h12m-4-4 4 4-4 4"/>',
  back: '<path d="m8 4-5 5 5 5M3 9h11a6 6 0 0 1 0 12h-3"/>',
  mute: '<path d="M11 4 6 8H3v8h3l5 4V4Zm5 5 5 6m0-6-5 6"/>',
  play: '<path d="m8 4 12 8-12 8V4Z"/>', pause: '<path d="M8 5v14M16 5v14"/>',
  rewind: '<path d="m11 5-9 7 9 7V5Zm10 0-9 7 9 7V5Z"/>',
  forward: '<path d="m3 5 9 7-9 7V5Zm10 0 9 7-9 7V5Z"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 14 6M4 12a8 8 0 0 0 14 6"/>',
  link: '<path d="m10 13 4-4m-6 7-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 9a4 4 0 0 0 6 0l4-4a4 4 0 0 0-6-6l-1 1"/>',
  art: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 6-5 4 3 4-6 4 5"/>',
  apps: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  code: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-14-2 16"/>',
  external: '<path d="M14 3h7v7m0-7L10 14M10 3H4v17h17v-6"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
};
const $ = id => document.getElementById(id);
function icon(name) {
  const span = document.createElement('span');
  span.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.tv}</svg>`;
  return span;
}
document.querySelectorAll('[data-icon]').forEach(node => node.append(icon(node.dataset.icon)));
let tvs = [], selected = null, busy = false, accessToken = '', activity = [];
let statusSequence = 0, controlsEnabled = true;
const current = () => tvs.find(tv => tv.id === selected);
function notice(text, error = false) {
  const node = $('message'); node.textContent = text; node.hidden = !text;
  node.classList.toggle('error', error);
}
function log(label, failed = false) {
  activity.unshift({label, failed, time: new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})});
  activity = activity.slice(0, 6);
  $('activity-list').replaceChildren(...activity.map(item => {
    const li = document.createElement('li'), dot = document.createElement('span'), text = document.createElement('span'), time = document.createElement('time');
    dot.className = `activity-dot${item.failed ? ' failed' : ''}`; text.textContent = item.label; time.textContent = item.time;
    li.append(dot, text, time); return li;
  }));
}
async function api(path, data) {
  const headers = {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (data !== undefined) Object.assign(headers, {'Content-Type': 'application/json', 'X-TV-Remote': '1'});
  const response = await fetch(path, {method: data === undefined ? 'GET' : 'POST', headers, body: data === undefined ? undefined : JSON.stringify(data), cache: 'no-store'});
  const result = await response.json().catch(() => ({error: 'The server could not complete this request.'}));
  if (response.status === 401 && !$('auth-dialog').open) $('auth-dialog').showModal();
  if (!response.ok) throw new Error(result.error || 'Request failed. Check the server and try again.');
  return result;
}
function updateControls() {
  const tv = current();
  document.querySelectorAll('button').forEach(button => {
    if (button.closest('dialog')) return;
    button.disabled = busy;
  });
  document.querySelectorAll('[data-paired]').forEach(node => node.disabled = busy || !controlsEnabled || tv?.enabled === false || !tv || (!tv.token_saved && tv.port !== 8001));
  $('wake').disabled = busy || !controlsEnabled || tv?.enabled === false || !tv?.mac;
  ['pair-main', 'pair-again'].forEach(id => $(id).disabled = busy || !controlsEnabled || tv?.enabled === false);
  // Kill switches remain usable while a slow command is in flight.
  $('master-switch').disabled = false; $('device-switch').disabled = !tv;
  $('wake').title = tv?.mac ? 'Send a Wake-on-LAN packet' : 'No MAC address saved; discover this TV while powered on';
}
function renderList() {
  $('tv-count').textContent = String(tvs.length);
  if (!tvs.length) {const p = document.createElement('p'); p.className = 'muted small'; p.textContent = 'No televisions added yet.'; $('tv-list').replaceChildren(p); return;}
  $('tv-list').replaceChildren(...tvs.map(tv => {
    const button = document.createElement('button'); button.className = `tv-item${tv.id === selected ? ' selected' : ''}`;
    button.setAttribute('aria-current', tv.id === selected ? 'true' : 'false');
    const graphic = icon('tv'); graphic.className = 'tv-icon';
    const text = document.createElement('span'), name = document.createElement('strong'), detail = document.createElement('small');
    name.textContent = tv.name; detail.textContent = tv.enabled === false ? 'Controls disabled' : tv.token_saved ? 'Token saved' : 'Ready to pair';
    text.append(name, detail); button.append(graphic, text); button.addEventListener('click', () => select(tv.id)); return button;
  }));
}
function resetArt() {
  $('art-status').textContent = 'State not checked';
  $('art-on').classList.remove('active'); $('art-off').classList.remove('active');
}
function select(id, refresh = true) {
  selected = id; const tv = current(); ++statusSequence;
  renderList(); $('empty').hidden = Boolean(tv); $('device').hidden = !tv;
  if (!tv) {updateControls(); return;}
  $('control-state').textContent = tv.enabled === false ? 'Device controls disabled' : controlsEnabled ? 'Device controls enabled' : 'All controls disabled';
  $('device-switch').textContent = tv.enabled === false ? 'Enable device' : 'Disable device';
  $('breadcrumb-tv').textContent = tv.name; $('device-name').textContent = tv.name;
  $('device-kind').textContent = tv.frame ? 'SAMSUNG · THE FRAME' : 'SAMSUNG TELEVISION';
  $('device-model').textContent = tv.model || 'Samsung Smart TV'; $('device-address').textContent = tv.host;
  $('device-power').textContent = 'Unknown'; $('device-pairing').textContent = tv.token_saved ? 'Saved on this computer' : 'Not saved';
  $('connection-status').textContent = 'Not checked'; $('connection-status').className = 'pill';
  $('last-checked').textContent = 'Status not checked yet'; $('pairing-banner').hidden = tv.token_saved;
  $('pair-again').firstChild.textContent = tv.token_saved ? 'Pair again' : 'Pair television';
  $('remote-caption').textContent = !controlsEnabled || tv.enabled === false ? 'Controls disabled' : tv.token_saved ? 'Ready for commands' : 'Pairing needed';
  $('remote-help').textContent = !controlsEnabled || tv.enabled === false ? 'A kill switch is blocking device commands.' : tv.token_saved ? 'Commands are sent directly over your home network.' : 'Pair your TV to unlock the remote.';
  $('art-panel').hidden = !tv.frame; resetArt();
  ['apps', 'artworks'].forEach(name => {$(name).replaceChildren(); $(name).hidden = true;});
  updateControls();
  if (refresh) refreshStatus().catch(error => notice(error.message, true));
}
async function loadState(refresh = true) {
  const state = await api('/api/state'); tvs = state.tvs; controlsEnabled = state.controls_enabled !== false;
  $('master-switch').textContent = controlsEnabled ? 'Disable all controls' : 'Enable all controls';
  $('master-state').textContent = controlsEnabled ? 'Master switch: enabled' : 'Master switch: disabled';
  $('subnet').value = state.subnet;
  const id = tvs.some(tv => tv.id === selected) ? selected : tvs[0]?.id;
  select(id || null, refresh); return state;
}
async function refreshStatus() {
  const id = selected, sequence = ++statusSequence;
  if (!id) return;
  $('connection-status').textContent = 'Checking…';
  const state = await api(`/api/tvs/${encodeURIComponent(id)}/status`);
  if (id !== selected || sequence !== statusSequence) return;
  const matched = state.reachable && state.identity_matches !== false;
  $('connection-status').textContent = matched ? 'Reachable' : state.reachable ? 'Identity changed' : 'Not reachable';
  $('connection-status').className = `pill${matched ? ' good' : ' bad'}`;
  $('device-power').textContent = state.power === 'on' ? 'On · TV or Art Mode' : state.power === 'off' ? 'Off' : 'Unknown';
  $('last-checked').textContent = `Checked ${new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
  if (state.identity_matches === false) notice('This address belongs to a different TV. Find televisions again before controlling it.', true);
}
async function run(label, operation, message = null) {
  if (busy) return null;
  busy = true; updateControls(); notice(message || `${label}…`);
  try {
    const result = await operation(); log(label);
    const detail = result?.status === 'command_sent' ? 'Command sent. Visible state is not confirmed.' : result?.status === 'wake_packet_sent' ? 'Wake packet sent. Refresh status in a few seconds.' : null;
    notice(detail || `${label} complete.`); return result;
  } catch (error) {notice(error.message, true); log(`${label} failed`, true); return null;}
  finally {busy = false; updateControls();}
}
function command(data, label, message) {
  const id = selected; if (!id) return Promise.resolve(null);
  return run(label, () => api(`/api/tvs/${encodeURIComponent(id)}/action`, data), message);
}
async function discover() {
  const result = await run('Network scan', async () => {
    const found = await api('/api/discover', {}); await loadState(false); return found;
  }, 'Looking for Samsung TVs on your network. This can take around 20 seconds.');
  if (result) notice(result.found.length ? `Found ${result.found.length} television${result.found.length === 1 ? '' : 's'}. Choose one to pair or control.` : 'No TVs responded. Turn them on, check the home subnet, and try again.');
  if (current()) refreshStatus().catch(error => notice(error.message, true));
}
async function setSwitch(path, enabled) {
  try {await api(path, {enabled}); await loadState(false); notice(enabled ? 'Controls enabled. Individual device switches still apply.' : 'Controls disabled across web and MCP. A command already sent cannot be recalled.'); log(enabled ? 'Controls enabled' : 'Kill switch enabled');}
  catch (error) {notice(error.message, true);}
}
$('master-switch').addEventListener('click', () => setSwitch('/api/controls', !controlsEnabled));
$('device-switch').addEventListener('click', () => {const tv = current(); if (tv) setSwitch(`/api/tvs/${encodeURIComponent(tv.id)}/controls`, tv.enabled === false);});
$('discover').addEventListener('click', discover); $('empty-discover').addEventListener('click', discover);
$('refresh').addEventListener('click', () => run('Status refresh', refreshStatus));
$('network-form').addEventListener('submit', event => {
  event.preventDefault(); run('Network saved', () => api('/api/network', {subnet: $('subnet').value.trim()}));
});
async function pair() {
  const result = await command({action: 'pair'}, 'TV pairing', 'Look at your TV and choose Allow for Samsung TV Remote MCP. Waiting up to 25 seconds…');
  if (result) {await loadState().catch(error => notice(error.message, true)); notice(result.token_saved ? 'Pairing token saved. Your remote is ready.' : 'Connected, but no token was saved. Check your TV authorization settings.');}
}
$('pair-main').addEventListener('click', pair); $('pair-again').addEventListener('click', pair);
document.querySelectorAll('[data-key]').forEach(button => button.addEventListener('click', () => command({action: 'key', key: button.dataset.key}, button.getAttribute('aria-label') || button.textContent.trim())));
$('wake').addEventListener('click', () => command({action: 'power', power: 'on'}, 'Wake request'));
$('power-off').addEventListener('click', () => {$('power-dialog').returnValue = ''; $('power-dialog').showModal();});
$('power-dialog').addEventListener('close', () => {if ($('power-dialog').returnValue === 'off') command({action: 'power', power: 'off'}, 'Power off');});
function showArt(result) {
  if (!result) return;
  const on = result.art_mode === 'on' || result.art_mode === true;
  const off = result.art_mode === 'off' || result.art_mode === false;
  $('art-status').textContent = on ? 'Art Mode is on' : off ? 'Art Mode is off' : 'State unknown';
  $('art-on').classList.toggle('active', on); $('art-off').classList.toggle('active', off);
  if ('requested' in result && ((result.requested && !on) || (!result.requested && !off))) notice('The reported Art Mode state does not match the request. Check the TV.', true);
}
$('art-refresh').addEventListener('click', async () => showArt(await command({action: 'art_status'}, 'Art Mode check')));
$('art-on').addEventListener('click', async () => showArt(await command({action: 'art_mode', enabled: true}, 'Enable Art Mode')));
$('art-off').addEventListener('click', async () => showArt(await command({action: 'art_mode', enabled: false}, 'Disable Art Mode')));
function itemList(id, items, title, onSelect, empty) {
  const container = $(id); container.replaceChildren(); container.hidden = false;
  if (!Array.isArray(items) || !items.length) {const p = document.createElement('p'); p.textContent = empty; container.append(p); return;}
  items.slice(0, 100).forEach(item => {
    const button = document.createElement('button'), label = document.createElement('span');
    label.textContent = title(item); button.append(label, icon('right')); button.addEventListener('click', () => onSelect(item)); container.append(button);
  });
  if (items.length > 100) {const p = document.createElement('p'); p.textContent = 'Showing the first 100 items.'; container.append(p);}
}
$('apps-list').addEventListener('click', async () => {
  const result = await command({action: 'apps'}, 'Load applications');
  if (result) itemList('apps', result.apps, item => item.name || item.appId || item.app_id || item.id || 'Unnamed app', item => {
    const id = String(item.appId || item.app_id || item.id || '');
    if (id) command({action: 'launch', app_id: id, app_type: Number(item.app_type) === 1 ? 'NATIVE_LAUNCH' : 'DEEP_LINK'}, 'Launch application');
  }, 'This TV did not return an app list. You can still launch a known app ID.');
});
$('art-list').addEventListener('click', async () => {
  const result = await command({action: 'art_list'}, 'Load artwork');
  if (result) itemList('artworks', result.artworks, item => item.title || item.name || item.content_id || 'Untitled artwork', item => {
    if (item.content_id) command({action: 'art_select', content_id: String(item.content_id)}, 'Select artwork');
  }, 'No artwork was returned by the TV.');
});
$('launch-form').addEventListener('submit', event => {event.preventDefault(); command({action: 'launch', app_id: $('app-id').value.trim()}, 'Launch application');});
$('text-form').addEventListener('submit', async event => {event.preventDefault(); if (await command({action: 'text', text: $('tv-text').value}, 'Text sent')) $('tv-text').value = '';});
$('auth-form').addEventListener('submit', async event => {
  event.preventDefault(); accessToken = $('access-token').value; $('auth-error').textContent = '';
  try {await loadState(); $('auth-dialog').close(); $('access-token').value = ''; notice('Connected to your home server.');}
  catch (error) {$('auth-error').textContent = error.message;}
});
loadState().catch(error => notice(error.message, true));
