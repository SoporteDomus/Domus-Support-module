/* Utilidades */
const $ = id => document.getElementById(id);
function fmt(v) { return v !== null && v !== undefined ? v.toLocaleString('es-CO') : '—'; }

function statusClass(status) {
    const map = { open: 'status-open', pending: 'status-pending', solved: 'status-solved', closed: 'status-closed', new: 'status-new' };
    return map[status] || 'status-closed';
}

function statusLabel(status) {
    const map = { open: 'Abierto', pending: 'Pendiente', solved: 'Resuelto', closed: 'Cerrado', new: 'Nuevo' };
    return map[status] || status;
}

function formatDate(dateStr) {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    return d.toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' });
}

/* Fecha de hoy como valor por defecto */
const todayISO = new Date().toISOString().split('T')[0];
$('date-from').value = todayISO;
$('date-to').value   = todayISO;

/* Tab Navigation */
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        $(btn.dataset.tab).classList.add('active');
    });
});

/* Lógica de Métricas */
let chartInstance = null;

async function run() {
    const dateFrom = $('date-from').value;
    const dateTo = $('date-to').value;
    if (!dateFrom || !dateTo) return;

    const btn = $('run');
    btn.disabled = true;

    ['res-content', 'causa-content'].forEach(id => $(id).classList.add('hidden'));
    ['res-loading', 'causa-loading'].forEach(id => $(id).classList.remove('hidden'));

    try {
        const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
        const [resJson, causaJson] = await Promise.all([
            fetch(`/api/resolution-metrics?${params}`).then(r => r.json()),
            fetch(`/api/causa-metrics?${params}`).then(r => r.json()),
        ]);

        $('m-tickets').textContent = fmt(resJson.tickets);

        const first = resJson.primera_resolucion || {};
        $('m-first-promedio').textContent = fmt(first.promedio);
        $('m-first-mediana').textContent  = fmt(first.mediana);
        $('m-first-minimo').textContent   = fmt(first.minimo);
        $('m-first-maximo').textContent   = fmt(first.maximo);

        const full = resJson.resolucion_final || {};
        $('m-full-tickets').textContent  = fmt(full.tickets_reabiertos ?? 0);
        $('m-full-promedio').textContent = fmt(full.promedio);
        $('m-full-mediana').textContent  = fmt(full.mediana);
        $('m-full-minimo').textContent   = fmt(full.minimo);
        $('m-full-maximo').textContent   = fmt(full.maximo);

        const tbody = $('causa-tbody');
        tbody.innerHTML = '';
        causaJson.tabla.forEach(row => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${row.causa}</td><td class="num">${row.cantidad}</td>`;
            tbody.appendChild(tr);
        });

        renderChart(causaJson.tabla);

        $('res-loading').classList.add('hidden');
        $('res-content').classList.remove('hidden');
        $('causa-loading').classList.add('hidden');
        $('causa-content').classList.remove('hidden');

    } catch (err) {
        console.error(err);
    } finally {
        btn.disabled = false;
    }
}

function renderChart(data) {
    const labels = data.map(r => r.causa);
    const values = data.map(r => r.cantidad);
    if (chartInstance) chartInstance.destroy();
    const ctx = $('causa-chart').getContext('2d');
    chartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: '#5b6af0',
                borderRadius: 6
            }]
        },
        options: { indexAxis: 'y', plugins: { legend: { display: false } } }
    });
}

$('run').addEventListener('click', run);

/* Tag Picker */
class TagPicker {
    constructor(containerId) {
        this.container = $(containerId);
        this.selected = new Set();
        this._build();
    }

    _build() {
        this.trigger = document.createElement('div');
        this.trigger.className = 'tag-picker-trigger';
        this.trigger.innerHTML = `
            <span class="tag-picker-trigger-text">Selecciona etiquetas…</span>
            <svg class="tag-picker-chevron" viewBox="0 0 16 16" fill="none">
                <path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>`;

        this.dropdown = document.createElement('div');
        this.dropdown.className = 'tag-picker-dropdown';

        const searchInput = document.createElement('input');
        searchInput.type = 'text';
        searchInput.className = 'tag-picker-search-input';
        searchInput.placeholder = 'Filtrar etiquetas…';
        searchInput.addEventListener('input', () => this._filter(searchInput.value));

        this.optionsEl = document.createElement('div');
        this.optionsEl.className = 'tag-picker-options';

        this.dropdown.appendChild(searchInput);
        this.dropdown.appendChild(this.optionsEl);
        this.container.appendChild(this.trigger);
        this.container.appendChild(this.dropdown);

        this.trigger.addEventListener('click', () => this.toggle());
        document.addEventListener('click', e => { if (!this.container.contains(e.target)) this.close(); });
    }

    _filter(query) {
        const q = query.toLowerCase();
        this.optionsEl.querySelectorAll('.tag-picker-option').forEach(opt => {
            opt.style.display = opt.querySelector('span').textContent.toLowerCase().includes(q) ? '' : 'none';
        });
    }

    _updateTrigger() {
        const textEl = this.trigger.querySelector('.tag-picker-trigger-text');
        if (this.selected.size === 0) {
            textEl.textContent = 'Selecciona etiquetas…';
            textEl.classList.remove('has-selection');
        } else {
            const n = this.selected.size;
            textEl.textContent = `${n} etiqueta${n > 1 ? 's' : ''} seleccionada${n > 1 ? 's' : ''}`;
            textEl.classList.add('has-selection');
        }
    }

    populate(tags) {
        this.selected.clear();
        this.optionsEl.innerHTML = '';
        if (!tags.length) {
            const empty = document.createElement('div');
            empty.className = 'tag-picker-empty';
            empty.textContent = 'No hay etiquetas disponibles';
            this.optionsEl.appendChild(empty);
            return;
        }
        tags.forEach(tag => {
            const label = document.createElement('label');
            label.className = 'tag-picker-option';
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.value = tag;
            cb.addEventListener('change', () => {
                if (cb.checked) this.selected.add(tag);
                else this.selected.delete(tag);
                this._updateTrigger();
            });
            const span = document.createElement('span');
            span.textContent = tag;
            label.appendChild(cb);
            label.appendChild(span);
            this.optionsEl.appendChild(label);
        });
        this._updateTrigger();
    }

    toggle() { this.dropdown.classList.contains('open') ? this.close() : this.open(); }

    open() {
        this.dropdown.classList.add('open');
        this.trigger.classList.add('open');
        const si = this.dropdown.querySelector('.tag-picker-search-input');
        if (si) { si.value = ''; this._filter(''); si.focus(); }
    }

    close() {
        this.dropdown.classList.remove('open');
        this.trigger.classList.remove('open');
    }

    getSelected() { return [...this.selected]; }
}

/* Instancias de los pickers */
const explorerPicker = new TagPicker('tag-picker-explorer');
const searchPicker   = new TagPicker('tag-picker-search');

/* Carga inicial de etiquetas desde Zendesk */
async function loadTags() {
    try {
        const data = await fetch('/api/tags').then(r => r.json());
        const tags = data.tags || [];
        explorerPicker.populate(tags);
        searchPicker.populate(tags);
    } catch (e) { console.error('Error cargando etiquetas:', e); }
}

loadTags();

/* Lógica IA — Explorador */
function buildTicketCard(t) {
    const card = document.createElement('div');
    card.className = 'ticket-card';
    const tagsHtml = (t.tags || []).map(tag =>
        `<span style="display:inline-block;padding:1px 7px;border-radius:12px;font-size:11px;background:rgba(91,106,240,.15);color:var(--accent);margin-right:4px;">${tag}</span>`
    ).join('');
    card.innerHTML = `
        <div class="ticket-id">#${t.id}</div>
        <div class="ticket-body">
            <div class="ticket-subject">${t.subject}</div>
            <div class="ticket-description" style="font-size:0.85rem;color:#888;margin-top:4px;line-height:1.4;">${t.description || 'Sin descripción'}</div>
            <div class="ticket-meta" style="margin-top:6px;">
                <span>📅 ${formatDate(t.created_at)}</span>
                ${tagsHtml ? `<span style="margin-left:8px;">${tagsHtml}</span>` : ''}
            </div>
        </div>
        <div class="ticket-status ${statusClass(t.status)}">${statusLabel(t.status)}</div>`;
    return card;
}

async function runAi() {
    const tags = explorerPicker.getSelected();
    if (!tags.length) return;

    $('ai-empty').classList.add('hidden');
    $('ai-results').classList.add('hidden');
    $('ai-loading').classList.remove('hidden');

    try {
        const params = new URLSearchParams({ limit: 5 });
        tags.forEach(t => params.append('tags', t));
        const data = await fetch(`/api/tickets-by-tags?${params}`).then(r => r.json());

        if (data.success === false) throw new Error(data.error);

        const list = $('ai-tickets-list');
        list.innerHTML = '';
        data.tickets.forEach(t => list.appendChild(buildTicketCard(t)));

        $('ai-loading').classList.add('hidden');
        $('ai-results').classList.remove('hidden');
    } catch (e) {
        console.error(e);
        $('ai-loading').classList.add('hidden');
        $('ai-empty').classList.remove('hidden');
    }
}

$('ai-run').addEventListener('click', runAi);

/* Lógica IA — Buscar ticket principal + relacionados */
async function runSearchCausa() {
    const ticketId = $('search-ticket-id').value;
    const tags     = searchPicker.getSelected();
    const errorMsg = $('search-error-msg');

    if (!ticketId || !tags.length) {
        errorMsg.textContent = 'Por favor, ingrese un ID de ticket y seleccione al menos una etiqueta.';
        errorMsg.classList.remove('hidden');
        return;
    }

    errorMsg.classList.add('hidden');
    $('search-results').classList.add('hidden');
    $('search-loading').classList.remove('hidden');

    try {
        const params = new URLSearchParams({ limit: 5 });
        tags.forEach(t => params.append('tags', t));

        const [ticketRes, relatedRes] = await Promise.all([
            fetch(`/api/ticket/${ticketId}`).then(r => r.json()),
            fetch(`/api/tickets-by-tags?${params}`).then(r => r.json()),
        ]);

        if (!ticketRes.success) throw new Error(ticketRes.error || 'Error al buscar el ticket principal');

        const prinCardContainer = $('search-principal-card');
        prinCardContainer.innerHTML = '';
        const t = ticketRes.ticket;
        const card = document.createElement('div');
        card.className = 'ticket-card';
        card.innerHTML = `
            <div class="ticket-id">#${t.id}</div>
            <div class="ticket-body">
                <div class="ticket-subject">${t.subject}</div>
                <div class="ticket-description" style="font-size:0.85rem;color:#888;margin-top:4px;line-height:1.4;">${t.description || 'Sin descripción'}</div>
                <div class="ticket-meta" style="margin-top:6px;"><span>📅 ${formatDate(t.created_at)}</span></div>
            </div>
            <div class="ticket-status ${statusClass(t.status)}">${statusLabel(t.status)}</div>`;
        prinCardContainer.appendChild(card);

        const relListContainer = $('search-related-list');
        relListContainer.innerHTML = '';
        (relatedRes.tickets || []).forEach(rt => relListContainer.appendChild(buildTicketCard(rt)));

        $('search-loading').classList.add('hidden');
        $('search-results').classList.remove('hidden');

    } catch (e) {
        console.error(e);
        errorMsg.textContent = e.message;
        errorMsg.classList.remove('hidden');
        $('search-loading').classList.add('hidden');
    }
}

$('search-run').addEventListener('click', runSearchCausa);

/* Generación de respuesta con IA */
async function generateAiResponse() {
    const ticketId = $('search-ticket-id').value;
    const tags     = searchPicker.getSelected();
    const genBtn   = $('ai-generate-btn');

    genBtn.disabled = true;
    $('ai-gen-result').classList.add('hidden');
    $('ai-gen-error').classList.add('hidden');
    $('ai-gen-loading').classList.remove('hidden');

    try {
        const res = await fetch('/api/generate-response', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticket_id: parseInt(ticketId), tags, extra_context: $('ai-extra-context').value.trim() || null }),
        }).then(r => r.json());

        if (!res.success) throw new Error(res.error);

        $('ai-gen-text').textContent = res.response;
        $('ai-gen-meta').textContent = `Basado en ${res.tickets_analyzed} tickets históricos analizados.`;
        $('ai-gen-loading').classList.add('hidden');
        $('ai-gen-result').classList.remove('hidden');
    } catch (e) {
        $('ai-gen-error').textContent = e.message;
        $('ai-gen-error').classList.remove('hidden');
        $('ai-gen-loading').classList.add('hidden');
    } finally {
        genBtn.disabled = false;
    }
}

$('ai-generate-btn').addEventListener('click', generateAiResponse);