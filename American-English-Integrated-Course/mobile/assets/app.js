(function () {
  'use strict';

  const STORAGE_KEY = 'ae-course-completed-v1';
  const FONT_KEY = 'ae-course-font-size-v1';
  const root = document.body.dataset.root || './';
  const readCompleted = () => {
    try { return new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')); }
    catch (_) { return new Set(); }
  };
  const completed = readCompleted();
  const units = (window.COURSE && window.COURSE.units) || [];

  function save() { localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(completed).sort())); }
  function updateProgress() {
    const total = units.length;
    const done = units.filter((unit) => completed.has(unit.id)).length;
    document.querySelectorAll('[data-course-progress]').forEach((el) => { el.textContent = `${done} / ${total} 个单元`; });
    document.querySelectorAll('[data-progress-bar]').forEach((el) => { el.style.width = `${total ? done / total * 100 : 0}%`; });
    const byBook = {};
    units.forEach((unit) => { byBook[unit.book] = (byBook[unit.book] || 0) + (completed.has(unit.id) ? 1 : 0); });
    document.querySelectorAll('[data-book-progress]').forEach((el) => { const book = el.dataset.bookProgress; const totalBook = units.filter((unit) => String(unit.book) === String(book)).length; el.textContent = `${byBook[book] || 0} / ${totalBook}`; });
    document.querySelectorAll('[data-book-progress-bar]').forEach((el) => { const book = el.dataset.bookProgressBar; const totalBook = units.filter((unit) => String(unit.book) === String(book)).length; el.style.width = `${totalBook ? (byBook[book] || 0) / totalBook * 100 : 0}%`; });
    document.querySelectorAll('[data-book-counter]').forEach((el) => { const book = el.dataset.bookCounter; const totalBook = units.filter((unit) => String(unit.book) === String(book)).length; el.textContent = `${byBook[book] || 0}/${totalBook}`; });
    document.querySelectorAll('[data-unit]').forEach((row) => {
      const id = row.dataset.unit;
      const doneRow = completed.has(id);
      row.classList.toggle('is-complete', doneRow);
      const state = row.querySelector('.unit-state');
      if (state) state.textContent = doneRow ? '已完成' : '未学习';
    });
    const continueLink = document.querySelector('[data-continue]');
    if (continueLink) {
      const next = units.find((unit) => !completed.has(unit.id)) || units[units.length - 1];
      if (next) continueLink.href = root + next.path;
      continueLink.textContent = completed.size ? (completed.size === total ? '复习最后一个单元' : '继续我的学习') : '开始学习';
    }
  }

  function setupComplete() {
    const id = document.body.dataset.unitId;
    const button = document.querySelector('[data-mark-complete]');
    if (!id || !button) return;
    const paint = () => { const done = completed.has(id); button.classList.toggle('is-complete', done); button.textContent = done ? '已完成本单元 ✓' : '标记本单元完成'; button.setAttribute('aria-pressed', String(done)); };
    button.addEventListener('click', () => { if (completed.has(id)) completed.delete(id); else completed.add(id); save(); paint(); updateProgress(); });
    paint();
  }

  function setupFontSize() {
    const allowed = ['small', 'normal', 'large'];
    const saved = localStorage.getItem(FONT_KEY) || 'normal';
    const apply = (size) => { const value = allowed.includes(size) ? size : 'normal'; document.documentElement.style.setProperty('--reading-size', value === 'small' ? '.92rem' : value === 'large' ? '1.12rem' : '1rem'); document.querySelectorAll('[data-font-size]').forEach((button) => button.classList.toggle('is-active', button.dataset.fontSize === value)); localStorage.setItem(FONT_KEY, value); };
    apply(saved);
    document.querySelectorAll('[data-font-size]').forEach((button) => button.addEventListener('click', () => apply(button.dataset.fontSize)));
  }

  function setupPlanHash() {
    if (document.body.classList.contains('page-plan') && window.location.hash) { const details = document.querySelector(window.location.hash); if (details && details.tagName === 'DETAILS') details.open = true; }
  }

  updateProgress();
  setupComplete();
  setupFontSize();
  setupPlanHash();
  if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register(root + 'sw.js').catch(() => {}));
})();
