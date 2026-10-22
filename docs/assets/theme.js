(() => {
  'use strict';
  const key = 'cookiepiano-theme';
  const root = document.documentElement;
  const applyTheme = (value) => {
    const dark = value === 'dark';
    root.dataset.theme = dark ? 'dark' : 'light';
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = dark ? '#15191f' : '#ffffff';
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      button.setAttribute('aria-pressed', String(dark));
    });
  };
  let initial = 'light';
  try { initial = localStorage.getItem(key); } catch { /* Storage is optional. */ }
  applyTheme(initial);
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      button.hidden = false;
      button.setAttribute('aria-pressed', String(root.dataset.theme === 'dark'));
      button.addEventListener('click', () => {
        const theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
        applyTheme(theme);
        try { localStorage.setItem(key, theme); } catch { /* Keep the in-page choice. */ }
      });
    });
  });
  window.addEventListener('storage', (event) => {
    if (event.key === key || event.key === null) applyTheme(event.newValue);
  });
})();
