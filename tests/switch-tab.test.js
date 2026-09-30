// Runs script.js against a minimal DOM and checks that opening the page
// with a #fedora hash shows the fedora tab instead of throwing.
// Usage: node tests/switch-tab.test.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const src = fs.readFileSync(
  path.join(__dirname, '..', '.github/actions/generate-repository-website/templates/script.js'), 'utf8');

function el(id) {
  const classes = new Set();
  return {
    id,
    classList: { add: c => classes.add(c), remove: c => classes.delete(c), has: c => classes.has(c) },
    textContent: '',
    addEventListener() {},
  };
}
const tabs = { ubuntu: el('ubuntu'), fedora: el('fedora'), arch: el('arch') };
const navTabs = [el('n1'), el('n2'), el('n3')];
const listeners = {};
const document = {
  querySelectorAll: sel => (sel === '.tab-content' ? Object.values(tabs) : sel === '.nav-tab' ? navTabs : []),
  querySelector: sel => (sel === '#year' ? el('year') : sel.includes("'fedora'") ? navTabs[1] : null),
  getElementById: id => tabs[id],
  addEventListener: (n, f) => { listeners[n] = f; },
};
const window = { location: { hash: '#fedora' } };
vm.runInNewContext(src, { document, window, navigator: {}, console, setTimeout });

let failed = 0;
try {
  listeners.DOMContentLoaded();
} catch (e) {
  console.log('FAIL DOMContentLoaded threw: ' + e.message);
  failed++;
}
if (!tabs.fedora.classList.has('active')) { console.log('FAIL fedora tab not active'); failed++; }
if (!navTabs[1].classList.has('active')) { console.log('FAIL fedora nav button not active'); failed++; }
console.log(`switch-tab: ${failed} failed`);
process.exit(failed ? 1 : 0);
