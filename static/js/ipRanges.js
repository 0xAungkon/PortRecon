export function addIPRow(start = '', end = '') {
  const container = document.getElementById('ipRangeRows');
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
  container.appendChild(el);
}

export function removeRow(id) {
  const container = document.getElementById('ipRangeRows');
  if (container.children.length > 1) {
    document.getElementById(id)?.remove();
  }
}

export function getIPRanges() {
  return [...document.querySelectorAll('#ipRangeRows .ip-row')].reduce((acc, row) => {
    const inputs = row.querySelectorAll('input');
    if (inputs[0].value && inputs[1].value) {
      acc.push({ start: inputs[0].value, end: inputs[1].value });
    }
    return acc;
  }, []);
}

export function setPreset(type) {
  const map = {
    web: '80,8080,443,8443',
    db: '3306,5432,1433,27017,6379',
    remote: '22,3389,5900',
    all: '80,443,22,3306,5432,27017,6379',
  };
  document.getElementById('ports').value = map[type] || '';
}
