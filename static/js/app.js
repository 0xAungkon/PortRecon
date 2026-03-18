/* ─── API CONFIG ─────────────────────────────────── */
const API_BASE = '/api/v1';

/* ─── STATE ──────────────────────────────────────── */
let isDark = false;
let scanning = false;
let results = [];
let scanHistory = [];
let activeScanId = null;
let eventSource = null;
let elapsedSec = 0;
let elapsedTimer = null;

/* ─── INIT ───────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', async () => {
  applyTheme();
  addIPRow('192.168.1.1', '192.168.1.50');
  await loadScanHistory();
  checkURLParams();
});

/* ─── THEME ─────────────────────────────────────── */
function toggleTheme() {
  isDark = !isDark;
  applyTheme();
}

function applyTheme() {
  document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  document.getElementById('themeLabel').textContent = isDark ? 'Dark' : 'Light';
  const icon = document.getElementById('themeIcon');
  icon.innerHTML = isDark
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
}

/* ─── IP RANGE MANAGEMENT ────────────────────────── */
function addIPRow(start = '', end = '') {
  const c = document.getElementById('ipRangeRows');
  const id = 'r' + Date.now() + Math.random().toString(36).slice(2, 6);
  const el = document.createElement('div');
  el.className = 'ip-row';
  el.id = id;
  el.innerHTML = `
    <input type="text" placeholder="e.g. 192.168.1.0" value="${start}"/>
    <input type="text" placeholder="e.g. 192.168.1.255" value="${end}"/>
    <button class="btn-icon-del" onclick="removeRow('${id}')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
    </button>
  `;
  c.appendChild(el);
}

function removeRow(id) {
  const c = document.getElementById('ipRangeRows');
  if (c.children.length > 1) document.getElementById(id)?.remove();
}

function getIPRanges() {
  return [...document.querySelectorAll('#ipRangeRows .ip-row')].reduce((acc, r) => {
    const inputs = r.querySelectorAll('input');
    if (inputs[0].value && inputs[1].value) {
      acc.push({ start: inputs[0].value, end: inputs[1].value });
    }
    return acc;
  }, []);
}

/* ─── PORT PRESETS ───────────────────────────────── */
function setPreset(t) {
  const m = {
    http: '80,8080',
    https: '443,8443',
    ssh: '22',
    all: '80,443,22,3306,5432,27017,6379',
  };
  document.getElementById('ports').value = m[t] || '';
}

/* ─── LOAD SCAN HISTORY ──────────────────────────– */
async function loadScanHistory() {
  try {
    const resp = await fetch(`${API_BASE}/scan`);
    if (!resp.ok) return;
    scanHistory = await resp.json();
    renderScanHistory();
  } catch (e) {
    console.error('Failed to load scan history:', e);
  }
}

function renderScanHistory() {
  const list = document.getElementById('scanList');
  list.innerHTML = '';

  if (!scanHistory.length) {
    list.innerHTML = '<div class="sb-empty-hint" id="sbEmptyHint">No scans yet.<br/>Start a new scan to begin.</div>';
    return;
  }

  scanHistory.forEach(scan => {
    const btn = document.createElement('button');
    btn.className = 'scan-item';
    btn.id = 'si-' + scan.id;
    btn.onclick = () => loadScan(scan.id);

    const statusDot = {
      'pending': 'pending',
      'running': 'running',
      'completed': 'completed',
      'failed': 'failed',
    }[scan.status] || 'pending';

    const created = new Date(scan.created_at);
    const timeStr = created.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    btn.innerHTML = `
      <div class="scan-dot ${statusDot}"></div>
      <div class="scan-item-name">${scan.name}</div>
      <div class="scan-item-time">${timeStr}</div>
    `;
    list.appendChild(btn);
  });
}

function setSidebarDot(id, status) {
  const el = document.getElementById('si-' + id);
  if (el) {
    el.querySelector('.scan-dot').className = `scan-dot ${status}`;
  }
}

function setActiveSidebar(id) {
  document.querySelectorAll('.scan-item').forEach(e => e.classList.remove('active'));
  if (id) document.getElementById('si-' + id)?.classList.add('active');
}

/* ─── LOAD HISTORICAL SCAN ───────────────────────── */
async function loadScan(id) {
  activeScanId = id;
  setActiveSidebar(id);
  
  // Update URL
  window.history.pushState({}, '', `?uuid=${id}`);

  const scan = scanHistory.find(s => s.id === id);
  if (!scan) return;

  document.getElementById('tbTitle').textContent = scan.name;
  document.getElementById('tbMeta').textContent = new Date(scan.created_at).toLocaleTimeString();

  setChip(scan.status);
  updateProgress(scan.progress, scan.total_targets);

  // Listen to status changes
  listenToScanStatus(id);

  // If completed, fetch results
  if (scan.status === 'completed') {
    await fetchScanResults(id);
  } else {
    results = [];
    renderResults();
  }
}

function checkURLParams() {
  const params = new URLSearchParams(window.location.search);
  const uuid = params.get('uuid');
  if (uuid) {
    const scan = scanHistory.find(s => s.id === uuid);
    if (scan) {
      loadScan(uuid);
    }
  }
}

/* ─── SCAN STATUS LISTENER ───────────────────────– */
function listenToScanStatus(scanId) {
  // Close existing event source
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

  eventSource = new EventSource(`${API_BASE}/scan/${scanId}`);

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    document.getElementById('tbMeta').textContent = 
      data.status === 'running' ? 'Scan in progress…' : 'Scan completed';
    
    setChip(data.status);
    updateProgress(data.progress, data.total_targets);
    setSidebarDot(scanId, data.status);

    if (data.status === 'completed' || data.status === 'failed') {
      eventSource.close();
      if (data.status === 'completed') {
        fetchScanResults(scanId);
      }
      // Refresh history
      loadScanHistory();
    }
  };

  eventSource.onerror = () => {
    eventSource.close();
    console.error('EventSource error');
  };
}

/* ─── FETCH SCAN RESULTS ─────────────────────────– */
async function fetchScanResults(scanId) {
  try {
    const resp = await fetch(`${API_BASE}/scan/${scanId}/output`);
    if (!resp.ok) return;
    const data = await resp.json();
    results = data.results || [];
    renderResults();
  } catch (e) {
    console.error('Failed to fetch results:', e);
  }
}

/* ─── CREATE NEW SCAN ────────────────────────────– */
function newScan() {
  if (scanning) return;
  activeScanId = null;
  window.history.pushState({}, '', '/');
  setActiveSidebar(null);
  resetAll(false);
}

/* ─── START SCAN ─────────────────────────────────– */
async function startScan() {
  const ranges = getIPRanges();
  const ports = document.getElementById('ports').value.trim();
  const name = (document.getElementById('scanName').value.trim() || 'Unnamed Scan');
  const workers = parseInt(document.getElementById('workers').value) || 16;
  const retries = parseInt(document.getElementById('retries').value) || 3;

  if (!ranges.length) {
    showFieldError('Add at least one IP range before starting.');
    return;
  }
  if (!ports) {
    showFieldError('Enter at least one port number.');
    return;
  }

  scanning = true;
  results = [];
  elapsedSec = 0;
  
  document.getElementById('startBtn').disabled = true;
  document.getElementById('stopBtn').classList.remove('hidden');
  document.getElementById('resultBody').innerHTML = '';
  document.getElementById('progressBar').classList.add('active');
  document.getElementById('tbMeta').textContent = 'Submitting scan...';

  try {
    const payload = {
      name,
      ip_range: ranges.map(r => `${r.start}-${r.end}`).join(','),
      ports,
      workers,
      retries,
    };

    const resp = await fetch(`${API_BASE}/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      showFieldError('Failed to start scan. Try again.');
      scanning = false;
      document.getElementById('startBtn').disabled = false;
      document.getElementById('stopBtn').classList.add('hidden');
      return;
    }

    const { id: scanId } = await resp.json();
    activeScanId = scanId;
    
    // Update URL
    window.history.pushState({}, '', `?uuid=${scanId}`);
    
    // Reload history and listen
    await loadScanHistory();
    setActiveSidebar(scanId);
    
    document.getElementById('tbTitle').textContent = name;
    document.getElementById('tbMeta').textContent = 'Scan queued...';
    setChip('pending');

    elapsedTimer = setInterval(() => {
      elapsedSec++;
      document.getElementById('statElapsed').textContent = elapsedSec + 's';
    }, 1000);

    listenToScanStatus(scanId);

  } catch (e) {
    console.error('Failed to start scan:', e);
    showFieldError('Error: ' + e.message);
    scanning = false;
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').classList.add('hidden');
  }
}

function stopScan() {
  scanning = false;
  if (elapsedTimer) clearInterval(elapsedTimer);
  if (eventSource) eventSource.close();
  document.getElementById('progressBar').classList.remove('active');
  document.getElementById('startBtn').disabled = false;
  document.getElementById('stopBtn').classList.add('hidden');
  document.getElementById('tbMeta').textContent = 'Scan stopped';
  setChip('stopped');
}

/* ─── UPDATE PROGRESS ────────────────────────────– */
function updateProgress(done, total) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  document.getElementById('progressBar').style.width = pct + '%';
  document.getElementById('progressPct').textContent = pct + '%';

  if (pct === 100) {
    document.getElementById('progressLabel').textContent = 'Scan completed';
    document.getElementById('currentTarget').textContent = '✓ Finished';
    document.getElementById('progressBar').classList.remove('active');
  } else if (done > 0) {
    document.getElementById('progressLabel').textContent = `Scanning: ${done}/${total}`;
    document.getElementById('currentTarget').textContent = `Scanning targets…`;
  }

  document.getElementById('statScanned').textContent = done;
  document.getElementById('statTotal').textContent = total;
  document.getElementById('progressMeta').textContent = `${pct}% complete · ${results.length} host${results.length !== 1 ? 's' : ''} with open ports`;
}

/* ─── STATUS CHIP ────────────────────────────────– */
function setChip(status) {
  const map = {
    'pending': ['chip-idle', '⏳ Pending'],
    'running': ['chip-running', '◆ Running'],
    'completed': ['chip-done', '✓ Done'],
    'failed': ['chip-failed', '✕ Failed'],
  };
  const [cls, lbl] = map[status] || map['pending'];
  const chipWrap = document.getElementById('chipWrap');
  chipWrap.innerHTML = `<div class="chip ${cls}"><div class="chip-dot"></div>${lbl}</div>`;
}

/* ─── RENDER RESULTS ─────────────────────────────– */
function renderResults() {
  const tbody = document.getElementById('resultBody');
  tbody.innerHTML = '';

  if (!results.length) {
    tbody.innerHTML = '<tr><td colspan="3"><div class="empty-state"><div class="empty-title">No results yet</div><div class="empty-sub">Results will appear here as the scan progresses</div></div></td></tr>';
  } else {
    results.forEach((r, idx) => {
      const tr = document.createElement('tr');
      const ports = (r.open_ports || []).map(p => `<span class="port-tag">${p}</span>`).join('');
      tr.innerHTML = `
        <td>${idx + 1}</td>
        <td>${r.host}</td>
        <td>${ports || '—'}</td>
        <td><span class="badge-open">● Open</span></td>
      `;
      tbody.appendChild(tr);
    });
  }

  document.getElementById('resultCount').textContent = results.length;
  document.getElementById('statOpen').textContent = results.length;
}

/* ─── EXPORT CSV ─────────────────────────────────– */
async function exportCSV() {
  if (!activeScanId) return;
  window.location.href = `${API_BASE}/scan/${activeScanId}/download`;
}

/* ─── RESET ──────────────────────────────────────– */
function resetAll(clearName = true) {
  if (scanning) stopScan();
  results = [];
  if (clearName) document.getElementById('scanName').value = '';
  document.getElementById('resultCount').textContent = '0';
  document.getElementById('statScanned').textContent = '0';
  document.getElementById('statOpen').textContent = '0';
  document.getElementById('statTotal').textContent = '—';
  document.getElementById('statElapsed').textContent = '0s';
  document.getElementById('progressBar').style.width = '0%';
  document.getElementById('progressBar').classList.remove('active');
  document.getElementById('progressPct').textContent = '0%';
  document.getElementById('progressLabel').textContent = 'Ready to scan';
  document.getElementById('progressMeta').textContent = '—';
  document.getElementById('currentTarget').textContent = '—';
  document.getElementById('importFeedback').textContent = '';
  document.getElementById('startBtn').disabled = false;
  document.getElementById('stopBtn').classList.add('hidden');
  setChip('idle');
  renderResults();
  document.getElementById('tbTitle').textContent = 'New Scan';
  document.getElementById('tbMeta').textContent = 'Configure your scan below and click Start';
}

/* ─── HELPERS ────────────────────────────────────– */
function showFieldError(msg) {
  const fb = document.getElementById('importFeedback');
  fb.textContent = msg;
  fb.style.color = 'var(--red)';
}
