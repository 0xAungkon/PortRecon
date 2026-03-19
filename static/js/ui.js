import { state } from './state.js';

export function showFieldError(message) {
  const feedback = document.getElementById('modalError') || document.getElementById('importFeedback');
  if (!feedback) return;
  feedback.textContent = message;
  feedback.style.color = 'var(--red)';
}

export function updateProgress(metrics = {}) {
  const totalRanges = Number(metrics.totalRanges ?? 0);
  const completedRanges = Number(metrics.completedRanges ?? 0);
  const totalHosts = Number(metrics.totalHosts ?? 0);
  const completedHosts = Number(metrics.completedHosts ?? 0);
  const failedHosts = Number(metrics.failedHosts ?? 0);
  const pct = Number.isFinite(Number(metrics.progressPercent))
    ? Number(metrics.progressPercent)
    : (totalRanges ? Math.round((completedRanges / totalRanges) * 100) : 0);

  document.getElementById('progressBar').style.width = `${pct}%`;
  document.getElementById('progressPct').textContent = `${pct}%`;

  if (pct === 100) {
    document.getElementById('progressLabel').textContent = 'Scan completed';
    document.getElementById('currentTarget').textContent = '✓ Finished';
    document.getElementById('progressBar').classList.remove('active');
  } else if (completedRanges > 0) {
    document.getElementById('progressLabel').textContent = `Ranges: ${completedRanges}/${totalRanges}`;
    document.getElementById('currentTarget').textContent = 'Scanning targets…';
  }

  document.getElementById('statScanned').textContent = completedHosts;
  document.getElementById('statTotal').textContent = totalHosts;
  document.getElementById('progressMeta').textContent = `Ranges ${completedRanges}/${totalRanges} · Hosts ${completedHosts}/${totalHosts} · Failed ${failedHosts} · ${pct}%`;
}

export function setChip(status) {
  const map = {
    idle: ['chip-idle', 'Idle'],
    stopped: ['chip-stopped', '■ Stopped'],
    pending: ['chip-idle', '⏳ Pending'],
    running: ['chip-running', '◆ Running'],
    completed: ['chip-done', '✓ Done'],
    failed: ['chip-failed', '✕ Failed'],
  };

  const [cls, label] = map[status] || map.pending;
  document.getElementById('chipWrap').innerHTML = `<div class="chip ${cls}"><div class="chip-dot"></div>${label}</div>`;
}

export function showConfigView() {
  document.getElementById('configView').classList.remove('hidden');
  document.getElementById('scanningView').classList.add('hidden');
  document.getElementById('actionControls').style.display = 'flex';
}

export function showScanningView(scan = null) {
  document.getElementById('configView').classList.add('hidden');
  document.getElementById('scanningView').classList.remove('hidden');

  if (!scan) return;

  const inputFile = scan.input_file_name || scan.input_file_path || '—';
  const status = scan.status ? scan.status.charAt(0).toUpperCase() + scan.status.slice(1) : '—';
  const totalRanges = scan.total_ranges ?? '—';
  const completedRanges = scan.completed_ranges ?? 0;
  const totalHosts = scan.total_hosts ?? '—';
  const completedHosts = scan.completed_hosts ?? 0;
  const failedHosts = scan.failed_hosts ?? 0;
  const progressPct = scan.progress_percent ?? 0;

  document.getElementById('detailName').textContent = scan.name || '—';
  document.getElementById('detailStatus').textContent = status;
  document.getElementById('detailInputFile').textContent = inputFile;
  document.getElementById('detailPorts').textContent = scan.ports || '—';
  document.getElementById('detailTotalRanges').textContent = totalRanges;
  document.getElementById('detailCompletedRanges').textContent = completedRanges;
  document.getElementById('detailTotalHosts').textContent = totalHosts;
  document.getElementById('detailCompletedHosts').textContent = completedHosts;
  document.getElementById('detailFailedHosts').textContent = failedHosts;
  document.getElementById('detailProgressPct').textContent = `${progressPct}%`;
}

export function showResultsTableView() {
  document.getElementById('resultsTableView').classList.remove('hidden');
  document.getElementById('resultsTextView').classList.add('hidden');
  document.getElementById('exportBtn').style.display = 'inline-flex';
}

export function showResultsTextView() {
  document.getElementById('resultsTableView').classList.add('hidden');
  document.getElementById('resultsTextView').classList.remove('hidden');
  document.getElementById('exportBtn').style.display = 'inline-flex';

  const textContainer = document.getElementById('resultsTextContent');
  if (!state.results.length) {
    textContainer.textContent = 'No results yet';
    return;
  }

  let textContent = 'SCAN RESULTS\n';
  textContent += '═'.repeat(60) + '\n\n';

  state.results.forEach((result, idx) => {
    textContent += `[${idx + 1}] ${result.host}\n`;
    if (result.open_ports?.length) {
      textContent += `    Open Ports: ${result.open_ports.join(', ')}\n`;
    }
    textContent += '\n';
  });

  textContent += '═'.repeat(60) + '\n';
  textContent += `\nTotal hosts with open ports: ${state.results.length}`;

  textContainer.textContent = textContent;
}

export function renderResults() {
  const tbody = document.getElementById('resultBody');
  tbody.innerHTML = '';

  if (!state.results.length) {
    tbody.innerHTML = '<tr><td colspan="4"><div class="empty-state"><div class="empty-title">No results yet</div><div class="empty-sub">Results will appear here as the scan progresses</div></div></td></tr>';
  } else {
    state.results.forEach((result, idx) => {
      const tr = document.createElement('tr');
      const ports = (result.open_ports || []).map(port => `<span class="port-tag">${port}</span>`).join('');
      tr.innerHTML = `
        <td>${idx + 1}</td>
        <td>${result.host}</td>
        <td>${ports || '—'}</td>
        <td><span class="badge-open">● Open</span></td>
      `;
      tbody.appendChild(tr);
    });
  }

  document.getElementById('resultCount').textContent = state.results.length;
  document.getElementById('statOpen').textContent = state.results.length;
}
