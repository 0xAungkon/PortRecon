import { API_BASE } from './config.js';
import { state } from './state.js';

export async function loadScanHistory() {
  try {
    const response = await fetch(`${API_BASE}/scan`);
    if (!response.ok) return;
    state.scanHistory = await response.json();
    renderScanHistory();
  } catch (error) {
    console.error('Failed to load scan history:', error);
  }
}

export function renderScanHistory() {
  const list = document.getElementById('scanList');
  list.innerHTML = '';

  if (!state.scanHistory.length) {
    list.innerHTML = '<div class="sb-empty-hint" id="sbEmptyHint">No scans yet.<br/>Start a new scan to begin.</div>';
    return;
  }

  state.scanHistory.forEach(scan => {
    const btn = document.createElement('button');
    btn.className = 'scan-item';
    btn.id = `si-${scan.id}`;
    btn.onclick = () => window.loadScan?.(scan.id);

    const statusDot = {
      pending: 'pending',
      running: 'running',
      completed: 'completed',
      failed: 'failed',
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

export function setSidebarDot(id, status) {
  const item = document.getElementById(`si-${id}`);
  if (item) {
    item.querySelector('.scan-dot').className = `scan-dot ${status}`;
  }
}

export function setActiveSidebar(id) {
  document.querySelectorAll('.scan-item').forEach(el => el.classList.remove('active'));
  if (id) document.getElementById(`si-${id}`)?.classList.add('active');
}
