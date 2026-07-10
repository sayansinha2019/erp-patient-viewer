/** Render Klarify explanation cards and clinical flags. */
function renderKlarifyResults(container, data) {
  container.innerHTML = '';
  const { humanized, flags = [], explanation_cards = [] } = data;
  let rendered = 0;

  if (humanized?.patient_summary) {
    const card = document.createElement('article');
    card.className = 'explanation-card';
    card.innerHTML = `
      <p class="card-label">SUMMARY</p>
      <p class="plain">${escapeHtml(humanized.patient_summary)}</p>
    `;
    container.appendChild(card);
    rendered++;
  }

  const cards = explanation_cards.length ? explanation_cards : [];
  for (const c of cards) {
    const card = document.createElement('article');
    card.className = 'explanation-card';
    card.innerHTML = `
      <p class="card-label">${escapeHtml(c.label || 'SECTION')}</p>
      <p class="clinical">${escapeHtml(c.clinical_text || '')}</p>
      <p class="plain">${escapeHtml(c.explanation || '')}</p>
    `;
    container.appendChild(card);
    rendered++;
  }

  for (const flag of flags) {
    const sev = flag.severity || 'informational';
    const card = document.createElement('article');
    card.className = `flag-card ${sev}`;
    const icon = sev === 'urgent' ? '●' : sev === 'advisory' ? '▲' : 'ℹ';
    card.innerHTML = `
      <h3>${icon} ${escapeHtml(flag.title || '')}</h3>
      <p>${escapeHtml(flag.body || '')}</p>
    `;
    container.appendChild(card);
    rendered++;
  }

  if (!rendered && humanized?.sections) {
    renderPrescriptionResults(container, data, null);
    return;
  }

  if (rendered === 0) {
    container.innerHTML = '<div class="empty">No explanation could be generated.</div>';
  }
}

/** Legacy section renderer (fallback). */
function renderPrescriptionResults(container, data, statusBarEl) {
  const { humanized } = data;
  const sections = humanized.sections || {};
  container.innerHTML = '';

  if (statusBarEl) {
    statusBarEl.innerHTML = '';
    const pipeline = humanized.pipeline_status || {};
    const items = [
      ['Parse', pipeline.parse_ok],
      ['Patient', pipeline.has_patient],
      ['Medication', pipeline.has_medication],
      ['Prescriber', pipeline.has_prescriber],
    ];
    for (const [label, ok] of items) {
      const b = document.createElement('span');
      b.className = 'badge' + (ok ? '' : ' warn');
      b.textContent = `${label}: ${ok ? 'OK' : '—'}`;
      statusBarEl.appendChild(b);
    }
  }

  if (humanized.patient_summary) {
    const narrative = document.createElement('div');
    narrative.className = 'explanation-card';
    narrative.innerHTML = `<p class="plain">${escapeHtml(humanized.patient_summary)}</p>`;
    container.appendChild(narrative);
  }

  for (const section of Object.values(sections)) {
    if (!section.items || !Object.keys(section.items).length) continue;
    const card = document.createElement('article');
    card.className = 'explanation-card';
    const h = document.createElement('p');
    h.className = 'card-label';
    h.textContent = section.title;
    card.appendChild(h);
    const ul = document.createElement('ul');
    ul.style.listStyle = 'none';
    ul.style.padding = '0';
    ul.style.margin = '0';
    for (const [k, v] of Object.entries(section.items)) {
      const li = document.createElement('li');
      li.style.marginBottom = '0.5rem';
      li.innerHTML = `<span style="color:var(--color-muted);font-size:0.875rem;">${escapeHtml(k)}</span><br><strong>${escapeHtml(v)}</strong>`;
      ul.appendChild(li);
    }
    card.appendChild(ul);
    container.appendChild(card);
  }
}

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text || '';
  return d.innerHTML;
}
