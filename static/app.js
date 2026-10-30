const form = document.getElementById('plan-form');
const statusBox = document.getElementById('status');
const results = document.getElementById('results');
const submitButton = document.getElementById('submit-button');
let currentPlan = null;

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function status(message, error = false) {
  statusBox.hidden = !message;
  statusBox.textContent = message;
  statusBox.classList.toggle('error', error);
}
function programLabel(kind) { return ({artist:'Music salon', movie:'Film circle', book:'Story circle'})[kind] || kind; }

function render(plan) {
  currentPlan = plan;
  const seeds = document.getElementById('seed-strip');
  seeds.innerHTML = `<span class="seed-chip">♪ ${escapeHtml(plan.seeds[0].name)}</span><span class="seed-arrow">+</span><span class="seed-chip">▣ ${escapeHtml(plan.seeds[1].name)}</span><span class="seed-arrow">→</span><span class="seed-chip">✳ Shared taste</span>`;
  document.getElementById('cards').innerHTML = plan.programs.map((p, i) => `
    <article class="program-card">
      <div class="card-top"><div class="card-number">0${i+1} / ${escapeHtml(programLabel(p.kind))}</div>
        <h3>${escapeHtml(p.title)}</h3><div class="anchor">Qloo anchor · ${escapeHtml(p.anchor)}</div>
        <p class="card-why">${escapeHtml(p.why_it_fits)}</p></div>
      <div class="card-bottom"><div class="card-badges"><span class="badge">${p.duration} min</span><span class="badge">Staff review</span></div>
        <ul><li>${escapeHtml(p.steps[0] || p.opening)}</li><li>${escapeHtml(p.access_note)}</li></ul>
        <button class="approve-button" data-index="${i}">Choose this activity ↗</button></div>
    </article>`).join('');
  document.querySelectorAll('.approve-button').forEach(button => button.addEventListener('click', () => approve(Number(button.dataset.index))));
  document.getElementById('candidate-lists').innerHTML = Object.entries(plan.candidates).map(([kind, items]) => `
    <div class="candidate-list"><strong>${escapeHtml(kind)}</strong><span>${items.slice(0,3).map(escapeHtml).join(' · ')}</span></div>`).join('');
  document.getElementById('with-qloo').textContent = plan.programs.map(p => p.anchor).join(' · ');
  document.getElementById('trace-rows').innerHTML = plan.trace.map(t => `
    <div class="trace-row"><strong>${escapeHtml(t.agent)}</strong><span>${escapeHtml(t.result)}</span><small>${t.ms} ms</small>
    ${t.qloo_calls?.length ? `<div class="trace-calls">${t.qloo_calls.map(c => `${escapeHtml(c.endpoint)} · ${escapeHtml(c.purpose)} · ${c.cached ? 'cache' : c.status}`).join('<br>')}</div>` : ''}</div>`).join('');
  results.hidden = false;
  results.scrollIntoView({behavior:'smooth', block:'start'});
}

async function approve(index) {
  if (!currentPlan) return;
  status('Saving your choice for a printable run sheet…');
  try {
    const response = await fetch(`/api/plans/${currentPlan.id}/approve`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({program_index:index})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not approve this activity');
    document.querySelectorAll('.approve-button').forEach((b, i) => {b.textContent = i === index ? 'Selected ✓' : 'Choose this activity ↗'; b.classList.toggle('approved', i === index);});
    document.querySelector('.approved-panel')?.remove();
    const panel = document.createElement('div');
    panel.className = 'approved-panel';
    panel.innerHTML = `<div><strong>Ready for your review.</strong><p>${escapeHtml(data.program.title)} has been selected. Check the details, then print a run sheet.</p></div><button type="button" id="print-button">Print run sheet ↗</button>`;
    document.getElementById('cards').after(panel);
    document.getElementById('print-button').addEventListener('click', () => printSheet(data.program));
    status('Activity selected. Review it before running the session.');
    panel.scrollIntoView({behavior:'smooth', block:'center'});
  } catch (error) { status(error.message, true); }
}

function printSheet(p) {
  const sheet = document.getElementById('print-sheet');
  sheet.innerHTML = `<h1>MosaicHour · staff run sheet</h1><p>Selected activity for ${currentPlan.request.group_size} people · ${p.duration} minutes · supply budget up to $${p.budget_limit}</p>
    <h2>${escapeHtml(p.title)}</h2><p><strong>Qloo cultural anchor:</strong> ${escapeHtml(p.anchor)}</p><p>${escapeHtml(p.why_it_fits)}</p>
    <h3>Opening</h3><p>${escapeHtml(p.opening)}</p><h3>Facilitation steps</h3><ol>${p.steps.map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ol>
    <h3>Closing</h3><p>${escapeHtml(p.closing)}</p><h3>Question to ask</h3><p>${escapeHtml(p.host_prompt)}</p>
    <h3>Staff checks</h3><p>${escapeHtml(p.access_note)}</p><p>${escapeHtml(p.materials)}</p>
    <p class="print-note">This is a draft for staff judgment. Confirm suitability, availability, rights, and any needed accommodations. No health outcome is implied.</p>`;
  sheet.hidden = false;
  window.print();
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const fields = new FormData(form);
  const payload = {artist:String(fields.get('artist')).trim(), movie:String(fields.get('movie')).trim(),
    group_size:Number(fields.get('group_size')), minutes:Number(fields.get('minutes')),
    budget:Number(fields.get('budget')), access_need:String(fields.get('access_need'))};
  submitButton.disabled = true;
  status('Qloo is connecting both favorites across music, film and books. The agents are drafting three activities…');
  try {
    const response = await fetch('/api/plan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not create a plan');
    document.querySelector('.approved-panel')?.remove();
    render(data);
    status(`Three drafts ready. ${data.trace.flatMap(t => t.qloo_calls || []).length} Qloo calls informed this plan. Review and choose one.`);
  } catch (error) {status(error.message, true);} finally {submitButton.disabled = false;}
});
