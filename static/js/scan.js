import { API_BASE } from './config.js';
import { state } from './state.js';
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
    updateProgress({
      totalRanges: data.total_ranges,
      completedRanges: data.completed_ranges,
      totalHosts: data.total_hosts,
      completedHosts: data.completed_hosts,
      failedHosts: data.failed_hosts,
      progressPercent: data.progress_percent,
    });
    setSidebarDot(scanId, data.status);

    if (data.status === 'running' || data.status === 'completed' || data.status === 'stopped') {
      const statusText = data.status === 'running' ? 'Running' : data.status === 'completed' ? 'Completed' : 'Stopped';
      document.getElementById('detailStatus').textContent = statusText;
      document.getElementById('detailTotalRanges').textContent = data.total_ranges ?? '—';
      document.getElementById('detailCompletedRanges').textContent = data.completed_ranges ?? '—';
      document.getElementById('detailTotalHosts').textContent = data.total_hosts ?? '—';
      document.getElementById('detailCompletedHosts').textContent = data.completed_hosts ?? '—';
      document.getElementById('detailFailedHosts').textContent = data.failed_hosts ?? '—';
      document.getElementById('detailProgressPct').textContent = `${data.progress_percent ?? 0}%`;
    }

    const isActive = data.status === 'running' || data.status === 'pending';
    state.scanning = isActive;
    document.getElementById('startBtn').disabled = isActive;
    document.getElementById('stopBtn').classList.toggle('hidden', !isActive);

    if (data.status === 'completed' || data.status === 'failed' || data.status === 'stopped') {
      state.eventSource.close();
      if (data.status === 'completed') {
        fetchScanResults(scanId).then(() => {
          renderResults();
          showResultsTableView();
        });
      } else {
        showConfigView();
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
  updateProgress({
    totalRanges: scan.total_ranges,
    completedRanges: scan.completed_ranges,
    totalHosts: scan.total_hosts,
    completedHosts: scan.completed_hosts,
    failedHosts: scan.failed_hosts,
    progressPercent: scan.progress_percent,
  });
  showScanningView(scan);

  const isActive = scan.status === 'running' || scan.status === 'pending';
  state.scanning = isActive;
  document.getElementById('startBtn').disabled = isActive;
  document.getElementById('stopBtn').classList.toggle('hidden', !isActive);

  if (isActive) {
    listenToScanStatus(id);
  }

  if (scan.status === 'completed') {
    await fetchScanResults(id);
    renderResults();
    showResultsTableView();
  } else {
    state.results = [];
    renderResults();
    showResultsTableView();
  }
}

export function checkURLParams() {
  const params = new URLSearchParams(window.location.search);
  const uuid = params.get('uuid');
  if (!uuid) {
    showConfigView();
    showResultsTableView();
    return;
  }

  const scan = state.scanHistory.find(s => s.id === uuid);
  if (scan) {
    loadScan(uuid);
    return;
  }

  showConfigView();
  showResultsTableView();
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

function resetLaunchForm() {
  document.getElementById('launchName').value = '';
  document.getElementById('launchFile').value = '';
  document.getElementById('launchPorts').value = '22,80,443,3306,8080,3389';
  document.getElementById('launchWorkers').value = '10';
  document.getElementById('launchRetries').value = '3';
  document.getElementById('modalError').textContent = '';
}

export async function startScan() {
  const name = document.getElementById('launchName').value.trim() || 'Unnamed Scan';
  const fileInput = document.getElementById('launchFile');
  const ipFile = fileInput?.files?.[0];
  const ports = document.getElementById('launchPorts').value.trim();
  const workers = parseInt(document.getElementById('launchWorkers').value, 10) || 10;
  const retries = parseInt(document.getElementById('launchRetries').value, 10) || 3;

  if (!ipFile) {
    showFieldError('Select a JSON/CSV file with IP ranges.');
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

  showScanningView();
  showResultsTableView();
  document.getElementById('detailName').textContent = name;
  document.getElementById('detailInputFile').textContent = ipFile.name;
  document.getElementById('detailPorts').textContent = ports;
  document.getElementById('detailStatus').textContent = 'Pending';
  document.getElementById('detailTotalRanges').textContent = '—';
  document.getElementById('detailCompletedRanges').textContent = '0';
  document.getElementById('detailTotalHosts').textContent = '—';
  document.getElementById('detailCompletedHosts').textContent = '0';
  document.getElementById('detailFailedHosts').textContent = '0';
  document.getElementById('detailProgressPct').textContent = '0%';

  try {
    const payload = new FormData();
    payload.append('name', name);
    payload.append('ip_file', ipFile);
    payload.append('ports', ports);
    payload.append('workers', String(workers));
    payload.append('retries', String(retries));

    const response = await fetch(`${API_BASE}/scan`, {
      method: 'POST',
      body: payload,
    });

    if (!response.ok) {
      let errorMessage = 'Failed to start scan. Try again.';
      try {
        const body = await response.json();
        if (body?.detail) errorMessage = body.detail;
      } catch {
        // Ignore parse errors and keep fallback message
      }

      showFieldError(errorMessage);
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
    resetLaunchForm();

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

export async function stopScan() {
  if (!state.activeScanId) {
    state.scanning = false;
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').classList.add('hidden');
    document.getElementById('tbMeta').textContent = 'Scan stopped';
    setChip('stopped');
    showConfigView();
    return;
  }

  try {
    await fetch(`${API_BASE}/scan/${state.activeScanId}/cancel`, { method: 'POST' });
  } catch (error) {
    console.error('Failed to cancel scan:', error);
  }

  state.scanning = false;
  if (state.elapsedTimer) clearInterval(state.elapsedTimer);
  if (state.eventSource) state.eventSource.close();

  document.getElementById('progressBar').classList.remove('active');
  document.getElementById('startBtn').disabled = false;
  document.getElementById('stopBtn').classList.add('hidden');
  document.getElementById('detailStatus').textContent = 'Stopped';
  document.getElementById('tbMeta').textContent = 'Scan stopped';
  setChip('stopped');
  showConfigView();

  await loadScanHistory();
}

export function exportCSV() {
  if (!state.activeScanId) return;
  window.location.href = `${API_BASE}/scan/${state.activeScanId}/download`;
}

export function resetAll(clearName = true) {
  if (state.scanning) stopScan();

  state.results = [];

  if (clearName) {
    document.getElementById('launchName').value = '';
    document.getElementById('launchPorts').value = '22,80,443,3306,8080,3389';
    document.getElementById('launchWorkers').value = '10';
    document.getElementById('launchRetries').value = '3';
    document.getElementById('launchFile').value = '';
  }

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
  document.getElementById('modalError').textContent = '';
  document.getElementById('startBtn').disabled = false;
  document.getElementById('stopBtn').classList.add('hidden');

  setChip('idle');
  showConfigView();
  showResultsTableView();
  renderResults();

  document.getElementById('tbTitle').textContent = 'New Scan';
  document.getElementById('tbMeta').textContent = 'Configure your scan below and click Start';
}
