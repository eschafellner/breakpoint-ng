// Exercise the rendered booking script, including asynchronous failures and races.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

async function run(script) {
  const elements = Object.fromEntries([
    'noSelection', 'bookingForm', 'formCourtId', 'formStart', 'formEnd',
    'dispCourt', 'dispTime', 'dispTotal', 'bookSubmit', 'formExpectedTotal',
  ].map(id => [id, {value: '', textContent: '', style: {}, disabled: true}]));
  const guests = {value: 'Anna'};
  const checkbox = {value: '10', checked: false, disabled: false};
  const label = {dataset: {courts: '1,', mode: 'OPTIONAL'}, style: {}, querySelector: () => checkbox};
  const otherCheckbox = {value: '11', checked: false, disabled: false};
  const otherLabel = {dataset: {courts: '2,', mode: 'OPTIONAL'}, style: {}, querySelector: () => otherCheckbox};
  const fields = {court_id: elements.formCourtId, start: elements.formStart, end: elements.formEnd, guest_names: guests};
  const pending = [];
  const context = {
    AbortController, URLSearchParams, setTimeout, clearTimeout,
    document: {
      getElementById: id => elements[id],
      querySelector: selector => fields[selector.match(/name="([^"]+)"/)[1]],
      querySelectorAll: selector => selector.startsWith('label') ? [label, otherLabel] : [checkbox, otherCheckbox].filter(cb => cb.checked && !cb.disabled),
    },
    fetch: (url, options) => new Promise(resolve => pending.push({url, options, resolve})),
  };
  vm.createContext(context);
  vm.runInContext(script, context);
  const pause = () => new Promise(resolve => setTimeout(resolve, 260));
  context.selectSlot('1', "Platz O'Hara", '2026-10-04T10:00:00+02:00', '2026-10-04T11:00:00+02:00', '10:00', '11:00', {classList: {add() {}, remove() {}}});
  assert.equal(elements.bookSubmit.disabled, true);
  assert.equal(otherCheckbox.disabled, true);
  assert.equal(otherLabel.style.display, 'none');
  checkbox.checked = true;
  context.updatePrice();
  await pause();
  let request = pending.shift();
  const params = new URL(request.url, 'http://localhost').searchParams;
  assert.equal(params.get('court_id'), '1');
  assert.equal(params.get('guest_names'), 'Anna');
  assert.deepEqual(params.getAll('extras'), ['10']);
  request.resolve({ok: true, json: async () => ({total: '39.50'})});
  await pause();
  assert.equal(elements.dispTotal.textContent, '39.50 €');
  assert.equal(elements.formExpectedTotal.value, '39.50');
  assert.equal(elements.bookSubmit.disabled, false);

  context.updatePrice();
  assert.equal(elements.bookSubmit.disabled, true);
  assert.equal(elements.formExpectedTotal.value, '');
  await pause();
  request = pending.shift();
  request.resolve({ok: false, json: async () => ({error: 'Platz geschlossen.'})});
  await pause();
  assert.equal(elements.dispTotal.textContent, 'Platz geschlossen.');
  assert.equal(elements.bookSubmit.disabled, true);

  context.updatePrice();
  await pause();
  const stale = pending.shift();
  context.updatePrice();
  assert.equal(stale.options.signal.aborted, true);
  await pause();
  const latest = pending.shift();
  latest.resolve({ok: true, json: async () => ({total: '25.00'})});
  await pause();
  stale.resolve({ok: true, json: async () => ({total: '999.00'})});
  await pause();
  assert.equal(elements.formExpectedTotal.value, '25.00');
  assert.equal(elements.dispTotal.textContent, '25.00 €');

  context.updatePrice();
  await pause();
  pending.shift().resolve({ok: true, json: async () => ({total: 'invalid'})});
  await pause();
  assert.equal(elements.bookSubmit.disabled, true);
  assert.equal(elements.formExpectedTotal.value, '');
}

run(fs.readFileSync(0, 'utf8')).catch(error => {console.error(error); process.exitCode = 1;});
