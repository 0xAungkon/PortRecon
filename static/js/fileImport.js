import { addIPRow } from './ipRanges.js';

export function handleImport(event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = ev => {
    const feedback = document.getElementById('importFeedback');

    try {
      const content = ev.target.result.trim();
      let importedCount = 0;

      if (content.startsWith('[')) {
        try {
          const ranges = JSON.parse(content);
          if (Array.isArray(ranges)) {
            ranges.forEach(range => {
              const [start, end] = String(range).split('-').map(value => value.trim());
              if (start && end) {
                addIPRow(start, end);
                importedCount++;
              }
            });

            feedback.style.color = 'var(--green)';
            feedback.textContent = `✓ Imported ${importedCount} range${importedCount !== 1 ? 's' : ''} from "${file.name}" (JSON)`;
            event.target.value = '';
            return;
          }
        } catch {
          // Fall through to CSV parsing
        }
      }

      const lines = content.split('\n').filter(line => line.trim());
      lines.forEach(line => {
        const [start, end] = line.split(',').map(value => value.trim());
        if (start && end) {
          addIPRow(start, end);
          importedCount++;
        }
      });

      if (importedCount > 0) {
        feedback.style.color = 'var(--green)';
        feedback.textContent = `✓ Imported ${importedCount} range${importedCount !== 1 ? 's' : ''} from "${file.name}" (CSV)`;
      } else {
        feedback.style.color = 'var(--red)';
        feedback.textContent = '✗ No valid ranges found in file';
      }
    } catch (error) {
      feedback.style.color = 'var(--red)';
      feedback.textContent = `✗ Error reading file: ${error.message}`;
    }

    event.target.value = '';
  };

  reader.readAsText(file);
}
