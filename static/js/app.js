import { applyTheme, toggleTheme } from './theme.js';
import { addIPRow, removeRow, setPreset } from './ipRanges.js';
import { handleImport } from './fileImport.js';
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
window.addIPRow = addIPRow;
window.removeRow = removeRow;
window.setPreset = setPreset;
window.handleImport = handleImport;
window.startScan = startScan;
window.stopScan = stopScan;
window.resetAll = resetAll;
window.exportCSV = exportCSV;
window.newScan = newScan;
window.loadScan = loadScan;

document.addEventListener('DOMContentLoaded', async () => {
  applyTheme();
  addIPRow('192.168.1.1', '192.168.1.50');
  await loadScanHistory();
  checkURLParams();
});
