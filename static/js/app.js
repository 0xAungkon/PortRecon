import { applyTheme, toggleTheme } from './theme.js';
import { loadScanHistory } from './history.js';
import {
  checkURLParams,
  exportCSV,
  loadScan,
  newScan,
  resetAll,
  startScan,
  stopScan,
} from './scan.js';

window.toggleTheme = toggleTheme;
window.startScan = startScan;
window.stopScan = stopScan;
window.resetAll = resetAll;
window.exportCSV = exportCSV;
window.newScan = newScan;
window.loadScan = loadScan;

document.addEventListener('DOMContentLoaded', async () => {
  applyTheme();
  await loadScanHistory();
  checkURLParams();
});
