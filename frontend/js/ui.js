// Shared UI helpers: escaping, DOM building, modal + form, toast, confirm.
const UI = (() => {
  // HTML-escape any user/content supplied text before injecting as text.
  function esc(v) {
    if (v === null || v === undefined) return '';
    return String(v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // Toast notifications
  function toast(msg, kind = 'ok', duration = 2600) {
    const host = document.getElementById('toast-host');
    const el = document.createElement('div');
    el.className = 'toast ' + (kind === 'err' ? 'err' : kind === 'ok' ? 'ok' : '');
    el.textContent = msg;
    host.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 250); }, duration);
  }

  // Modal open/close
  let _modalKeyHandler = null;
  function openModal(html) {
    const host = document.getElementById('modal-host');
    document.getElementById('modal').innerHTML = html;
    host.classList.remove('hidden');
    host.querySelector('.modal-backdrop').onclick = closeModal;
    // Map Enter -> primary/Save action and Esc -> Cancel/Close for every modal.
    if (_modalKeyHandler) document.removeEventListener('keydown', _modalKeyHandler);
    _modalKeyHandler = (ev) => {
      const hostEl = document.getElementById('modal-host');
      const modal = document.getElementById('modal');
      if (!modal || !hostEl || hostEl.classList.contains('hidden')) return;
      if (ev.key === 'Escape') {
        const btn = modal.querySelector('[data-cancel]') || modal.querySelector('[data-x]');
        ev.preventDefault();
        if (btn) btn.click(); else closeModal();
      } else if (ev.key === 'Enter') {
        const t = ev.target || {};
        const tag = t.tagName || '';
        // Don't hijack Enter inside multi-line text, multi-selects, or when a
        // button already has focus (Enter activates it natively).
        if (tag === 'TEXTAREA' || tag === 'BUTTON') return;
        if (tag === 'SELECT' && t.multiple) return;
        const ok = modal.querySelector('[data-ok]') || modal.querySelector('[data-save]');
        if (ok) { ev.preventDefault(); ok.click(); }
      }
    };
    document.addEventListener('keydown', _modalKeyHandler);
  }
  function closeModal() {
    document.getElementById('modal-host').classList.add('hidden');
    document.getElementById('modal').innerHTML = '';
    if (_modalKeyHandler) { document.removeEventListener('keydown', _modalKeyHandler); _modalKeyHandler = null; }
  }

  // Confirm dialog -> returns a Promise<boolean>
  function confirm(title, message, { danger = false, okLabel = 'Confirm' } = {}) {
    return new Promise((resolve) => {
      openModal(`
        <div class="modal-head"><h2>${esc(title)}</h2>
          <button class="icon-btn" data-x>×</button></div>
        <div class="modal-body"><p class="muted">${esc(message)}</p></div>
        <div class="modal-foot">
          <button class="btn ghost" data-cancel>Cancel</button>
          <button class="btn ${danger ? 'danger' : 'primary'}" data-ok>${esc(okLabel)}</button>
        </div>`);
      const m = document.getElementById('modal');
      const done = (val) => { closeModal(); resolve(val); };
      m.querySelector('[data-x]').onclick = () => done(false);
      m.querySelector('[data-cancel]').onclick = () => done(false);
      m.querySelector('[data-ok]').onclick = () => done(true);
    });
  }

  // Build a form modal from a field spec. Returns Promise<values|null>.
  // fields: [{key,label,type,required,options,value,placeholder,half}]
  function formModal(title, fields, initial = {}) {
    return new Promise((resolve) => {
      const body = fields.map((f) => renderField(f, initial[f.key])).join('');
      openModal(`
        <div class="modal-head"><h2>${esc(title)}</h2>
          <button class="icon-btn" data-x>×</button></div>
        <div class="modal-body"><form id="mform">${body}</form></div>
        <div class="modal-foot">
          <button class="btn ghost" data-cancel>Cancel</button>
          <button class="btn primary" data-ok>Save</button>
        </div>`);
      const m = document.getElementById('modal');
      const done = (val) => { closeModal(); resolve(val); };
      m.querySelector('[data-x]').onclick = () => done(null);
      m.querySelector('[data-cancel]').onclick = () => done(null);
      m.querySelector('[data-ok]').onclick = () => {
        const form = document.getElementById('mform');
        const out = {};
        let ok = true;
        fields.forEach((f) => {
          const el = form.elements[f.key];
          let v = el ? el.value.trim() : '';
          if (f.required && !v) { el.style.borderColor = 'var(--red)'; ok = false; }
          if (f.type === 'number') v = v === '' ? null : Number(v);
          out[f.key] = v === '' ? null : v;
        });
        if (!ok) { toast('Please fill required fields', 'err'); return; }
        done(out);
      };
    });
  }

  function renderField(f, val) {
    const v = val !== undefined && val !== null ? val : (f.value ?? '');
    let control;
    if (f.type === 'select') {
      const opts = (f.options || []).map((o) => {
        const ov = typeof o === 'object' ? o.value : o;
        const ol = typeof o === 'object' ? o.label : o;
        return `<option value="${esc(ov)}" ${String(ov) === String(v) ? 'selected' : ''}>${esc(ol)}</option>`;
      }).join('');
      control = `<select name="${esc(f.key)}">${f.required ? '' : '<option value=""></option>'}${opts}</select>`;
    } else if (f.type === 'textarea') {
      control = `<textarea name="${esc(f.key)}" rows="3" placeholder="${esc(f.placeholder || '')}">${esc(v)}</textarea>`;
    } else if (f.type === 'date') {
      control = `<input type="date" name="${esc(f.key)}" value="${esc(v)}" />`;
    } else if (f.type === 'time') {
      // step=1 exposes a seconds field so the value is full HH:MM:SS.
      control = `<input type="time" step="1" name="${esc(f.key)}" value="${esc(v)}" />`;
    } else if (f.type === 'duration') {
      // Free HH:MM:SS entry (elapsed time can exceed 24h, so not <input type=time>).
      control = `<input type="text" name="${esc(f.key)}" value="${esc(v)}" placeholder="${esc(f.placeholder || 'HH:MM:SS')}" pattern="[0-9]{1,3}:[0-5][0-9]:[0-5][0-9]" inputmode="numeric" />`;
    } else {
      const t = f.type === 'number' ? 'number' : 'text';
      control = `<input type="${t}" name="${esc(f.key)}" value="${esc(v)}" placeholder="${esc(f.placeholder || '')}" />`;
    }
    return `<div class="field">
      <label>${esc(f.label)}${f.required ? ' <span style="color:var(--red)">*</span>' : ''}</label>
      ${control}</div>`;
  }

  function el(html) { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstChild; }

  function empty(icon, msg, actionHtml = '') {
    return `<div class="empty"><div class="big">${icon}</div><div>${esc(msg)}</div>${actionHtml}</div>`;
  }

  return { esc, toast, openModal, closeModal, confirm, formModal, el, empty };
})();
