/** Klarify shared UI helpers — toasts, busy buttons, safe fetch. */
(function () {
  function ensureToastHost() {
    let host = document.getElementById('toastHost');
    if (!host) {
      host = document.createElement('div');
      host.id = 'toastHost';
      host.className = 'toast-host';
      host.setAttribute('role', 'status');
      host.setAttribute('aria-live', 'polite');
      document.body.appendChild(host);
    }
    return host;
  }

  /** Non-blocking notification. kind: 'info' | 'success' | 'error' */
  window.toast = function (message, kind = 'info', ms = 3800) {
    const host = ensureToastHost();
    const el = document.createElement('div');
    el.className = `toast toast--${kind}`;
    el.textContent = message;
    host.appendChild(el);
    requestAnimationFrame(() => el.classList.add('is-visible'));
    setTimeout(() => {
      el.classList.remove('is-visible');
      setTimeout(() => el.remove(), 300);
    }, ms);
  };

  /** Show a spinner on a button and block double clicks. */
  window.setBusy = function (btn, busy) {
    if (!btn) return;
    if (busy) {
      btn.dataset.wasDisabled = btn.disabled ? '1' : '';
      btn.disabled = true;
      btn.classList.add('is-busy');
      btn.setAttribute('aria-busy', 'true');
    } else {
      btn.disabled = btn.dataset.wasDisabled === '1';
      btn.classList.remove('is-busy');
      btn.removeAttribute('aria-busy');
    }
  };

  function errorText(data, status) {
    const d = data && data.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d) && d.length) return d.map((x) => x.msg || String(x)).join(' ');
    if (status === 413) return 'File is too large.';
    if (status >= 500) return 'Something went wrong on our side. Please try again.';
    return `Request failed (${status}).`;
  }

  /** fetch + JSON with friendly errors. Throws Error with .status */
  window.apiFetch = async function (url, options = {}) {
    let res;
    try {
      res = await fetch(url, options);
    } catch (_) {
      const err = new Error('Network error — check your connection and try again.');
      err.status = 0;
      throw err;
    }
    let data = null;
    try { data = await res.json(); } catch (_) { /* non-JSON */ }
    if (!res.ok) {
      const err = new Error(errorText(data, res.status));
      err.status = res.status;
      throw err;
    }
    return data;
  };

  window.escapeHtml = function (text) {
    const d = document.createElement('div');
    d.textContent = text == null ? '' : String(text);
    return d.innerHTML;
  };

  window.formatDate = function (iso) {
    try {
      const lang = (sessionStorage.getItem('klarify_lang') || 'de');
      return new Date(iso).toLocaleString(lang, { dateStyle: 'medium', timeStyle: 'short' });
    } catch (_) {
      return iso || '';
    }
  };
})();
