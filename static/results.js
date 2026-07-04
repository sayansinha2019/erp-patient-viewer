/** Render prescription summary into a container element. */
function renderPrescriptionResults(container, data, statusBarEl) {
  const { humanized } = data;
  const sections = humanized.sections || {};
  container.innerHTML = '';

  if (statusBarEl) {
    statusBarEl.innerHTML = '';
    const pipeline = humanized.pipeline_status || {};
    const items = [
      ['Parse', pipeline.parse_ok],
      ['Patient data', pipeline.has_patient],
      ['Medication', pipeline.has_medication],
      ['Prescriber', pipeline.has_prescriber],
    ];
    for (const [label, ok] of items) {
      const b = document.createElement('span');
      b.className = 'badge' + (ok ? '' : ' warn');
      b.textContent = `${label}: ${ok ? 'OK' : 'Missing'}`;
      statusBarEl.appendChild(b);
    }
    const t = document.createElement('span');
    t.className = 'badge info';
    t.textContent = humanized.translated
      ? `Translated to ${humanized.target_language}`
      : 'English (base)';
    statusBarEl.appendChild(t);
    if (humanized.translation_provider === 'gemini') {
      const g = document.createElement('span');
      g.className = 'badge gemini';
      g.textContent = 'Powered by Gemini';
      statusBarEl.appendChild(g);
    } else if (humanized.translation_provider === 'offline' || humanized.translation_provider === 'cache') {
      const o = document.createElement('span');
      o.className = 'badge offline';
      o.textContent = humanized.from_cache ? 'From cache' : 'Offline labels';
      statusBarEl.appendChild(o);
    }
    if (data.erp) {
      const e = document.createElement('span');
      e.className = 'badge info';
      e.textContent = `Fachdienst: ${data.erp.mode}`;
      statusBarEl.appendChild(e);
    }
  }

  let rendered = 0;

  if (humanized.patient_summary) {
    const narrative = document.createElement('div');
    narrative.className = 'summary-narrative';
    const h = document.createElement('h2');
    h.textContent = 'What this means for you';
    const p = document.createElement('p');
    p.textContent = humanized.patient_summary;
    narrative.appendChild(h);
    narrative.appendChild(p);
    container.appendChild(narrative);
    rendered++;
  }

  for (const section of Object.values(sections)) {
    if (!section.items || !Object.keys(section.items).length) continue;
    const card = document.createElement('div');
    card.className = 'section-card';
    const h = document.createElement('h3');
    h.textContent = section.title;
    card.appendChild(h);
    const ul = document.createElement('ul');
    ul.className = 'kv-list';
    for (const [k, v] of Object.entries(section.items)) {
      const li = document.createElement('li');
      const keySpan = document.createElement('span');
      keySpan.className = 'key';
      keySpan.textContent = k;
      const valSpan = document.createElement('span');
      valSpan.className = 'val';
      valSpan.textContent = v;
      li.appendChild(keySpan);
      li.appendChild(valSpan);
      ul.appendChild(li);
    }
    card.appendChild(ul);
    container.appendChild(card);
    rendered++;
  }

  if (rendered === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = 'No summary sections returned. Check logs/erp-viewer.log on the server.';
    container.appendChild(empty);
  }

  return rendered;
}
