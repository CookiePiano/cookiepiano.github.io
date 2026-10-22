import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../docs/assets/theme.js', import.meta.url), 'utf8');

function page({ saved = null, blocked = false } = {}) {
  const root = { dataset: {} };
  const meta = { content: '#ffffff' };
  const attributes = {};
  const handlers = {};
  const button = { hidden: true, setAttribute: (name, value) => { attributes[name] = value; }, addEventListener: (name, action) => { handlers[name] = action; } };
  let loaded = false;
  let ready;
  let storage;
  let preference = saved;
  const context = {
    document: {
      documentElement: root,
      querySelector: () => meta,
      querySelectorAll: () => loaded ? [button] : [],
      addEventListener: (name, callback) => { if (name === 'DOMContentLoaded') ready = callback; },
    },
    localStorage: {
      getItem: () => { if (blocked) throw new Error('Storage blocked'); return preference; },
      setItem: (key, value) => { if (blocked) throw new Error('Storage blocked'); preference = value; },
    },
    window: { addEventListener: (name, callback) => { if (name === 'storage') storage = callback; } },
  };
  vm.runInNewContext(source, context);
  return { root, meta, button, attributes, ready() { loaded = true; ready(); }, click() { handlers.click(); }, storage(event) { storage(event); }, saved() { return preference; } };
}

test('first visit is light before controls load', () => {
  const p = page();
  assert.equal(p.root.dataset.theme, 'light');
  assert.equal(p.meta.content, '#ffffff');
  p.ready();
  assert.equal(p.button.hidden, false);
  assert.equal(p.attributes['aria-pressed'], 'false');
});

test('saved dark choice is applied before the body and survives navigation', () => {
  const p = page({ saved: 'dark' });
  assert.equal(p.root.dataset.theme, 'dark');
  assert.equal(p.meta.content, '#15191f');
  p.ready();
  assert.equal(p.attributes['aria-pressed'], 'true');
});

test('manual toggle updates appearance, state and the next page', () => {
  const p = page();
  p.ready();
  p.click();
  assert.equal(p.root.dataset.theme, 'dark');
  assert.equal(p.saved(), 'dark');
  assert.equal(p.attributes['aria-pressed'], 'true');
  assert.equal(page({ saved: p.saved() }).root.dataset.theme, 'dark');
  p.click();
  assert.equal(p.root.dataset.theme, 'light');
  assert.equal(p.saved(), 'light');
});

test('blocked storage keeps the page and its toggle usable', () => {
  const p = page({ blocked: true });
  p.ready();
  assert.equal(p.root.dataset.theme, 'light');
  p.click();
  assert.equal(p.root.dataset.theme, 'dark');
  p.click();
  assert.equal(p.root.dataset.theme, 'light');
});

test('invalid saved preferences fall back to light', () => {
  assert.equal(page({ saved: 'system' }).root.dataset.theme, 'light');
});

test('other tabs synchronize explicit choices and reset to light on clear', () => {
  const p = page();
  p.ready();
  p.storage({ key: 'cookiepiano-theme', newValue: 'dark' });
  assert.equal(p.root.dataset.theme, 'dark');
  p.storage({ key: 'unrelated-key', newValue: 'light' });
  assert.equal(p.root.dataset.theme, 'dark');
  p.storage({ key: null, newValue: null });
  assert.equal(p.root.dataset.theme, 'light');
});
