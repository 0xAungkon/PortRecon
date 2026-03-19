import { API_BASE } from './config.js';
import { state } from './state.js';
import { getIPRanges } from './ipRanges.js';
import { loadScanHistory, setActiveSidebar, setSidebarDot } from './history.js';
import {
  renderResults,
  setChip,
  showConfigView,
  showFieldError,
  showResultsTableView,
  showResultsTextView,
  showScanningView,
  updateProgress,
} from './ui.js';

export async function fetchScanResults(scanId) {
  try {
    const response = await fetch(`${API_BASE}/scan/${scanId}/output`);
    if (!response.ok) return;
    const data = await response.json();
    state.results = data.results || [];
  } catch (error) {
    console.error('Failed to fetch results:', error);
  }
}

export function listenToScanStatus(scanId) {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }

  state.eventSource = new EventSource(`${API_BASE}/scan/${scanId}`);

  state.eventSource.onmessage = event => {
    const data = JSON.parse(event.data);

    document.getElementById('tbMeta').textContent = data.status === 'running' ? 'Scan in progress…' : 'Scan completed';

    setChip(data.status);
    updateProgress(data.progress, data.total_targets);
    setSidebarDot(scanId, data.status);

    if (data.status === 'running' || data.status === 'completed') {
      document.getElementById('detailStatus').textContent = data.status === 'running' ? 'Running' : 'Completed';
      document.getElementById('detailTargets').textContent = data.total_targets ?? '—';
      document.getElementById('detailProgress').textContent = `${data.progress}/${data.total_targets}`;
    }

    if (data.status === 'completed' || data.status === 'failed') {
      state.eventSource.close();
      if (data.status === 'completed') {
        fetchScanResults(scanId).then(() => {
          renderResults();
          showResultsTextView();
        });
      }
      loadScanHistory();
    }
  };

  state.eventSource.onerror = () => {
    state.eventSource.close();
    console.error('EventSource error');
  };
}

export async function loadScan(id) {
  state.activeScanId = id;
  setActiveSidebar(id);
  window.history.pushState({}, '', `?uuid=${id}`);

  const scan = state.scanHistory.find(s => s.id === id);
  if (!scan) return;

  document.getElementById('tbTitle').textContent = scan.name;
  document.getElementById('tbMeta').textContent = new Date(scan.created_at).toLocaleTimeString();

  setChip(scan.status);
  updateProgress(scan.progress, scan.total_targets);
  showScanningView(scan);
  listenToScanStatus(id);

  if (scan.status === 'completed') {
    await fetchScanResults(id);
    renderResults();
    showResultsTextView();
  } else {
    state.results = [];
    renderResults();
    showResultsTableView();
  }
}

export function checkURLParams() {
  const params = new URLSearchParams(window.location.search);
  const uuid = params.get('uuid');
  if (!uuid) return;

  const scan = state.scanHistory.find(s => s.id === uuid);
  if (scan) {
    loadScan(uuid);
  }
}

export function newScan() {
  if (state.scanning) return;
  state.activeScanId = null;
  window.history.pushState({}, '', '/');
  setActiveSidebar(null);
  showConfigView();
  showResultsTableView();
  resetAll(false);
}

export async function startScan() {
  const ranges = getIPRanges();
  const ports = document.getElementById('ports').value.trim();
  const name = document.getElementById('scanName').value.trim() || 'Unnamed Scan';
  const workers = parseInt(document.getElementById('workers').value, 10) || 16;
  const retries = parseInt(document.getElementById('retries').value, 10) || 3;

  if (!ranges.length) {
    showFieldError('Add at least one IP range before starting.');
    return;
  }

  if (!ports) {
    showFieldError('Enter at least one port number.');
    return;
  }

  state.scanning = true;
  state.results = [];
  state.elapsedSec = 0;

  document.getElementById('startBtn').disabled = true;
  document.getElementById('stopBtn').classList.remove('hidden');
  document.getElementById('resultBody').innerHTML = '';
  document.getElementById('progressBar').classList.add('active');
  document.getElementById('tbMeta').textContent = 'Submitting scan...';

  const rangesStr = ranges.map(r => `${r.start}-${r.end}`).join(', ');
  showScanningView();
  showResultsTableView();
  document.getElementById('detailName').textContent = name;
  document.getElementById('detailRanges').textContent = rangesStr;
  document.getElementById('detailPorts').textContent = ports;
  document.getElementById('detailStatus').textContent = 'Pending';

  try {
    const payload = {
      name,
      ip_range: ranges.map(r => `${r.start}-${r.end}`).join(','),
      ports,
      workers,
      retries,
    };

    const response = await fetch(`${API_BASE}/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      showFieldError('Failed to start scan. Try again.');
      state.scanning = false;
      document.getElementById('startBtn').disabled = false;
      document.getElementById('stopBtn').classList.add('hidden');
      showConfigView();
      return;
    }

    const { id: scanId } = await response.json();
    state.activeScanId = scanId;
    window.history.pushState({}, '', `?uuid=${scanId}`);

    await loadScanHistory();
    setActiveSidebar(scanId);

    document.getElementById('tbTitle').textContent = name;
    document.getElementById('tbMeta').textContent = 'Scan queued...';
    setChip('pending');

    state.elapsedTimer = setInterval(() => {
      state.elapsedSec++;
      document.getElementById('statElapsed').textContent = `${state.elapsedSec}s`;
    }, 1000);

    listenToScanStatus(scanId);
  } catch (error) {
    console.error('Failed to start scan:', error);
    showFieldError(`Error: ${error.message}`);
    state.scanning = false;
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').classList.add('hidden');
    showConfigView();
  }
}

export function stopScan() {
  state.scanning = false;

  if (state.elapsedTimer) clearInterval(state.elapsedTimer);
  if (state.eventSource) state.eventSource.close();

  document.getElementById('progressBar').classList.remove('active');
  document.getElementById('startBtn').disabled = false;
  document.getElementById('stopBtn').classList.add('hidden');
  document.getElementById('tbMeta').textContent = 'Scan stopped';
  setChip('stopped');
  showConfigView();
}

export function exportCSV() {
  if (!state.activeScanId) return;
  window.location.href = `${API_BASE}/scan/${state.activeScanId}/download`;
}

export function resetAll(clearName = true) {
  if (state.scanning) stopScan();

  state.results = [];

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
  showConfigView();
  showResultsTableView();
  renderResults();

  document.getElementById('tbTitle').textContent = 'New Scan';
  document.getElementById('tbMeta').textContent = 'Configure your scan below and click Start';
}
