/* ═══════════════════════════════════════════════════════════════
   STATE
════════════════════════════════════════════════════════════════ */
const state = {
  uploaded:    false,
  querying:    false,
  dataset:     { name: '', rows: 0, columns: [] },
  masterSchema: {},   // { column_name: "NUM"|"TEXT"|"DATE" } - single source of truth
  chartMap:    {},   // id -> Chart instance
  tableData:   {},   // msgId -> { columns, allRows, page, sql }
  sidebarOpen: true,
  leftSidebarOpen: true,
  lastSQL:     '',
  overview:    null,
  // Viz modal state
  vizModal:    { msgId: null, chart: null },
};

const PAGE_SIZE = 20;

/* ═══════════════════════════════════════════════════════════════
   DOM REFS
════════════════════════════════════════════════════════════════ */
const uploadScreen      = document.getElementById('uploadScreen');
const chatScreen        = document.getElementById('chatScreen');
const uploadZone        = document.getElementById('uploadZone');
const fileInput         = document.getElementById('fileInput');
const uploadIconEl      = document.getElementById('uploadIconEl');
const uploadTitleEl     = document.getElementById('uploadTitleEl');
const uploadHintEl      = document.getElementById('uploadHintEl');
const uploadError       = document.getElementById('uploadError');

const datasetName       = document.getElementById('datasetName');
const datasetMeta       = document.getElementById('datasetMeta');
const newChatBtn        = document.getElementById('newChatBtn');
const chatMain          = document.getElementById('chatMain');
const emptyState        = document.getElementById('emptyState');
const messagesContainer = document.getElementById('messagesContainer');
const leftSidebar       = document.getElementById('leftSidebar');
const leftSidebarToggle = document.getElementById('leftSidebarToggle');
const leftSidebarClose  = document.getElementById('leftSidebarClose');
const datasetOverview   = document.getElementById('datasetOverview');

const inputBarWrap      = document.querySelector('.input-bar-wrap');
const chatInput         = document.getElementById('chatInput');
const sendBtn           = document.getElementById('sendBtn');

// Viz modal elements
const vizModal          = document.getElementById('vizModal');
const vizModalClose     = document.getElementById('vizModalClose');
const vizChartTypeGrid  = document.getElementById('vizChartTypeGrid');
const vizXAxis          = document.getElementById('vizXAxis');
const vizYAxis          = document.getElementById('vizYAxis');
const vizAggRow         = document.getElementById('vizAggRow');
const vizGenerateBtn    = document.getElementById('vizGenerateBtn');
const vizPreviewEmpty   = document.getElementById('vizPreviewEmpty');
const vizPreviewChart   = document.getElementById('vizPreviewChart');
const vizModalCanvas    = document.getElementById('vizModalCanvas');
const vizAIRec          = document.getElementById('vizAIRec');
const vizAIRecText      = document.getElementById('vizAIRecText');
const vizRecChips       = document.getElementById('vizRecChips');

/* ═══════════════════════════════════════════════════════════════
   UPLOAD
════════════════════════════════════════════════════════════════ */
uploadZone.addEventListener('click', (e) => {
  if (e.target !== fileInput) fileInput.click();
});
fileInput.addEventListener('change', () => {
  if (fileInput.files.length) doUpload(fileInput.files[0]);
});
uploadZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  uploadZone.classList.add('dragover');
});
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
uploadZone.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadZone.classList.remove('dragover');
  const f = e.dataTransfer.files[0];
  if (f) doUpload(f);
});

async function doUpload(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['csv', 'xlsx', 'xls', 'tsv', 'txt'].includes(ext)) {
    showUploadError('Only CSV (.csv) and Excel (.xlsx, .xls) files are supported.');
    return;
  }
  uploadError.style.display = 'none';
  uploadZone.classList.add('uploading');
  uploadIconEl.innerHTML = iconSpinner();
  uploadTitleEl.textContent = 'Uploading…';
  uploadHintEl.textContent  = file.name;

  const fd = new FormData();
  fd.append('file', file);

  try {
    const res  = await fetch('/upload', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) { showUploadError(data.error || 'Upload failed.'); return; }

    state.dataset = { name: file.name, rows: data.rows, columns: data.columns };
    state.uploaded = true;

    // Store master schema from backend (single source of truth)
    state.masterSchema = data.schema || {};

    // Store dataset preview rows for chart builder
    state.previewTruncated = !!data.preview_truncated;
    state.previewRowCount = data.preview_row_count || 0;

    uploadZone.classList.remove('uploading');
    uploadZone.classList.add('success');
  uploadIconEl.innerHTML = iconCheck();
    uploadTitleEl.textContent = `${file.name} uploaded!`;
    uploadHintEl.textContent  = `${data.rows.toLocaleString()} rows · ${data.columns.length} columns`;

    setTimeout(() => transitionToChat(data), 800);

  } catch {
    showUploadError('Upload failed. Please check your connection.');
    uploadZone.classList.remove('uploading');
    uploadIconEl.innerHTML = iconFolder();
    uploadTitleEl.textContent = 'Drag & drop your dataset here';
    uploadHintEl.textContent  = 'or click to browse';
  }
}

function showUploadError(msg) {
  uploadError.textContent = msg;
  uploadError.style.display = 'block';
  uploadZone.classList.remove('uploading', 'success');
  uploadIconEl.innerHTML = iconFolder();
  uploadTitleEl.textContent = 'Drag & drop your dataset here';
  uploadHintEl.textContent  = 'or click to browse';
}

/* ═══════════════════════════════════════════════════════════════
   TRANSITION UPLOAD → CHAT
════════════════════════════════════════════════════════════════ */
function transitionToChat(data) {
  datasetName.textContent = state.dataset.name;
  datasetMeta.textContent = `${data.rows.toLocaleString()} rows · ${data.columns.length} cols`;

  // Initialize master entry for visualizations with preview rows from upload
  state.previewTruncated = !!data.preview_truncated;
  state.previewRowCount = data.preview_row_count || 0;
  state.tableData['master'] = {
    columns: data.columns,
    allRows: data.preview_rows || [],
    page: 0,
    sql: 'SELECT * FROM dataset'
  };

  // Dataset Overview in Sidebar
  populateOverview(data);

  uploadScreen.style.display = 'none';
  chatScreen.style.display   = 'flex';
  inputBarWrap.classList.add('visible');
  chatInput.focus();

  // On tablet/mobile, the sidebar is an overlay drawer - start collapsed
  if (window.innerWidth <= 1100 && state.leftSidebarOpen) {
    state.leftSidebarOpen = false;
    leftSidebar.classList.add('hidden');
  }
}

function populateOverview(data) {
  // Fetch full overview from backend for enhanced data
  fetch('/dataset-overview')
    .then(res => res.json())
    .then(overview => {
      if (!overview.success) return;
      state.overview = overview;
      
      const elRows = document.getElementById('sbRows');
      const elCols = document.getElementById('sbCols');
      const elSize = document.getElementById('sbSize');
      const elNum  = document.getElementById('sbNum');
      const elCat  = document.getElementById('sbCat');
      const elDate = document.getElementById('sbDate');
      const elBool = document.getElementById('sbBool');
      const elMissing = document.getElementById('sbMissing');
      const elDupes   = document.getElementById('sbDupes');
      const elHealth  = document.getElementById('sbHealth');

      if (elRows) elRows.textContent = overview.total_records.toLocaleString();
      if (elCols) elCols.textContent = overview.total_columns;
      if (elSize) elSize.textContent = overview.dataset_size;
      if (elNum)  elNum.textContent  = overview.column_types.numeric;
      if (elCat)  elCat.textContent  = overview.column_types.categorical;
      if (elDate) elDate.textContent = overview.column_types.date;
      if (elBool) elBool.textContent = overview.column_types.boolean;
      
      // Missing values
      const mv = overview.data_quality.total_missing_values;
      const mp = overview.data_quality.missing_percentage;
      if (elMissing) {
        elMissing.textContent = mv > 0 ? `${mv.toLocaleString()} (${mp}%)` : '0';
        elMissing.title = mv > 0 ? `${mv.toLocaleString()} missing (${mp}%)` : 'No missing values';
      }
      
      // Duplicates
      const dupes = overview.data_quality.duplicate_records;
      if (elDupes) elDupes.textContent = dupes > 0 ? dupes.toLocaleString() : '0';
      
      // Health score
      const hs = overview.health_score;
      const elHealthFill = document.getElementById('sbHealthFill');
      const elHealthStatus = document.getElementById('sbHealthStatus');
      const healthWidget = document.getElementById('sbHealthWidget');
      const statusKey = (hs.status || '').toLowerCase();
      if (elHealth) elHealth.textContent = `${hs.score}`;
      if (elHealthFill) elHealthFill.style.width = `${hs.score}%`;
      if (elHealthStatus) {
        elHealthStatus.textContent = hs.status;
        elHealthStatus.className = `metric-health-status status-${statusKey}`;
      }
      if (healthWidget) healthWidget.dataset.status = statusKey;
      
      // Update dataset meta if available
      const datasetMeta = document.getElementById('datasetMeta');
      if (datasetMeta) {
        datasetMeta.textContent = `${overview.total_records.toLocaleString()} rows · ${overview.total_columns} cols · ${overview.dataset_size}`;
      }
    })
    .catch(err => {
      console.warn('Failed to fetch dataset overview:', err);
      // Fallback: use basic upload data
      const cols = data.columns || [];
      const elRows = document.getElementById('sbRows');
      const elCols = document.getElementById('sbCols');
      const elNum  = document.getElementById('sbNum');
      const elCat  = document.getElementById('sbCat');
      if (elRows) elRows.textContent = (data.rows || 0).toLocaleString();
      if (elCols) elCols.textContent = cols.length;
      
      // Simple classification fallback
      let numCols = [], catCols = [];
      if (Object.keys(state.masterSchema).length > 0) {
        const classified = classifyColumnsFromSchema(cols);
        numCols = classified.numCols;
        catCols = classified.catCols;
      } else {
        const numericHints = /id|num|count|qty|amount|price|sales|revenue|age|score|gpa|salary|total|rate|value|profit|cost|quantity|percent|ratio/;
        const dateHints    = /date|time|year|month|day|period|created|updated/;
        numCols = cols.filter(c => numericHints.test(c.toLowerCase()));
        catCols = cols.filter(c => !numericHints.test(c.toLowerCase()) && !dateHints.test(c.toLowerCase()));
      }
      if (elNum) elNum.textContent = numCols.length;
      if (elCat) elCat.textContent = catCols.length;
    });
}

async function showDatasetOverview() {
  if (!state.uploaded) return;

  emptyState.style.display = 'none';
  messagesContainer.style.display = 'none';
  datasetOverview.style.display = 'block';
  inputBarWrap.classList.remove('visible');
  document.querySelectorAll('.sidebar-nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === 'overview');
  });
  chatMain.scrollTo({ top: 0, behavior: 'smooth' });

  const loading = document.getElementById('overviewLoading');
  const content = document.getElementById('overviewContent');
  const error = document.getElementById('overviewError');
  loading.style.display = 'flex';
  content.style.display = 'none';
  error.style.display = 'none';

  try {
    const overview = state.overview || await fetchDatasetOverview();
    state.overview = overview;
    renderDatasetOverview(overview);
    loading.style.display = 'none';
    content.style.display = 'block';
  } catch (err) {
    loading.style.display = 'none';
    error.textContent = err.message || 'Unable to generate the dataset overview.';
    error.style.display = 'block';
  }
}

async function fetchDatasetOverview() {
  const response = await fetch('/dataset-overview');
  const data = await response.json();
  if (!response.ok || !data.success) {
    throw new Error(data.error || 'Unable to generate the dataset overview.');
  }
  return data;
}

function closeDatasetOverview() {
  if (!datasetOverview) return;
  datasetOverview.style.display = 'none';
  messagesContainer.style.display = 'flex';
  emptyState.style.display = messagesContainer.children.length ? 'none' : 'block';
  inputBarWrap.classList.add('visible');
  document.querySelectorAll('.sidebar-nav-item').forEach(item => item.classList.remove('active'));
  chatInput.focus();
}

function renderDatasetOverview(overview) {
  const statCard = (label, value, icon) => `
    <div class="overview-stat-card">
      <i class="ti ${icon}"></i>
      <div><span>${escHtml(String(label))}</span><strong>${escHtml(String(value))}</strong></div>
    </div>`;

  document.getElementById('overviewSummary').innerHTML = [
    statCard('Total Records', overview.total_records.toLocaleString(), 'ti-list-numbers'),
    statCard('Total Columns', overview.total_columns, 'ti-columns'),
    statCard('Dataset / File Size', overview.dataset_size, 'ti-database'),
    statCard('Health Score', `${overview.health_score.score} / 100`, 'ti-heartbeat'),
  ].join('');

  document.getElementById('overviewTypes').innerHTML = [
    statCard('Numeric Columns', overview.column_types.numeric, 'ti-numbers'),
    statCard('Categorical Columns', overview.column_types.categorical, 'ti-tags'),
    statCard('Date/Time Columns', overview.column_types.date, 'ti-calendar'),
    statCard('Boolean Columns', overview.column_types.boolean, 'ti-toggle-left'),
  ].join('');

  document.getElementById('overviewSchemaBody').innerHTML = overview.schema_details.map(item => `
    <tr>
      <td><strong>${escHtml(item.column_name)}</strong></td>
      <td><span class="overview-type-badge">${escHtml(item.sqlite_type)}</span></td>
      <td>${item.sample_values.length ? item.sample_values.map(value => escHtml(value)).join(', ') : '<span class="overview-muted">No non-null samples</span>'}</td>
    </tr>`).join('');

  const detailRow = (label, value) => `
    <div class="overview-detail-row"><span>${escHtml(label)}</span><strong>${escHtml(String(value))}</strong></div>`;
  const quality = overview.data_quality;
  document.getElementById('overviewQuality').innerHTML = [
    detailRow('Total Missing Values', quality.total_missing_values.toLocaleString()),
    detailRow('Missing Value Percentage', `${quality.missing_percentage}%`),
    detailRow('Duplicate Record Count', quality.duplicate_records.toLocaleString()),
    detailRow('Empty Columns', quality.empty_columns),
    detailRow('Data Consistency', `${quality.consistency_percentage}%`),
  ].join('');

  const keys = overview.key_fields;
  document.getElementById('overviewKeys').innerHTML = [
    detailRow('Primary Identifier', keys.primary_id || 'Not detected'),
    detailRow('Date Column', keys.date_column || 'Not detected'),
    detailRow('Main Measures', keys.measure_columns.length ? keys.measure_columns.join(', ') : 'Not detected'),
  ].join('');

  const health = overview.health_score;
  document.getElementById('overviewHealth').innerHTML = `
    <div class="overview-health">
      <div class="overview-health-score"><strong>${health.score}</strong><span>/100</span></div>
      <div class="overview-health-copy">
        <span class="overview-health-status status-${health.status.toLowerCase()}">${escHtml(health.status)}</span>
        <div class="overview-health-track"><span style="width:${health.score}%"></span></div>
      </div>
    </div>`;
}

function exportDatasetOverview() {
  const format = document.getElementById('overviewExportFormat').value;
  window.location.href = `/dataset-overview/download/${format}`;
}

/* ═══════════════════════════════════════════════════════════════
   NEW CHAT / RESET
════════════════════════════════════════════════════════════════ */
function hardResetToUploadScreen() {
  Object.values(state.chartMap).forEach(c => c && c.destroy && c.destroy());
  if (state.vizModal.chart) { state.vizModal.chart.destroy(); state.vizModal.chart = null; }

  state.chartMap = {};
  state.tableData = {};
  state.uploaded = false;
  state.dataset = { name: '', rows: 0, columns: [] };
  state.querying = false;
  state.lastSQL  = '';
  state.overview = null;
  state.vizModal = { msgId: null, chart: null };
  state.previewTruncated = false;
  state.previewRowCount = 0;

  messagesContainer.innerHTML = '';
  emptyState.style.display = 'block';
  if (datasetOverview) datasetOverview.style.display = 'none';
  inputBarWrap.classList.remove('visible');
  chatScreen.style.display = 'none';
  uploadScreen.style.display = 'flex';

  uploadZone.classList.remove('success', 'uploading', 'dragover');
  uploadIconEl.innerHTML = iconFolder();
  uploadTitleEl.textContent = 'Drag & drop your dataset here';
  uploadHintEl.textContent  = 'or click to browse';
  uploadError.style.display = 'none';
  fileInput.value = '';
  closeVizModal();
}

newChatBtn.addEventListener('click', () => {
  // Preserve theme (stored in localStorage + already applied to body)

  // Smooth transition
  document.body.classList.add('page-transition-out');

  // Clear any server-side session-backed state by navigating to the initial page.
  // Backend /initial-load page corresponds to showing the upload UI.
  setTimeout(() => {
    window.location.href = '/';
  }, 160);

  // Immediate in-memory reset to prevent flashes of old UI
  setTimeout(() => hardResetToUploadScreen(), 0);
});

/* ═══════════════════════════════════════════════════════════════
   SIDEBAR TOGGLE
   ════════════════════════════════════════════════════════════════ */
if (leftSidebarToggle) leftSidebarToggle.addEventListener('click', toggleLeftSidebar);
if (leftSidebarClose) leftSidebarClose.addEventListener('click', toggleLeftSidebar);

function toggleLeftSidebar() {
  state.leftSidebarOpen = !state.leftSidebarOpen;
  leftSidebar.classList.toggle('hidden', !state.leftSidebarOpen);
}

/* ═══════════════════════════════════════════════════════════════
   SIDEBAR NAVIGATION
════════════════════════════════════════════════════════════════ */
// Sidebar navigation items - close on mobile overlay
if (leftSidebar) {
  leftSidebar.addEventListener('click', (e) => {
    const btn = e.target.closest('.sidebar-nav-item');
    if (!btn) return;
    if (window.innerWidth <= 1100) toggleLeftSidebar();
  });
}

// Legacy suggestion grid
const suggestionGrid = document.getElementById('suggestionGrid');
if (suggestionGrid) {
  suggestionGrid.addEventListener('click', (e) => {
    const btn = e.target.closest('.suggestion-btn');
    if (!btn) return;
    const q = btn.dataset.q;
    if (q) sendMessage(q);
  });
}

/* ═══════════════════════════════════════════════════════════════
   INPUT BAR
════════════════════════════════════════════════════════════════ */
chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 140) + 'px';
  sendBtn.disabled = chatInput.value.trim() === '';
});

chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!sendBtn.disabled && !state.querying) sendMessage(chatInput.value.trim());
  }
});

sendBtn.addEventListener('click', () => {
  if (!state.querying) sendMessage(chatInput.value.trim());
});

// Theme toggle
const themeToggle = document.getElementById('themeToggle');
const themeToggleUpload = document.getElementById('themeToggleUpload');
function toggleTheme(){
  const body = document.body;
  const curr = body.getAttribute('data-theme') || 'light';
  const next = curr === 'dark' ? 'light' : 'dark';
  body.setAttribute('data-theme', next);
  try { localStorage.setItem('theme', next); } catch {}
}

if (themeToggle) themeToggle.addEventListener('click', toggleTheme);
if (themeToggleUpload) themeToggleUpload.addEventListener('click', toggleTheme);

try {
  const saved = localStorage.getItem('theme');
  if (saved === 'dark' || saved === 'light') document.body.setAttribute('data-theme', saved);
} catch {}


/* ═══════════════════════════════════════════════════════════════
   SEND MESSAGE
════════════════════════════════════════════════════════════════ */
async function sendMessage(text) {
  if (!text || state.querying || !state.uploaded) return;

  // Hide empty state and overview on first question
  closeDatasetOverview();
  emptyState.style.display = 'none';

  appendUserMsg(text);

  chatInput.value = '';
  chatInput.style.height = 'auto';
  sendBtn.disabled = true;
  state.querying = true;

  const loadingId = appendLoadingMsg();

  try {
    const res  = await fetch('/query', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ question: text }),
    });
    const data = await res.json();

    removeMsg(loadingId);

    if (!res.ok) {
      appendErrorMsg(data.error || 'Query failed. Please try again.');
      return;
    }

    if (data.type === 'delete_confirm') {
      appendConfirmMsg(data.message);
      return;
    }

    if (data.type === 'irrelevant') {
      appendIrrelevantMsg(data.message, data.suggestions || []);
      return;
    }

    appendAIMsg(data, text);

  } catch (err) {
    removeMsg(loadingId);
    appendErrorMsg('Could not reach the server. Please check your connection.');
    console.error(err);
  } finally {
    state.querying = false;
    sendBtn.disabled = chatInput.value.trim() === '';
    scrollToBottom();
  }
}

/* ═══════════════════════════════════════════════════════════════
   MESSAGE RENDERERS
════════════════════════════════════════════════════════════════ */
function appendUserMsg(text) {
  const row = document.createElement('div');
  row.className = 'msg-row msg-user';
  row.innerHTML = `<div class="msg-user-bubble">${escHtml(text)}</div>`;
  messagesContainer.appendChild(row);
  scrollToBottom();
}

function appendLoadingMsg() {
  const id = 'load-' + Date.now();
  const row = document.createElement('div');
  row.className = 'msg-row msg-ai msg-loading';
  row.id = id;
  row.innerHTML = `
    <div class="msg-ai-wrap">
      <div class="msg-ai-avatar" aria-hidden="true">${iconBot()}</div>
      <div class="msg-ai-card">
        <div class="loading-dots">
          <span></span><span></span><span></span>
        </div>
        <span class="loading-text">Analyzing your dataset…</span>
      </div>
    </div>`;
  messagesContainer.appendChild(row);
  scrollToBottom();
  return id;
}

function appendErrorMsg(errText) {
  const row = document.createElement('div');
  row.className = 'msg-row msg-ai';
  row.innerHTML = `
    <div class="msg-ai-wrap">
      <div class="msg-ai-avatar" aria-hidden="true">${iconBot()}</div>
      <div class="msg-ai-card">
        <div class="ai-error">${iconX()} ${escHtml(errText)}</div>
      </div>
    </div>`;
  messagesContainer.appendChild(row);
}

function appendConfirmMsg(msg) {
  const row = document.createElement('div');
  row.className = 'msg-row msg-ai';
  row.innerHTML = `
    <div class="msg-ai-wrap">
      <div class="msg-ai-avatar" aria-hidden="true">${iconWarn()}</div>
      <div class="msg-ai-card">
        <div class="confirm-warning">${parseMarkdown(msg)}</div>
      </div>
    </div>`;
  messagesContainer.appendChild(row);
}

function appendIrrelevantMsg(reason, suggestions) {
  const row = document.createElement('div');
  row.className = 'msg-row msg-ai';

  const chipsHtml = suggestions.length
    ? `<div class="irrelevant-suggestions">
        <div class="irrelevant-suggestions-label">Try asking:</div>
        <div class="irrelevant-chips">
          ${suggestions.map(s =>
            `<button class="irrelevant-chip" onclick="sendMessage(${JSON.stringify(s)})">${escHtml(s)}</button>`
          ).join('')}
        </div>
      </div>`
    : '';

  row.innerHTML = `
    <div class="msg-ai-wrap">
      <div class="msg-ai-avatar" aria-hidden="true">${iconNo()}</div>
      <div class="msg-ai-card">
        <div class="irrelevant-card">
          <div class="irrelevant-header">
            <span class="irrelevant-badge">Dataset Relevance Check</span>
          </div>
          <p class="irrelevant-body">This question doesn't appear to be related to the uploaded dataset.</p>
          <p class="irrelevant-hint">I can only answer questions using data available in the current dataset.</p>
          ${chipsHtml}
        </div>
      </div>
    </div>`;
  messagesContainer.appendChild(row);
  scrollToBottom();
}

function removeMsg(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

/* ═══════════════════════════════════════════════════════════════
   MAIN AI MESSAGE RENDERER
════════════════════════════════════════════════════════════════ */
function appendAIMsg(data, question) {
  const msgId = 'msg-' + Date.now();
  const row = document.createElement('div');
  row.className = 'msg-row msg-ai';
  row.id = msgId;

  let inner = '';

  // ── Text / markdown ──
  if (data.message && data.type !== 'visualization') {
    inner += `<div class="ai-summary">${parseMarkdown(data.message)}</div>`;
  }

  // ── Visualization response ──
  if (data.type === 'visualization' && data.visualization) {
    const viz = data.visualization;

    // Chart canvas
    inner += `
      <div class="msg-chart-wrap" id="chart-container-${msgId}">
        <canvas id="chart-${msgId}"></canvas>
      </div>`;

    // Chart type switcher
    const allTypes = viz.all_types || [viz.chart_type];
    if (allTypes.length > 1) {
      inner += `
        <div class="viz-switcher" id="switcher-${msgId}">
          <span class="viz-picker-label">Switch chart:</span>
          ${allTypes.map(t => `
            <button class="viz-type-btn${t === viz.chart_type ? ' active' : ''}"
              onclick="switchVizType('${msgId}', '${t}', this)">${_chartLabel(t)}</button>
          `).join('')}
        </div>`;
    }

    // Data table below chart
    if (data.columns && data.rows && data.rows.length > 0) {
      const tableId = msgId + '-t';
      inner += `<div class="ai-divider"></div>` + buildTableBlock(tableId, data.columns, data.rows, data.total || data.rows.length, question, false);
      state.tableData[tableId] = { columns: data.columns, allRows: data.rows, page: 0, sql: '' };
    }
  }

  // ── Table result (query / schema / edit) ──
  if (data.type !== 'visualization' && data.columns && data.rows && data.rows.length > 0) {
    if (inner) inner += `<div class="ai-divider"></div>`;
    inner += buildTableBlock(msgId, data.columns, data.rows, data.total || data.rows.length, question, data.type === 'query');
  }

  // ── Edit success ──
  if (data.type === 'edit' && data.message) {
    inner = `<div class="ai-summary">${parseMarkdown(data.message)}</div>` + inner;
  }

  row.innerHTML = `
    <div class="msg-ai-wrap">
      <div class="msg-ai-avatar" aria-hidden="true">${iconBot()}</div>
      <div class="msg-ai-card">${inner || '<div class="ai-summary">Done</div>'}</div>
    </div>`;

  messagesContainer.appendChild(row);

  // Register table data for pagination
  if (data.type !== 'visualization' && data.columns && data.rows) {
    state.tableData[msgId] = { columns: data.columns, allRows: data.rows, page: 0, sql: state.lastSQL };
  }

  // Render visualization chart
  if (data.type === 'visualization' && data.visualization) {
    requestAnimationFrame(() => {
      const container = document.getElementById(`chart-container-${msgId}`);
      if (container) {
        container.dataset.allTypes = JSON.stringify(data.visualization.all_types || []);
        if (data.visualization.x_column) container.dataset.xCol = data.visualization.x_column;
        if (data.visualization.y_column) container.dataset.yCol = data.visualization.y_column;
      }
      renderChartInMsg(msgId, data.visualization.spec, 'chart-' + msgId);
    });
  }
}

/* ═══════════════════════════════════════════════════════════════
   TABLE BUILDER
════════════════════════════════════════════════════════════════ */
function buildTableBlock(msgId, columns, rows, total, question, showToolbar) {
  const pageRows  = rows.slice(0, PAGE_SIZE);
  const totalPages = Math.ceil(rows.length / PAGE_SIZE);
  const showing   = Math.min(PAGE_SIZE, rows.length);

  const statsBar = `
    <div class="result-stats">
      <span class="result-count">
        ${showing < total
          ? `Showing ${showing} of ${total.toLocaleString()} rows`
          : `${total.toLocaleString()} row${total !== 1 ? 's' : ''}`}
      </span>
    </div>`;

  const tableHtml = `
    <div class="result-table-wrap">
      <table class="result-table" id="table-${msgId}">
        <thead><tr>${columns.map(c => `<th>${escHtml(c)}</th>`).join('')}</tr></thead>
        <tbody>${buildTableRows(columns, pageRows)}</tbody>
      </table>
      ${totalPages > 1 ? `
        <div class="table-pagination">
          <span id="page-info-${msgId}">Page 1 of ${totalPages}</span>
          <div class="pagination-btns">
            <button class="page-btn" id="prev-${msgId}" disabled onclick="changePage('${msgId}',-1)">← Prev</button>
            <button class="page-btn" id="next-${msgId}" ${totalPages <= 1 ? 'disabled' : ''} onclick="changePage('${msgId}',1)">Next →</button>
          </div>
        </div>` : ''}
    </div>`;

  // Action toolbar — Visualize (query only) + Export
  let toolbarHtml = '';
  if (rows.length >= 1) {
    toolbarHtml = `
      <div class="action-toolbar">
        ${showToolbar ? `<button class="toolbar-btn toolbar-btn-primary" onclick="openVizModal('${msgId}')">Visualize</button><div class="toolbar-sep"></div>` : ''}
        <div class="dl-wrap">
          <button class="toolbar-btn" onclick="toggleDlMenu('${msgId}')"><i class="ti ti-download"></i> Export ▾</button>
          <div class="dl-menu" id="dlmenu-${msgId}">
            <button class="dl-opt" onclick="dlFmt('xlsx')">Excel (.xlsx)</button>
            <button class="dl-opt" onclick="dlFmt('pdf')">PDF (.pdf)</button>
            <button class="dl-opt" onclick="dlFmt('docx')">Word (.docx)</button>
            <button class="dl-opt" onclick="dlFmt('png')">Image (.png)</button>
          </div>
        </div>
      </div>`;
  }

  return statsBar + tableHtml + toolbarHtml;
}

function smartRecommend(numCols, catCols, dateCols, question) {
  const q = (question || '').toLowerCase();
  const recs = [];

  if (dateCols.length >= 1 && numCols.length >= 1) {
    recs.push({ type: 'line',      icon: '', label: 'Line Chart' });
    recs.push({ type: 'area',      icon: '', label: 'Area Chart' });
  } else if (catCols.length >= 1 && numCols.length >= 1) {
    const uniqueVals = catCols.length; // approximate
    if (/pie|proportion|share|percent|distribution/i.test(q) || catCols.length === 1) {
      recs.push({ type: 'pie',   icon: '', label: 'Pie Chart' });
      recs.push({ type: 'donut', icon: '', label: 'Donut Chart' });
      recs.push({ type: 'bar',   icon: '', label: 'Bar Chart' });
    } else {
      recs.push({ type: 'bar',   icon: '', label: 'Bar Chart' });
      recs.push({ type: 'pie',   icon: '', label: 'Pie Chart' });
      recs.push({ type: 'donut', icon: '', label: 'Donut Chart' });
    }
  } else if (numCols.length >= 2) {
    recs.push({ type: 'scatter',   icon: '', label: 'Scatter Plot' });
    recs.push({ type: 'histogram', icon: '', label: 'Histogram' });
  } else if (numCols.length >= 1) {
    recs.push({ type: 'histogram', icon: '', label: 'Histogram' });
    recs.push({ type: 'bar',       icon: '', label: 'Bar Chart' });
  }

    // Icons are now rendered as SVG badges elsewhere; keep labels text-only.
  return recs.slice(0, 4).map(r => ({...r, icon: ''}));
}

function classifyColumns(columns, rows) {
  // Prefer master schema if available (single source of truth)
  if (Object.keys(state.masterSchema).length > 0) {
    return classifyColumnsFromSchema(columns);
  }
  
  // Fallback: old heuristic-based classification (for backward compatibility)
  const sample = rows.slice(0, 20);
  const numericHint = /id|num|count|qty|amount|price|sales|revenue|age|score|gpa|salary|total|rate|value|profit|cost|quantity|percent|ratio|avg|sum|mean/;
  const dateHint    = /date|time|year|month|day|period|created|updated/;

  const numCols  = columns.filter(c => {
    if (numericHint.test(c.toLowerCase())) return true;
    const vals = sample.map(r => r[c]).filter(v => v !== null && v !== '');
    return vals.length > 0 && vals.every(v => !isNaN(Number(v)));
  });
  const dateCols = columns.filter(c => dateHint.test(c.toLowerCase()));
  const catCols  = columns.filter(c => !numCols.includes(c) && !dateCols.includes(c));

  return { numCols, catCols, dateCols };
}

/**
 * Classify columns using the master schema (single source of truth).
 * Returns { numCols, catCols, dateCols } based on schema types.
 */
function classifyColumnsFromSchema(columns) {
  const numCols  = [];
  const dateCols = [];
  const catCols  = [];
  
  columns.forEach(c => {
    const dtype = state.masterSchema[c];
    if (dtype === 'NUM') {
      numCols.push(c);
    } else if (dtype === 'DATE') {
      dateCols.push(c);
    } else {
      catCols.push(c);
    }
  });
  
  return { numCols, catCols, dateCols };
}

/* ═══════════════════════════════════════════════════════════════
   INLINE CHART (from rec chips — renders directly below table)
════════════════════════════════════════════════════════════════ */
function renderInlineChart(msgId, chartType, btnEl) {
  const td = state.tableData[msgId];
  if (!td) return;

  // Toggle: clicking same button again hides chart
  const container = document.getElementById(`inline-chart-${msgId}`);
  if (!container) return;

  const allBtns = btnEl.closest('.chart-rec-strip').querySelectorAll('.chart-rec-chip');
  const wasActive = btnEl.classList.contains('active-chart');
  allBtns.forEach(b => b.classList.remove('active-chart'));

  if (wasActive) {
    container.innerHTML = '';
    if (state.chartMap[msgId + '-inline']) {
      state.chartMap[msgId + '-inline'].destroy();
      delete state.chartMap[msgId + '-inline'];
    }
    return;
  }

  btnEl.classList.add('active-chart');

  const { numCols, catCols, dateCols } = classifyColumns(td.columns, td.allRows);
  const spec  = buildSpecFromData(chartType, td.columns, td.allRows, numCols, catCols);
  const cid   = `inline-canvas-${msgId}`;
  const allTypes = ['bar','line','area','pie','donut','scatter','histogram'];

  // Build type switcher only for relevant types
  const { recs: swRecs } = { recs: smartRecommend(numCols, catCols, dateCols, '').slice(0, 5) };
  const switcherBtns = smartRecommend(numCols, catCols, dateCols, '').slice(0, 5).map(r =>
      `<button class="inline-ct-btn${r.type === chartType ? ' active' : ''}"
      onclick="switchInlineChart('${msgId}', '${r.type}', this)">${_chartIconSvg(r.type)} ${r.label}</button>`
  ).join('');

  container.innerHTML = `
    <div class="inline-chart-panel">
      <div class="inline-chart-header">
        <div class="inline-chart-title">
          <span>${escHtml(spec.title || chartType + ' Chart')}</span>
        </div>
        <div class="inline-chart-type-strip">${switcherBtns}</div>
      </div>
      <div class="inline-chart-body">
        <canvas id="${cid}"></canvas>
      </div>
    </div>`;

  requestAnimationFrame(() => {
    if (state.chartMap[msgId + '-inline']) {
      state.chartMap[msgId + '-inline'].destroy();
    }
    state.chartMap[msgId + '-inline'] = renderChart(cid, spec);
  });
}

function switchInlineChart(msgId, newType, btnEl) {
  const td = state.tableData[msgId];
  if (!td) return;

  btnEl.closest('.inline-chart-type-strip')
    .querySelectorAll('.inline-ct-btn').forEach(b => b.classList.remove('active'));
  btnEl.classList.add('active');

  const { numCols, catCols } = classifyColumns(td.columns, td.allRows);
  const spec  = buildSpecFromData(newType, td.columns, td.allRows, numCols, catCols);
  const panel = btnEl.closest('.inline-chart-panel');
  const title = panel.querySelector('.inline-chart-title span');
  if (title) title.textContent = spec.title || newType + ' Chart';

  const cid = `inline-canvas-${msgId}`;
  if (state.chartMap[msgId + '-inline']) {
    state.chartMap[msgId + '-inline'].destroy();
  }
  state.chartMap[msgId + '-inline'] = renderChart(cid, spec);
}

/* ═══════════════════════════════════════════════════════════════
   VIZ MODAL (Power BI–style panel)
════════════════════════════════════════════════════════════════ */
function openVizModal(msgId) {
  const td = state.tableData[msgId];
  if (!td) return;

  // Handle empty rows (e.g. initial master state)
  if (td.allRows.length === 0 && msgId === 'master') {
    sendMessage('Show top 10 rows');
    showToast('Loading a data sample for visualization...', 'info');
    return;
  }

  state.vizModal.msgId = msgId;

  // Populate axis dropdowns
  vizXAxis.innerHTML = td.columns.map(c => `<option value="${escHtml(c)}">${escHtml(c)}</option>`).join('');
  vizYAxis.innerHTML = td.columns.map(c => `<option value="${escHtml(c)}">${escHtml(c)}</option>`).join('');

  // Pre-select sensible defaults based on column classification
  const { numCols, catCols, dateCols } = classifyColumns(td.columns, td.allRows);
  if (catCols.length >= 1)  vizXAxis.value = catCols[0];
  else if (dateCols.length) vizXAxis.value = dateCols[0];
  if (numCols.length >= 1)  vizYAxis.value = numCols[0];
  else if (td.columns.length >= 2) vizYAxis.value = td.columns[1];

  // AI recommendation
  const recs = smartRecommend(numCols, catCols, dateCols, '');
  if (recs.length) {
    vizAIRecText.textContent = `Best chart for this data: ${recs[0].icon} ${recs[0].label}`;
    vizAIRec.style.display = 'flex';
    // Pre-select best chart type
    vizChartTypeGrid.querySelectorAll('.viz-chart-type-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.type === recs[0].type);
    });

    // Suggestion chips
    vizRecChips.style.display = 'flex';
    const existing = vizRecChips.querySelectorAll('.viz-rec-chip-btn');
    existing.forEach(e => e.remove());
    recs.forEach((r, i) => {
      const btn = document.createElement('button');
      btn.className = 'viz-rec-chip-btn' + (i === 0 ? ' active' : '');
      btn.textContent = `${r.icon} ${r.label}`;
      btn.addEventListener('click', () => {
        vizChartTypeGrid.querySelectorAll('.viz-chart-type-btn').forEach(b => {
          b.classList.toggle('active', b.dataset.type === r.type);
        });
        vizRecChips.querySelectorAll('.viz-rec-chip-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      });
      vizRecChips.appendChild(btn);
    });
  } else {
    vizAIRec.style.display = 'none';
    vizRecChips.style.display = 'none';
  }

  // Reset preview
  vizPreviewEmpty.style.display = 'flex';
  vizPreviewChart.style.display = 'none';
  if (state.vizModal.chart) { state.vizModal.chart.destroy(); state.vizModal.chart = null; }

  vizModal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function closeVizModal() {
  vizModal.style.display = 'none';
  document.body.style.overflow = '';
  if (state.vizModal.chart) { state.vizModal.chart.destroy(); state.vizModal.chart = null; }
}

vizModalClose.addEventListener('click', closeVizModal);
vizModal.addEventListener('click', (e) => {
  if (e.target === vizModal) closeVizModal();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && vizModal.style.display !== 'none') closeVizModal();
});

// Chart type grid selection
vizChartTypeGrid.addEventListener('click', (e) => {
  const btn = e.target.closest('.viz-chart-type-btn');
  if (!btn) return;
  vizChartTypeGrid.querySelectorAll('.viz-chart-type-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
});

// Aggregation selection
vizAggRow.addEventListener('click', (e) => {
  const btn = e.target.closest('.viz-agg-btn');
  if (!btn) return;
  vizAggRow.querySelectorAll('.viz-agg-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
});

// Generate chart
vizGenerateBtn.addEventListener('click', () => {
  const msgId = state.vizModal.msgId;
  if (!msgId) return;
  const td = state.tableData[msgId];
  if (!td) return;

  const chartType = vizChartTypeGrid.querySelector('.viz-chart-type-btn.active')?.dataset.type || 'bar';
  const xCol      = vizXAxis.value;
  const yCol      = vizYAxis.value;
  const agg       = vizAggRow.querySelector('.viz-agg-btn.active')?.dataset.agg || 'sum';

  const spec = buildSpecFromDataWithAxes(chartType, td.columns, td.allRows, xCol, yCol, agg);

  if (state.vizModal.chart) { state.vizModal.chart.destroy(); state.vizModal.chart = null; }

  vizPreviewEmpty.style.display = 'none';
  vizPreviewChart.style.display = 'flex';

  requestAnimationFrame(() => {
    state.vizModal.chart = renderChart('vizModalCanvas', spec);
  });
});

/* ═══════════════════════════════════════════════════════════════
   SPEC BUILDERS (Enhanced)
════════════════════════════════════════════════════════════════ */

/**
 * Fetch a chart spec from the backend custom-render endpoint.
 * This ensures the backend pipeline (Aggregate → Sort → Top-N → Render) is used.
 */
async function fetchCustomChartSpec(chartType, xCol, yCol, agg, sortOrder, topN) {
  try {
    const res = await fetch('/visualize/custom-render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chart_type: chartType,
        xColumn: xCol,
        yColumn: yCol,
        aggregation: agg,
        sortOrder: sortOrder,
        topN: topN,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      console.error('Custom render failed:', data.error);
      return null;
    }
    return data;
  } catch (err) {
    console.error('Custom render error:', err);
    return null;
  }
}

/**
 * Build a chart spec locally (fallback when backend is unavailable).
 * This is a client-side implementation of the same pipeline:
 * Aggregate → Sort → Top-N → Render
 */
function buildSpecFromDataWithAxes(chartType, columns, rows, xCol, yCol, agg, sortOrder, topN) {
  // Use defaults
  sortOrder = sortOrder || 'desc';
  topN = topN || 20;

  // Compute aggregation from rows
  const MAX_DATA = 10000;
  const working = rows.slice(0, MAX_DATA);

  if (chartType === 'scatter' && xCol && yCol) {
    const limited = working.slice(0, 500);
    return {
      plotType: 'scatter',
      title: `${yCol} vs ${xCol}`,
      xLabel: xCol, yLabel: yCol,
      series: [{ label: 'Data', data: limited.map(r => ({ x: Number(r[xCol]), y: Number(r[yCol]) })) }]
    };
  }

  if (chartType === 'histogram') {
    const col  = yCol || xCol;
    const vals = rows.map(r => Number(r[col])).filter(v => !isNaN(v));
    return buildHistogramSpec(col, vals);
  }

  // Aggregate
  const aggMap = {};
  working.forEach(r => {
    const k = String(r[xCol] ?? '(blank)');
    const v = Number(r[yCol]) || 0;
    if (!aggMap[k]) aggMap[k] = { sum: 0, count: 0, min: Infinity, max: -Infinity, vals: [] };
    aggMap[k].sum   += v;
    aggMap[k].count += 1;
    aggMap[k].min    = Math.min(aggMap[k].min, v);
    aggMap[k].max    = Math.max(aggMap[k].max, v);
    if (v) aggMap[k].vals.push(v);
  });

  const getValue = (entry) => {
    switch (agg) {
      case 'avg':   return entry.count ? entry.sum / entry.count : 0;
      case 'count': return entry.count;
      case 'max':   return entry.max;
      case 'min':   return entry.min;
      case 'median': {
        const sorted = [...entry.vals].sort((a, b) => a - b);
        const mid = Math.floor(sorted.length / 2);
        return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
      }
      default:      return entry.sum;
    }
  };

  // ISSUE 3: Sort descending first, then reverse if asc
  let sorted = Object.entries(aggMap).sort((a, b) => getValue(b[1]) - getValue(a[1]));
  if (sortOrder === 'asc') {
    sorted.reverse();
  }

  // Apply Top-N
  sorted = sorted.slice(0, topN);

  // Truncate long labels
  const labels = sorted.map(e => String(e[0]));
  const data   = sorted.map(e => +getValue(e[1]).toFixed(2));

  return {
    plotType: chartType,
    title: `${agg.toUpperCase()}(${yCol || 'Count'}) by ${xCol}`,
    xLabel: xCol,
    yLabel: yCol || 'Count',
    labels,
    series: [{ label: yCol || 'Count', data, labels }],
    _totalCategories: sorted.length,
  };
}

function buildSpecFromData(chartType, columns, rows, numCols, catCols) {
  const MAX_DATA = 10000;
  const working = rows.slice(0, MAX_DATA);

  if (chartType === 'scatter' && numCols.length >= 2) {
    const xc = numCols[0], yc = numCols[1];
    const limited = working.slice(0, 500);
    return {
      plotType: 'scatter',
      title: `${yc} vs ${xc}`,
      xLabel: xc, yLabel: yc,
      series: [{ label: 'Data', data: limited.map(r => ({ x: Number(r[xc]), y: Number(r[yc]) })) }]
    };
  }

  if (chartType === 'histogram' && numCols.length >= 1) {
    const col  = numCols[0];
    const vals = rows.map(r => Number(r[col])).filter(v => !isNaN(v));
    return buildHistogramSpec(col, vals);
  }

  const xCol = catCols[0] || columns[0];
  const yCol = numCols[0] || columns[1] || columns[0];

  // Aggregate: sum by default
  const agg = {};
  working.forEach(r => {
    const k = String(r[xCol] ?? '(blank)');
    const v = Number(r[yCol]) || 0;
    agg[k] = (agg[k] || 0) + v;
  });

  // Sort descending and take top 20
  const sorted = Object.entries(agg).sort((a, b) => b[1] - a[1]).slice(0, 20);
  const labels = sorted.map(e => String(e[0]));
  const data = sorted.map(e => e[1]);

  return {
    plotType: chartType,
    title: `${yCol} by ${xCol}`,
    xLabel: xCol, yLabel: yCol,
    labels,
    series: [{ label: yCol, data, labels }]
  };
}

function buildHistogramSpec(col, vals) {
  const cleanVals = vals.filter(v => !isNaN(v) && isFinite(v));
  if (cleanVals.length === 0) {
    return {
      plotType: 'bar', title: `Distribution of ${col}`,
      xLabel: col, yLabel: 'Count',
      series: [{ label: 'Frequency', data: [], labels: [] }]
    };
  }
  const min  = Math.min(...cleanVals), max = Math.max(...cleanVals);
  const bins = Math.min(15, Math.ceil(Math.sqrt(cleanVals.length)));
  const binSize = (max - min) / bins || 1;
  const counts  = Array(bins).fill(0);
  const labels  = [];
  for (let i = 0; i < bins; i++) {
    const lo = min + i * binSize;
    const hi = min + (i + 1) * binSize;
    labels.push(`${lo.toFixed(1)}–${hi.toFixed(1)}`);
  }
  cleanVals.forEach(v => {
    const idx = Math.min(Math.floor((v - min) / binSize), bins - 1);
    if (idx >= 0) counts[idx]++;
  });
  return {
    plotType: 'bar', title: `Distribution of ${col}`,
    xLabel: col, yLabel: 'Count',
    series: [{ label: 'Frequency', data: counts, labels }]
  };
}

/* ═══════════════════════════════════════════════════════════════
   PAGINATION
════════════════════════════════════════════════════════════════ */
function changePage(msgId, delta) {
  const td = state.tableData[msgId];
  if (!td) return;

  const totalPages = Math.ceil(td.allRows.length / PAGE_SIZE);
  const newPage    = td.page + delta;
  if (newPage < 0 || newPage >= totalPages) return;

  td.page = newPage;
  const pageRows = td.allRows.slice(newPage * PAGE_SIZE, (newPage + 1) * PAGE_SIZE);

  const tbody = document.querySelector(`#table-${msgId} tbody`);
  if (tbody) tbody.innerHTML = buildTableRows(td.columns, pageRows);

  const info = document.getElementById(`page-info-${msgId}`);
  if (info) info.textContent = `Page ${newPage + 1} of ${totalPages}`;

  const prevBtn = document.getElementById(`prev-${msgId}`);
  const nextBtn = document.getElementById(`next-${msgId}`);
  if (prevBtn) prevBtn.disabled = newPage === 0;
  if (nextBtn) nextBtn.disabled = newPage >= totalPages - 1;
}

function buildTableRows(columns, rows) {
  return rows.map(row =>
    `<tr>${columns.map(c => `<td title="${escHtml(String(row[c] ?? ''))}">${escHtml(String(row[c] ?? ''))}</td>`).join('')}</tr>`
  ).join('');
}

/* ═══════════════════════════════════════════════════════════════
   DOWNLOAD / EXPORT
════════════════════════════════════════════════════════════════ */
function toggleDlMenu(msgId) {
  document.querySelectorAll('.dl-menu').forEach(m => {
    if (m.id !== `dlmenu-${msgId}`) m.classList.remove('open');
  });
  const menu = document.getElementById(`dlmenu-${msgId}`);
  if (menu) menu.classList.toggle('open');
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.dl-wrap')) {
    document.querySelectorAll('.dl-menu').forEach(m => m.classList.remove('open'));
  }
});

function dlFmt(fmt) {
  window.location.href = `/download/${fmt}`;
  document.querySelectorAll('.dl-menu').forEach(m => m.classList.remove('open'));
}

/* ═══════════════════════════════════════════════════════════════
   SWITCH CHART TYPE (visualization response)
════════════════════════════════════════════════════════════════ */
async function switchVizType(msgId, newType, btnEl) {
  const switcher = document.getElementById(`switcher-${msgId}`);
  if (switcher) {
    switcher.querySelectorAll('.viz-type-btn').forEach(b => b.classList.remove('active'));
    btnEl.classList.add('active');
  }

  const container = document.getElementById(`chart-container-${msgId}`);
  const xCol = container ? container.dataset.xCol : undefined;
  const yCol = container ? container.dataset.yCol : undefined;

  try {
    const body = { type: newType };
    if (xCol) body.xColumn = xCol;
    if (yCol) body.yColumn = yCol;

    const res  = await fetch('/visualize/render', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      console.error(data.error);
      showToast(data.error || 'Could not switch chart type. Please try again.', 'error');
      return;
    }
    renderChartInMsg(msgId, data.spec, 'chart-' + msgId);
  } catch (err) {
    console.error('switchVizType error:', err);
    showToast('Could not switch chart type. Please check your connection.', 'error');
  }
}

/* ═══════════════════════════════════════════════════════════════
   CHART.JS RENDERERS — PROFESSIONAL BI-STYLE
   ISSUE 1, 7: Comprehensive fix for labels, tooltips, legends
════════════════════════════════════════════════════════════════ */
// Register the Chart.js datalabels plugin globally for bar chart value labels
Chart.register(ChartDataLabels);
// Configure defaults for datalabels on bar charts
Chart.defaults.set('plugins.datalabels', {
  display: false, // disable globally, enable per-chart
});

const CHART_COLORS = [
  '#2563EB','#3B82F6','#60A5FA','#F59E0B','#EF4444',
  '#8B5CF6','#EC4899','#14B8A6','#F97316','#6366F1',
  '#0EA5E9','#D946EF','#84CC16','#F43F5E','#06B6D4',
];

/** Get theme-aware text/muted colors */
function getThemeColors() {
  const isDark = document.body.getAttribute('data-theme') === 'dark';
  return {
    text:      isDark ? '#F1F5F9' : '#1E293B',
    textMid:   isDark ? '#CBD5E1' : '#475569',
    textMuted: isDark ? '#94A3B8' : '#64748B',
    grid:      isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)',
    bg:        isDark ? '#0F172A' : '#FFFFFF',
    cardBg:    'transparent',
  };
}

function renderChartInMsg(msgId, spec, canvasId) {
  if (!spec) return;
  const existing = state.chartMap[msgId];
  if (existing) { existing.destroy(); delete state.chartMap[msgId]; }
  const chart = renderChart(canvasId, spec);
  if (chart) state.chartMap[msgId] = chart;
}

function renderChart(canvasId, spec, opts = {}) {
  if (!spec) return null;
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;

  const compact = !!opts.compact;
  const colors = getThemeColors();
  const plotType   = (spec.plotType || '').toLowerCase();
  let chartJsType  = 'bar';
  if (plotType === 'line' || plotType === 'area') chartJsType = 'line';
  else if (plotType === 'scatter') chartJsType = 'scatter';
  else if (plotType === 'pie')     chartJsType = 'pie';
  else if (plotType === 'donut')   chartJsType = 'doughnut';

  const series  = spec.series && spec.series[0] ? spec.series[0] : null;
  const labels  = series?.labels || spec.labels || [];
  const values  = series?.data   || [];
  const isPie  = chartJsType === 'pie' || chartJsType === 'doughnut';
  const isArea = plotType === 'area';
  const pieLegendPadding = labels.length > 8 ? 24 : 14;

  // Build background colors for pie charts
  let bgColors = isPie ? CHART_COLORS.slice(0, values.length) : 'rgba(37,99,235,0.18)';
  let borderColors = isPie ? CHART_COLORS.slice(0, values.length).map(c => c + 'dd') : '#2563EB';
  
  // For bar charts, use gradient-like colors
  if (!isPie && chartJsType !== 'scatter') {
    // Single color with transparency
    bgColors = 'rgba(37,99,235,0.18)';
  }

  // Format large numbers
  const formatNum = (v) => {
    if (typeof v !== 'number') return String(v);
    if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
    if (Math.abs(v) >= 1_000) return (v / 1_000).toFixed(1) + 'K';
    return v.toLocaleString();
  };

  const dataset = {
    label:           series?.label || spec.yLabel || 'Data',
    data:            values,
    backgroundColor: bgColors,
    borderColor:     borderColors,
    borderWidth:     isPie ? 2 : 2,
    pointRadius:     chartJsType === 'scatter' ? 4 : (chartJsType === 'line' ? 3 : 2),
    pointHoverRadius: chartJsType === 'line' ? 5 : 4,
    fill:            isArea ? true : undefined,
    tension:         chartJsType === 'line' ? 0.3 : undefined,
    hoverBackgroundColor: isPie ? CHART_COLORS.slice(0, values.length).map(c => c + 'ff') : undefined,
    offset:          isPie ? labels.map((_, index) => (index % 2 === 0 ? 5 : 2)) : undefined,
  };

  const useLabels = !isPie && chartJsType !== 'scatter';
  
  // For pie charts with a handful of slices, annotate each slice directly —
  // with more slices the labels collide, so rely on the legend instead.
  const pieLabelsPlugin = (isPie && !compact && labels.length <= 8) ? {
    id: 'pieLabels',
    afterDraw(chart) {
      const { ctx, data } = chart;
      const total = data.datasets[0].data.reduce((a, b) => a + b, 0);
      if (total === 0) return;
      
      chart.getDatasetMeta(0).data.forEach((arc, i) => {
        const label = data.labels[i];
        const value = data.datasets[0].data[i];
        const pct = ((value / total) * 100).toFixed(1);
        const midAngle = arc.startAngle + (arc.endAngle - arc.startAngle) / 2;
        
        // Position label outside the arc
        const radius = arc.outerRadius * 1.35;
        const x = Math.cos(midAngle) * radius + arc.x;
        const y = Math.sin(midAngle) * radius + arc.y;
        
        ctx.save();
        ctx.translate(x, y);
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        
        // Truncate long labels
        const displayLabel = label.length > 14 ? label.substring(0, 12) + '…' : label;
        
        // Background for readability
        const textWidth = ctx.measureText(displayLabel).width;
        const pctWidth = ctx.measureText(`${pct}%`).width;
        const maxWidth = Math.max(textWidth, pctWidth) + 8;
        
        ctx.fillStyle = document.body.getAttribute('data-theme') === 'dark' ? 'rgba(15,23,42,0.90)' : 'rgba(255,255,255,0.92)';
        ctx.shadowColor = document.body.getAttribute('data-theme') === 'dark' ? 'rgba(0,0,0,0.5)' : 'rgba(0,0,0,0.1)';
        ctx.shadowBlur = 4;
        ctx.fillRect(-maxWidth/2 - 3, -18, maxWidth + 6, 36);
        ctx.shadowBlur = 0;
        
        ctx.font = 'bold 10px Inter, system-ui, sans-serif';
        ctx.fillStyle = colors.text;
        ctx.fillText(displayLabel, 0, -5);
        
        ctx.font = '10px Inter, system-ui, sans-serif';
        ctx.fillStyle = colors.textMuted;
        ctx.fillText(`${formatNum(value)} (${pct}%)`, 0, 10);
        
        ctx.restore();
      });
    }
  } : null;

  return new Chart(canvas.getContext('2d'), {
    type: chartJsType,
    data: {
      labels:   useLabels ? labels : (isPie ? labels : undefined),
      datasets: [dataset],
    },
    plugins: pieLabelsPlugin ? [pieLabelsPlugin] : [],
    options: {
      responsive: true,
      maintainAspectRatio: true,
      layout: (isPie && !compact) ? { padding: { top: 28, right: 40, bottom: 30, left: 40 } } : {},
      animation: { duration: compact ? 300 : 500 },
      ...(chartJsType === 'bar' ? {
        plugins: {
          ...(isPie ? {} : {
            datalabels: {
              display: values.length <= 20 && !compact,
              color: colors.text,
              anchor: 'end',
              align: 'end',
              font: { size: 9, weight: '600' },
              formatter: (v) => formatNum(v),
            }
          }),
          legend: {
            display: (isPie || chartJsType === 'doughnut') && !compact,
            position: 'bottom',
            labels: {
              boxWidth: 14,
              padding: pieLegendPadding,
              font: { size: 11, weight: '500' },
              color: colors.textMuted,
              usePointStyle: true,
            },
          },
          title: {
            display: !!spec.title && !compact,
            text:    spec.title || '',
            font:    { size: 14, weight: '700' },
            color:   colors.text,
            padding: { bottom: 14, top: 4 },
          },
          tooltip: {
            backgroundColor: document.body.getAttribute('data-theme') === 'dark' ? '#1E293B' : '#FFFFFF',
            titleColor: colors.text,
            bodyColor: colors.textMid,
            borderColor: document.body.getAttribute('data-theme') === 'dark' ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
            borderWidth: 1,
            padding: 12,
            cornerRadius: 8,
            boxPadding: 6,
            usePointStyle: true,
            callbacks: {
              title: function(items) {
                if (!items.length) return '';
                return items[0].label || '';
              },
              label: function(ctx) {
                const v = ctx.parsed?.y ?? ctx.parsed?.r ?? ctx.parsed;
                const label = ctx.dataset.label || '';
                const formatted = typeof v === 'number' ? formatNum(v) : v;
                
                // For pie charts, show percentage
                if (isPie && ctx.dataset.data) {
                  const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                  const pct = total > 0 ? ((v / total) * 100).toFixed(1) : 0;
                  return ` ${label}: ${formatted} (${pct}%)`;
                }
                
                return ` ${label}: ${formatted}`;
              },
            },
          },
        }
      } : {
        legend: {
          display: (isPie || chartJsType === 'doughnut') && !compact,
          position: 'bottom',
          labels: {
            boxWidth: 14,
            padding: pieLegendPadding,
            font: { size: 11, weight: '500' },
            color: colors.textMuted,
            usePointStyle: true,
          },
        },
        title: {
          display: !!spec.title && !compact,
          text:    spec.title || '',
          font:    { size: 14, weight: '700' },
          color:   colors.text,
          padding: { bottom: 14, top: 4 },
        },
        tooltip: {
          backgroundColor: document.body.getAttribute('data-theme') === 'dark' ? '#1E293B' : '#FFFFFF',
          titleColor: colors.text,
          bodyColor: colors.textMid,
          borderColor: document.body.getAttribute('data-theme') === 'dark' ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
          borderWidth: 1,
          padding: 12,
          cornerRadius: 8,
          boxPadding: 6,
          usePointStyle: true,
          callbacks: {
            title: function(items) {
              if (!items.length) return '';
              if (chartJsType === 'scatter') return '';
              return items[0].label || '';
            },
            label: function(ctx) {
              // Scatter points carry both an X and a Y value — show each on its own line.
              if (chartJsType === 'scatter') {
                const px = typeof ctx.parsed?.x === 'number' ? formatNum(ctx.parsed.x) : ctx.parsed?.x;
                const py = typeof ctx.parsed?.y === 'number' ? formatNum(ctx.parsed.y) : ctx.parsed?.y;
                return [` ${spec.xLabel || 'X'}: ${px}`, ` ${spec.yLabel || 'Y'}: ${py}`];
              }

              const v = ctx.parsed?.y ?? ctx.parsed?.r ?? ctx.parsed;
              const label = ctx.dataset.label || '';
              const formatted = typeof v === 'number' ? formatNum(v) : v;

              // For pie charts, show percentage
              if (isPie && ctx.dataset.data) {
                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                const pct = total > 0 ? ((v / total) * 100).toFixed(1) : 0;
                return ` ${label}: ${formatted} (${pct}%)`;
              }

              return ` ${label}: ${formatted}`;
            },
          },
        },
      }),
      scales: isPie ? {} : {
        x: {
          ticks: {
            maxRotation: compact ? 0 : 45,
            minRotation: 0,
            font: { size: compact ? 9 : 11, weight: '500' },
            color: colors.textMuted,
            maxTicksLimit: compact ? 6 : 25,
            autoSkip: true,
            autoSkipPadding: 8,
            callback: function(value, index) {
              const label = this.getLabelForValue(value);
              if (!label) return '';
              // Truncate long labels but show full on hover via tooltip
              const maxLen = compact ? 8 : 20;
              return label.length > maxLen ? label.substring(0, maxLen - 2) + '…' : label;
            },
          },
          grid: {
            color: colors.grid,
            drawBorder: false,
          },
          title: {
            display: !!spec.xLabel && !compact,
            text: spec.xLabel || '',
            font: { size: 12, weight: '600' },
            color: colors.textMuted,
          },
        },
        y: {
          // Plain line charts auto-scale to the data range so trends remain visible;
          // bar/area/scatter/histogram start at zero so magnitudes stay comparable.
          beginAtZero: chartJsType !== 'line' || isArea,
          ticks: {
            font: { size: compact ? 9 : 11, weight: '500' },
            color: colors.textMuted,
            callback: function(v) {
              return formatNum(v);
            },
            maxTicksLimit: compact ? 4 : 8,
          },
          grid: {
            color: colors.grid,
            drawBorder: false,
          },
          title: {
            display: !!spec.yLabel && !compact,
            text: spec.yLabel || '',
            font: { size: 12, weight: '600' },
            color: colors.textMuted,
          },
        },
      },
      elements: {
        bar: {
          borderRadius: 3,
          backgroundColor: 'rgba(37,99,235,0.75)',
          hoverBackgroundColor: '#2563EB',
        },
        line: {
          borderColor: '#2563EB',
          backgroundColor: 'rgba(37,99,235,0.08)',
        },
        point: {
          backgroundColor: '#2563EB',
          borderColor: '#FFFFFF',
          borderWidth: 1.5,
          hoverRadius: 6,
        },
      },
    },
  });
}

/* ═══════════════════════════════════════════════════════════════
   HELPERS
════════════════════════════════════════════════════════════════ */
function iconSpinner(){
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 2a10 10 0 1 0 10 10"/>
  </svg>`;
}

function iconCheck(){
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M20 6 9 17l-5-5"/>
  </svg>`;
}

function iconFolder(){
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M3 6h5l2 2h11v10H3z"/>
  </svg>`;
}

function iconBot(){
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="5" y="4" width="14" height="16" rx="2"/>
    <path d="M9 13h.01"/>
    <path d="M15 13h.01"/>
    <path d="M9 17c1.5 1.2 4.5 1.2 6 0"/>
  </svg>`;
}

function iconWarn(){
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M10.3 3.7 1.9 18a2 2 0 0 0 1.7 3h16.8a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0z"/>
    <path d="M12 9v4"/>
    <path d="M12 17h.01"/>
  </svg>`;
}

function iconX(){
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M18 6 6 18"/>
    <path d="M6 6l12 12"/>
  </svg>`;
}

function iconNo(){
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/>
    <path d="M15 9 9 15"/>
  </svg>`;
}

function iconInfo(){
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/>
    <path d="M12 16v-4"/>
    <path d="M12 8h.01"/>
  </svg>`;
}

/**
 * Shows a dismissible toast notification in the bottom-right corner.
 * type: 'info' | 'success' | 'error' | 'warning'
 * duration: ms before auto-dismiss, or 0 to require manual dismissal.
 */
function showToast(message, type = 'info', duration = 4500) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const icons = { success: iconCheck(), error: iconNo(), warning: iconWarn(), info: iconInfo() };

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || icons.info}</span>
    <span class="toast-message">${escHtml(message)}</span>
    <button class="toast-close" type="button" aria-label="Dismiss notification">${iconX()}</button>
  `;

  const dismiss = () => {
    if (!toast.isConnected) return;
    toast.classList.add('toast-exit');
    toast.addEventListener('animationend', () => toast.remove(), { once: true });
  };

  toast.querySelector('.toast-close').addEventListener('click', dismiss);
  container.appendChild(toast);

  if (duration > 0) {
    setTimeout(dismiss, duration);
  }
}

function _chartIconSvg(type){
  const map = {
    bar: 'M4 20V10h4v10H4z M10 20V4h4v16h-4z M16 20v-7h4v7h-4z',
    line: 'M4 19l6-6 4 4 6-10',
    area: 'M4 19V9l5 4 4-7 7 13',
    pie: 'M12 12V2a10 10 0 1 1-9 5h9z',
    donut: 'M12 2a10 10 0 1 0 9 5',
    scatter: 'M7 17l3-6 4 8 3-4',
    histogram: 'M4 20V10h4v10H4z M10 20V4h4v16h-4z M16 20v-6h4v6h-4z'
  };
  const d = map[type] || map.bar;
  return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg>`;
}

function _chartLabel(t) {
  const labels = { bar:'Bar', line:'Line', area:'Area', pie:'Pie',
                   donut:'Donut', scatter:'Scatter', histogram:'Histogram' };
  return labels[t] || t;
}

/** Which Custom Chart Builder controls apply to each chart type. */
const CHART_CONTROL_APPLICABILITY = {
  bar:       { aggregation: true,  sortOrder: true,  topN: true },
  pie:       { aggregation: true,  sortOrder: true,  topN: true },
  donut:     { aggregation: true,  sortOrder: true,  topN: true },
  line:      { aggregation: true,  sortOrder: false, topN: false },
  area:      { aggregation: true,  sortOrder: false, topN: false },
  scatter:   { aggregation: false, sortOrder: false, topN: false },
  histogram: { aggregation: false, sortOrder: false, topN: false },
};

/**
 * Enable/disable the Aggregation, Sort Order and Top N controls based on the
 * selected chart type, and explain why via an inline note — so the UI never
 * shows a control that silently has no effect on the generated chart.
 */
function updateCustomControlAvailability(chartType) {
  const rules = CHART_CONTROL_APPLICABILITY[chartType] || CHART_CONTROL_APPLICABILITY.bar;

  const aggRow = document.getElementById('customAggRow');
  const sortOrder = document.getElementById('customSortOrder');
  const topN = document.getElementById('customTopN');
  const note = document.getElementById('customControlsNote');

  if (aggRow) {
    aggRow.classList.toggle('is-disabled', !rules.aggregation);
    aggRow.querySelectorAll('.viz-agg-btn').forEach(b => { b.disabled = !rules.aggregation; });
  }
  if (sortOrder) sortOrder.disabled = !rules.sortOrder;
  if (topN) topN.disabled = !rules.topN;

  if (note) {
    const disabledNames = [];
    if (!rules.aggregation) disabledNames.push('Aggregation');
    if (!rules.sortOrder) disabledNames.push('Sort Order');
    if (!rules.topN) disabledNames.push('Top N');
    if (disabledNames.length) {
      note.textContent = `${disabledNames.join(', ')} ${disabledNames.length > 1 ? "don't" : "doesn't"} apply to ${_chartLabel(chartType)} charts — the full dataset is shown.`;
      note.style.display = 'block';
    } else {
      note.style.display = 'none';
    }
  }
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&')
    .replace(/</g, '<')
    .replace(/>/g, '>')
    .replace(/"/g, '"');
}

function scrollToBottom() {
  chatMain.scrollTo({ top: chatMain.scrollHeight, behavior: 'smooth' });
}

/* ═══════════════════════════════════════════════════════════════
   VISUALIZATION NAVIGATION — Sub-menu Toggle
════════════════════════════════════════════════════════════════ */
let _vizSubOpen = false;
function toggleVizSubMenu() {
  _vizSubOpen = !_vizSubOpen;
  const menu = document.getElementById('vizSubMenu');
  const arrow = document.getElementById('vizSubArrow');
  if (menu) menu.classList.toggle('open', _vizSubOpen);
  if (arrow) arrow.style.transform = _vizSubOpen ? 'rotate(180deg)' : 'rotate(0deg)';
}

/* ═══════════════════════════════════════════════════════════════
   AUTO VISUALIZATION PAGE
════════════════════════════════════════════════════════════════ */
let _autoVizData = null;       // cached recommendations
const _autoVizCharts = {};     // canvasId -> Chart instance map

function showAutoVisualization() {
  if (!state.uploaded) return;
  closeAllPages();
  const page = document.getElementById('autoVizPage');
  page.style.display = 'block';
  document.querySelectorAll('.sidebar-nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === 'auto-viz');
  });
  // Close overview if open
  const ov = document.getElementById('datasetOverview');
  if (ov) ov.style.display = 'none';
  chatMain.scrollTo({ top: 0, behavior: 'smooth' });
  fetchAndRenderAutoViz();
}

function closeAutoVisualization() {
  const page = document.getElementById('autoVizPage');
  if (page) page.style.display = 'none';
  // Destroy all auto-viz charts
  Object.values(_autoVizCharts).forEach(c => { if (c) c.destroy(); });
  Object.keys(_autoVizCharts).forEach(k => delete _autoVizCharts[k]);
  // Show messages or empty state
  document.getElementById('messagesContainer').style.display = 'flex';
  document.getElementById('emptyState').style.display = messagesContainer.children.length ? 'none' : 'block';
  inputBarWrap.classList.add('visible');
  document.querySelectorAll('.sidebar-nav-item').forEach(item => item.classList.remove('active'));
  if (chatInput) chatInput.focus();
}

function closeAllPages() {
  ['datasetOverview', 'autoVizPage', 'customChartPage'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  document.getElementById('messagesContainer').style.display = 'none';
  document.getElementById('emptyState').style.display = 'none';
  inputBarWrap.classList.remove('visible');
}

async function fetchAndRenderAutoViz() {
  const loading = document.getElementById('autoVizLoading');
  const content = document.getElementById('autoVizContent');
  const errorEl = document.getElementById('autoVizError');
  loading.style.display = 'flex';
  content.style.display = 'none';
  errorEl.style.display = 'none';

  try {
    const res = await fetch('/visualize/auto-recommendations', { method: 'POST' });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.error || 'Failed to generate recommendations');
    }

    _autoVizData = data;
    loading.style.display = 'none';
    content.style.display = 'block';

    // Render column profile
    renderColumnProfile(data.columns_profile);
    // Render recommendation cards
    renderAutoVizCards(data.recommendations);
  } catch (err) {
    loading.style.display = 'none';
    errorEl.textContent = err.message || 'Unable to generate auto visualizations.';
    errorEl.style.display = 'block';
  }
}

function renderColumnProfile(colProfile) {
  const el = document.getElementById('vizColumnProfile');
  if (!el) return;
  const { numeric, date, categorical } = colProfile;
  let html = '<div class="viz-col-profile-bar">';
  if (numeric.length) html += `<span class="viz-col-pill viz-col-num">${numeric.length} Numeric</span>`;
  if (date.length) html += `<span class="viz-col-pill viz-col-date">${date.length} Date</span>`;
  if (categorical.length) html += `<span class="viz-col-pill viz-col-cat">${categorical.length} Categorical</span>`;
  html += '</div>';
  if (numeric.length) html += `<div class="viz-col-names">Numeric: ${numeric.join(', ')}</div>`;
  if (date.length) html += `<div class="viz-col-names">Date: ${date.join(', ')}</div>`;
  if (categorical.length) html += `<div class="viz-col-names">Categorical: ${categorical.join(', ')}</div>`;
  el.innerHTML = html;
}

function renderAutoVizCards(recommendations) {
  const grid = document.getElementById('autoVizGrid');
  if (!grid) return;
  grid.innerHTML = '';

  recommendations.forEach((rec, idx) => {
    const card = document.createElement('div');
    card.className = 'auto-viz-card';
    card.dataset.idx = idx;

    const chartType = rec.chart_type;
    const chartLabel = _chartLabel(chartType);
    const confidence = rec.confidence_score;
    const isPie = chartType === 'pie' || chartType === 'donut';
    const pieSeries = rec.spec?.series?.[0];
    const pieLegend = isPie && pieSeries?.labels && pieSeries?.data
      ? pieSeries.labels.map((label, i) => {
          const value = pieSeries.data[i];
          const total = pieSeries.data.reduce((sum, item) => sum + item, 0);
          const pct = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0';
          return { label, value, pct };
        }).slice(0, 6)
      : [];

    // Build mini chart placeholder
    const canvasId = `auto-viz-canvas-${idx}`;

    let insightsHtml = '';
    if (rec.insights && rec.insights.length) {
      insightsHtml = rec.insights.slice(0, 4).map(ins => `<li>${parseMarkdown(ins)}</li>`).join('');
      insightsHtml = `<ul class="auto-viz-insights">${insightsHtml}</ul>`;
    }

    card.innerHTML = `
      <div class="auto-viz-card-header">
        <div class="auto-viz-card-title">
          <span class="auto-viz-card-icon">${_chartIconSvg(chartType)}</span>
          <div>
            <strong>${chartLabel}</strong>
            <div class="auto-viz-card-sub">${escHtml(rec.reason)}</div>
          </div>
        </div>
        <div class="auto-viz-confidence" title="Confidence score">
          <span class="confidence-badge score-${confidence >= 85 ? 'high' : confidence >= 75 ? 'mid' : 'low'}">${confidence}%</span>
        </div>
      </div>
      <div class="auto-viz-card-body">
        <div class="auto-viz-chart-shell ${isPie ? 'is-pie' : ''}">
          <div class="auto-viz-chart-mini">
            <canvas id="${canvasId}"></canvas>
          </div>
          ${isPie ? `
            <div class="auto-viz-legend-panel">
              ${pieLegend.map(item => `
                <div class="auto-viz-legend-row">
                  <span class="auto-viz-legend-label" title="${escHtml(item.label)}">${escHtml(item.label)}</span>
                  <span class="auto-viz-legend-value">${escHtml(String(item.value))}</span>
                  <span class="auto-viz-legend-pct">${item.pct}%</span>
                </div>
              `).join('')}
            </div>
          ` : ''}
        </div>
        <div class="auto-viz-card-meta">
          <span><strong>X</strong> ${escHtml(rec.x_column || '—')}</span>
          <span><strong>Y</strong> ${escHtml(rec.y_column || '—')}</span>
        </div>
        ${insightsHtml}
      </div>
      <div class="auto-viz-card-actions">
        <button class="toolbar-btn" onclick="expandAutoVizChart(${idx})"><i class="ti ti-maximize"></i> Expand</button>
        <button class="toolbar-btn" onclick="exportAutoVizChart(${idx}, 'png')"><i class="ti ti-photo"></i> PNG</button>
      </div>
    `;
    grid.appendChild(card);

    // Render chart in the mini canvas after DOM insertion
    requestAnimationFrame(() => {
      renderAutoVizMiniChart(canvasId, rec.spec);
    });
  });
}

function renderAutoVizMiniChart(canvasId, spec) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !spec) return;

  // Destroy existing if any
  if (_autoVizCharts[canvasId]) {
    _autoVizCharts[canvasId].destroy();
    delete _autoVizCharts[canvasId];
  }

  const chart = renderChart(canvasId, spec, { compact: true });
  if (chart) _autoVizCharts[canvasId] = chart;
}

/**
 * "Expand" on an Auto Visualization card opens the full Custom Chart Builder,
 * pre-populated with this recommendation's chart type and axes — giving the
 * user the complete experience (insights panel + PNG/PDF/Excel/Word export)
 * instead of a bare read-only preview.
 */
function expandAutoVizChart(idx) {
  if (!_autoVizData || !_autoVizData.recommendations[idx]) return;
  const rec = _autoVizData.recommendations[idx];
  openCustomChartFromRecommendation(rec);
}

function openCustomChartFromRecommendation(rec) {
  showCustomChartBuilder();

  // Chart type
  const typeGrid = document.getElementById('customChartTypeGrid');
  if (typeGrid && rec.chart_type) {
    typeGrid.querySelectorAll('.viz-chart-type-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.type === rec.chart_type);
    });
  }

  // Axes — override the auto-selected defaults with the recommendation's columns.
  // If the recommendation has no Y column (e.g. histogram, frequency charts),
  // keep the sensible default already chosen by populateCustomAxisDropdowns().
  const xAxis = document.getElementById('customXAxis');
  const yAxis = document.getElementById('customYAxis');
  if (xAxis && rec.x_column) xAxis.value = rec.x_column;
  if (yAxis && rec.y_column) yAxis.value = rec.y_column;

  // Sensible defaults for aggregation, sort order and Top N
  const aggRow = document.getElementById('customAggRow');
  if (aggRow) {
    aggRow.querySelectorAll('.viz-agg-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.agg === 'sum');
    });
  }
  document.getElementById('customSortOrder').value = 'desc';
  document.getElementById('customTopN').value = 20;

  checkCustomValidation();
  customGenerateChart();
}

/**
 * Export an Auto Visualization card's chart in the given format.
 * The card preview renders a compact, label-free chart to fit the small card —
 * for export, a full-quality chart (title, axis labels, legend) is rendered
 * off-screen and used as the source image instead.
 */
async function exportAutoVizChart(idx, fmt) {
  if (!_autoVizData || !_autoVizData.recommendations[idx]) return;
  const rec = _autoVizData.recommendations[idx];

  const tempWrap = document.createElement('div');
  tempWrap.style.position = 'fixed';
  tempWrap.style.left = '-9999px';
  tempWrap.style.top = '0';
  tempWrap.style.width = '800px';
  tempWrap.style.height = '450px';
  const tempCanvas = document.createElement('canvas');
  tempCanvas.id = `auto-viz-export-${idx}-${Date.now()}`;
  tempWrap.appendChild(tempCanvas);
  document.body.appendChild(tempWrap);

  const tempChart = renderChart(tempCanvas.id, rec.spec);
  if (!tempChart) {
    tempWrap.remove();
    return;
  }

  // Wait for the off-screen chart to finish its render pass before capturing it.
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));

  try {
    await downloadChartExport(fmt, tempChart, rec.spec, rec.insights || [], _chartFileSlug(rec.spec?.title));
  } finally {
    tempChart.destroy();
    tempWrap.remove();
  }
}


/* ═══════════════════════════════════════════════════════════════
   CUSTOM CHART BUILDER — PROFESSIONAL BI-STYLE
   ISSUES 2, 3, 4, 5, 7
════════════════════════════════════════════════════════════════ */
let _customChartInstance = null;
let _customChartState = null; // { spec, insights } for the currently rendered chart

function showCustomChartBuilder() {
  if (!state.uploaded) return;
  closeAllPages();
  const page = document.getElementById('customChartPage');
  page.style.display = 'block';
  document.querySelectorAll('.sidebar-nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === 'custom-chart');
  });
  const ov = document.getElementById('datasetOverview');
  if (ov) ov.style.display = 'none';
  chatMain.scrollTo({ top: 0, behavior: 'smooth' });

  // Populate axis dropdowns from dataset
  populateCustomAxisDropdowns();
  // Reset preview
  resetCustomChartPreview();
  // Reset warning + sync control availability with the active chart type
  checkCustomValidation();
}

function closeCustomChartBuilder() {
  const page = document.getElementById('customChartPage');
  if (page) page.style.display = 'none';
  if (_customChartInstance) {
    _customChartInstance.destroy();
    _customChartInstance = null;
  }
  document.getElementById('messagesContainer').style.display = 'flex';
  document.getElementById('emptyState').style.display = messagesContainer.children.length ? 'none' : 'block';
  inputBarWrap.classList.add('visible');
  document.querySelectorAll('.sidebar-nav-item').forEach(item => item.classList.remove('active'));
  if (chatInput) chatInput.focus();
}

function populateCustomAxisDropdowns() {
  // Get all columns from state (master table data)
  const allColumns = state.dataset.columns || [];
  const xAxis = document.getElementById('customXAxis');
  const yAxis = document.getElementById('customYAxis');
  if (!xAxis || !yAxis) return;

  xAxis.innerHTML = allColumns.map(c => `<option value="${escHtml(c)}">${escHtml(c)}</option>`).join('');
  yAxis.innerHTML = allColumns.map(c => `<option value="${escHtml(c)}">${escHtml(c)}</option>`).join('');

  // Pre-select logical defaults
  const { numCols, catCols, dateCols } = classifyColumnsFromSchema(allColumns);
  if (catCols.length) xAxis.value = catCols[0];
  else if (dateCols.length) xAxis.value = dateCols[0];
  if (numCols.length) yAxis.value = numCols[0];
  else if (allColumns.length >= 2) yAxis.value = allColumns[1];
}

function resetCustomChartPreview() {
  const empty = document.getElementById('customChartEmpty');
  const insights = document.getElementById('customChartInsights');
  if (empty) empty.style.display = 'flex';
  if (insights) insights.style.display = 'none';
  if (_customChartInstance) {
    _customChartInstance.destroy();
    _customChartInstance = null;
  }
  _customChartState = null;
}

function resetCustomChartBuilder() {
  populateCustomAxisDropdowns();
  resetCustomChartPreview();
  // Reset chart type to bar
  const grid = document.getElementById('customChartTypeGrid');
  if (grid) {
    grid.querySelectorAll('.viz-chart-type-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.type === 'bar');
    });
  }
  // Reset agg to sum
  const aggRow = document.getElementById('customAggRow');
  if (aggRow) {
    aggRow.querySelectorAll('.viz-agg-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.agg === 'sum');
    });
  }
  document.getElementById('customSortOrder').value = 'desc';
  document.getElementById('customTopN').value = 20;
  checkCustomValidation();
}

/* ── ISSUE 4: Chart Validation Rules (Professional BI-style) ── */
function validateChartConfiguration(chartType, xCol, yCol) {
  if (!xCol && !yCol) {
    return { valid: false, suggestion: null, message: 'Please select at least one axis column.' };
  }

  const allColumns = state.dataset.columns || [];
  const { numCols, catCols, dateCols } = classifyColumnsFromSchema(allColumns);

  const xIsNum = numCols.includes(xCol);
  const xIsCat = catCols.includes(xCol);
  const xIsDate = dateCols.includes(xCol);
  const yIsNum = yCol ? numCols.includes(yCol) : false;
  const yIsCat = yCol ? catCols.includes(yCol) : false;
  const yIsDate = yCol ? dateCols.includes(yCol) : false;

  // ISSUE 4: Professional validation rules with friendly messages
  if (chartType === 'scatter') {
    if (!yIsNum || !xIsNum) {
      let suggestion = 'bar';
      let message = 'Scatter Plot requires two numeric columns. ';
      if (xIsCat && yIsNum) {
        suggestion = 'bar';
        message += 'Since your X-axis is categorical, try a **Bar Chart** instead to compare values across categories.';
      } else if (xIsDate && yIsNum) {
        suggestion = 'line';
        message += 'Since your X-axis is a date, try a **Line Chart** instead to show trends over time.';
      } else {
        message += 'Try **Bar Chart** instead for mixed data types.';
      }
      return { valid: false, suggestion, message };
    }
  }

  if (chartType === 'pie' || chartType === 'donut') {
    if (!xIsCat) {
      let message = 'Pie Chart requires a categorical X-axis (text labels). ';
      if (xIsDate) {
        message += 'Try **Bar Chart** instead to show date-based distribution.';
      } else {
        message += 'Try **Bar Chart** instead.';
      }
      return { valid: false, suggestion: 'bar', message };
    }
    if (yCol && !yIsNum) {
      return { valid: false, suggestion: 'bar', message: 'Pie Chart requires a numeric Y-axis. Try **Bar Chart** instead.' };
    }
  }

  if (chartType === 'histogram') {
    if (!yIsNum && !xIsNum) {
      let message = 'Histogram requires a numeric column. ';
      if (xIsCat && yIsNum) {
        message += 'Since you have a categorical X-axis and numeric Y-axis, try **Bar Chart** instead.';
      } else {
        message += 'Try **Bar Chart** instead.';
      }
      return { valid: false, suggestion: 'bar', message };
    }
  }

  if (chartType === 'line' || chartType === 'area') {
    if (!xIsDate && !xIsNum) {
      let message = 'Line Chart works best with a Date or Numeric X-axis. ';
      if (xIsCat && yIsNum) {
        message += 'Since your X-axis is categorical, try **Bar Chart** for clearer comparison.';
      } else {
        message += 'Try **Bar Chart** instead.';
      }
      return { valid: false, suggestion: 'bar', message };
    }
    if (!yIsNum) {
      return { valid: false, suggestion: 'bar', message: 'Line Chart requires a numeric Y-axis. Try **Bar Chart** instead.' };
    }
  }

  return { valid: true, suggestion: null, message: '' };
}

/* ── ISSUE 4: Get chart type suggestion based on column types ── */
function getSuggestedChartType(xCol, yCol) {
  const allColumns = state.dataset.columns || [];
  const { numCols, catCols, dateCols } = classifyColumnsFromSchema(allColumns);
  
  const xIsNum = numCols.includes(xCol);
  const xIsCat = catCols.includes(xCol);
  const xIsDate = dateCols.includes(xCol);
  const yIsNum = yCol ? numCols.includes(yCol) : false;

  if (xIsCat && yIsNum) return 'bar';
  if (xIsDate && yIsNum) return 'line';
  if (xIsNum && yIsNum) return 'scatter';
  if (xIsNum && !yCol) return 'histogram';
  if (xIsCat && !yCol) return 'pie';
  return 'bar';
}

/* ── Generate Custom Chart (Backend-Powered) ───────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const generateBtn = document.getElementById('customGenerateBtn');
  if (generateBtn) generateBtn.addEventListener('click', customGenerateChart);

  // Chart type selection in custom builder
  const typeGrid = document.getElementById('customChartTypeGrid');
  if (typeGrid) {
    typeGrid.addEventListener('click', (e) => {
      const btn = e.target.closest('.viz-chart-type-btn');
      if (!btn) return;
      typeGrid.querySelectorAll('.viz-chart-type-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      // Auto-validate on type change
      checkCustomValidation();
    });
  }

  // Axis change validation
  const cx = document.getElementById('customXAxis');
  const cy = document.getElementById('customYAxis');
  if (cx) cx.addEventListener('change', function() {
    // ISSUE 4: Auto-suggest chart type when axis changes
    const suggestedType = getSuggestedChartType(this.value, cy ? cy.value : '');
    const typeGrid = document.getElementById('customChartTypeGrid');
    if (typeGrid && suggestedType) {
      typeGrid.querySelectorAll('.viz-chart-type-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.type === suggestedType);
      });
    }
    checkCustomValidation();
  });
  if (cy) cy.addEventListener('change', function() {
    const suggestedType = getSuggestedChartType(cx ? cx.value : '', this.value);
    const typeGrid = document.getElementById('customChartTypeGrid');
    if (typeGrid && suggestedType) {
      typeGrid.querySelectorAll('.viz-chart-type-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.type === suggestedType);
      });
    }
    checkCustomValidation();
  });
  
  // Top N change validation
  const topNInput = document.getElementById('customTopN');
  if (topNInput) {
    topNInput.addEventListener('change', function() {
      validateTopNInput(this);
      checkCustomValidation();
    });
  }

  // Sort order change
  const sortOrder = document.getElementById('customSortOrder');
  if (sortOrder) {
    sortOrder.addEventListener('change', checkCustomValidation);
  }
});

/** ISSUE 2: Validate the Top N input field with proper capping */
function validateTopNInput(input) {
  let val = parseInt(input.value, 10);
  const validValues = [5, 10, 20, 50, 100];
  
  // Handle NaN
  if (isNaN(val) || val < 1) {
    val = 10;
  }
  
  // Find nearest valid value
  const nearest = validValues.reduce((prev, curr) => 
    Math.abs(curr - val) < Math.abs(prev - val) ? curr : prev
  );
  
  // ISSUE 2: Cap at dataset row count
  const maxRows = state.dataset.rows || 1000;
  const capped = Math.min(nearest, maxRows);
  
  if (val !== capped || !validValues.includes(val)) {
    input.value = capped;
    // Show brief validation message
    const warning = document.getElementById('customChartWarning');
    if (val !== capped) {
      if (capped < val && val !== capped) {
        warning.innerHTML = `Capped to ${capped} (dataset has ${maxRows.toLocaleString()} rows)`;
      } else {
        warning.innerHTML = `Adjusted to nearest valid value: Top ${capped}`;
      }
      warning.style.display = 'block';
      setTimeout(() => {
        if (warning.innerHTML.startsWith('Capped') || warning.innerHTML.startsWith('Adjusted')) {
          warning.style.display = 'none';
        }
      }, 3000);
    }
  }
}

function checkCustomValidation() {
  const chartType = document.getElementById('customChartTypeGrid')?.querySelector('.viz-chart-type-btn.active')?.dataset.type || 'bar';
  const xCol = document.getElementById('customXAxis')?.value || '';
  const yCol = document.getElementById('customYAxis')?.value || '';
  const warning = document.getElementById('customChartWarning');

  updateCustomControlAvailability(chartType);

  // Hard validation errors — incompatible chart type / axis combination
  const result = validateChartConfiguration(chartType, xCol, yCol);
  if (!result.valid) {
    warning.innerHTML = parseMarkdown(result.message);
    warning.className = 'custom-chart-warning';
    warning.style.display = 'block';
    return;
  }

  // Soft notice — Pie/Donut charts cap at 20 categories for readability
  if (chartType === 'pie' || chartType === 'donut') {
    const topN = parseInt(document.getElementById('customTopN')?.value || '20', 10);
    if (topN > 20) {
      warning.innerHTML = parseMarkdown(`Pie and Donut charts display up to **20** categories for readability. Showing the top 20 of your requested ${topN}.`);
      warning.className = 'custom-chart-warning info';
      warning.style.display = 'block';
      return;
    }
  }

  warning.className = 'custom-chart-warning';
  warning.style.display = 'none';
}

async function customGenerateChart() {
  const chartType = document.getElementById('customChartTypeGrid')?.querySelector('.viz-chart-type-btn.active')?.dataset.type || 'bar';
  const xCol = document.getElementById('customXAxis')?.value || '';
  const yCol = document.getElementById('customYAxis')?.value || '';
  const agg = document.getElementById('customAggRow')?.querySelector('.viz-agg-btn.active')?.dataset.agg || 'sum';
  const sortOrder = document.getElementById('customSortOrder')?.value || 'desc';
  let topN = parseInt(document.getElementById('customTopN')?.value || '20', 10);

  // Validate
  const validation = validateChartConfiguration(chartType, xCol, yCol);
  if (!validation.valid) {
    const warning = document.getElementById('customChartWarning');
    warning.innerHTML = parseMarkdown(validation.message);
    warning.className = 'custom-chart-warning';
    warning.style.display = 'block';
    return;
  }

  // ISSUE 2: Validate Top N - properly cap and validate
  const validTopN = [5, 10, 20, 50, 100];
  if (isNaN(topN) || topN < 1) topN = 10;
  const nearest = validTopN.reduce((prev, curr) =>
    Math.abs(curr - topN) < Math.abs(prev - topN) ? curr : prev
  );
  topN = Math.min(nearest, state.dataset.rows || 1000);
  document.getElementById('customTopN').value = topN;

  // Refresh the inline notice (e.g. Pie/Donut Top-N cap) for the normalized value
  checkCustomValidation();

  // Show loading state on button
  const generateBtn = document.getElementById('customGenerateBtn');
  const originalText = generateBtn.innerHTML;
  generateBtn.innerHTML = '<i class="ti ti-spinner"></i> Generating...';
  generateBtn.disabled = true;

  try {
    // Fetch spec from backend (uses full dataset, correct pipeline)
    const result = await fetchCustomChartSpec(chartType, xCol, yCol, agg, sortOrder, topN);
    
    if (!result) {
      // Fallback to local spec building using preview rows
      console.warn('Backend custom render failed, falling back to local rendering');
      const td = state.tableData['master'];
      if (!td) {
        showToast('No dataset loaded. Please upload a dataset first.', 'warning');
        return;
      }
      showToast('Could not reach the server for this chart — showing a quick local preview instead.', 'warning');
      const spec = buildCustomSpec(chartType, td.columns, td.allRows, xCol, yCol, agg, sortOrder, topN);
      renderCustomChart(spec, []);
      renderCustomChartInsights(spec, chartType, xCol, yCol);
    } else {
      // Render using backend spec + professional insights
      renderCustomChart(result.spec, result.insights || []);
    }
  } catch (err) {
    console.error('Chart generation failed:', err);
    // Final fallback
    const td = state.tableData['master'];
    if (td) {
      showToast('Could not reach the server for this chart — showing a quick local preview instead.', 'warning');
      const spec = buildCustomSpec(chartType, td.columns, td.allRows, xCol, yCol, agg, sortOrder, topN);
      renderCustomChart(spec, []);
      renderCustomChartInsights(spec, chartType, xCol, yCol);
    } else {
      showToast('Chart generation failed. Please try again.', 'error');
    }
  } finally {
    generateBtn.innerHTML = originalText;
    generateBtn.disabled = false;
  }
}

/** Render the chart and professional insights */
function renderCustomChart(spec, insights) {
  if (_customChartInstance) {
    _customChartInstance.destroy();
    _customChartInstance = null;
  }

  _customChartState = { spec, insights: insights || [] };

  // Show chart
  const empty = document.getElementById('customChartEmpty');
  const canvas = document.getElementById('customChartCanvas');
  if (empty) empty.style.display = 'none';
  if (canvas) {
    requestAnimationFrame(() => {
      _customChartInstance = renderChart('customChartCanvas', spec);
    });
  }

  // Show professional insights
  const panel = document.getElementById('customChartInsights');
  const body = document.getElementById('customChartInsightsBody');
  if (panel && body) {
    if (insights && insights.length > 0) {
      body.innerHTML = insights.map(i => `<div class="chart-insight-item">${parseMarkdown(i)}</div>`).join('');
      panel.style.display = 'block';
    } else {
      panel.style.display = 'none';
    }
  }
}

function buildCustomSpec(chartType, columns, rows, xCol, yCol, agg, sortOrder, topN) {
  const MAX = 500;
  const limited = rows.slice(0, MAX);

  if (chartType === 'scatter' && xCol && yCol) {
    return {
      plotType: 'scatter',
      title: `${yCol} vs ${xCol}`,
      xLabel: xCol, yLabel: yCol,
      series: [{ label: 'Data', data: limited.map(r => ({ x: Number(r[xCol]), y: Number(r[yCol]) })) }]
    };
  }

  if (chartType === 'histogram') {
    const col = yCol || xCol;
    const vals = rows.map(r => Number(r[col])).filter(v => !isNaN(v));
    return buildHistogramSpec(col, vals);
  }

  // Aggregate
  const aggMap = {};
  rows.forEach(r => {
    const k = String(r[xCol] ?? '(blank)');
    const v = Number(r[yCol]) || 0;
    if (!aggMap[k]) aggMap[k] = { sum: 0, count: 0, min: Infinity, max: -Infinity, vals: [] };
    aggMap[k].sum += v;
    aggMap[k].count += 1;
    aggMap[k].min = Math.min(aggMap[k].min, v);
    aggMap[k].max = Math.max(aggMap[k].max, v);
    aggMap[k].vals.push(v);
  });

  const getValue = (entry) => {
    switch (agg) {
      case 'avg': return entry.count ? entry.sum / entry.count : 0;
      case 'count': return entry.count;
      case 'max': return entry.max;
      case 'min': return entry.min;
      case 'median': {
        const sorted = [...entry.vals].sort((a, b) => a - b);
        const mid = Math.floor(sorted.length / 2);
        return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
      }
      default: return entry.sum;
    }
  };

  // ISSUE 3: Sort descending first, then reverse if asc
  let sorted = Object.entries(aggMap).sort((a, b) => getValue(b[1]) - getValue(a[1]));
  if (sortOrder === 'asc') sorted.reverse();
  sorted = sorted.slice(0, topN);

  const labels = sorted.map(e => e[0]);
  const data = sorted.map(e => +getValue(e[1]).toFixed(2));

  return {
    plotType: chartType,
    title: `${agg.toUpperCase()}(${yCol || 'Count'}) by ${xCol}`,
    xLabel: xCol, yLabel: yCol || 'Count',
    labels,
    series: [{ label: yCol || 'Count', data, labels }]
  };
}

function renderCustomChartInsights(spec, chartType, xCol, yCol) {
  const panel = document.getElementById('customChartInsights');
  const body = document.getElementById('customChartInsightsBody');
  if (!panel || !body) return;

  const insights = [];

  if (spec.series && spec.series[0]) {
    const data = spec.series[0].data || [];
    const labels = spec.series[0].labels || [];

    if (data.length) {
      const values = data.filter(v => typeof v === 'number');
      const maxVal = Math.max(...values);
      const minVal = Math.min(...values);
      const sumVal = values.reduce((a, b) => a + b, 0);
      const avgVal = sumVal / values.length;

      const maxIdx = data.indexOf(maxVal);
      const minIdx = data.indexOf(minVal);
      const maxLabel = labels[maxIdx] || '—';
      const minLabel = labels[minIdx] || '—';

      insights.push(`Highest: ${maxLabel} (${maxVal.toLocaleString()})`);
      insights.push(`Lowest: ${minLabel} (${minVal.toLocaleString()})`);
      insights.push(`Average: ${avgVal.toLocaleString(undefined, {maximumFractionDigits: 2})}`);
      insights.push(`Total: ${sumVal.toLocaleString()} across ${data.length} categories`);
    }
  }

  if (chartType === 'line' || chartType === 'area') {
    insights.push(`Trend view: ${xCol} over time showing ${yCol} patterns`);
  } else if (chartType === 'scatter') {
    insights.push(`Correlation view: Relationship between ${xCol} and ${yCol}`);
  } else if (chartType === 'pie') {
    insights.push(`Proportion view: Relative share of each ${xCol} category`);
  } else if (chartType === 'histogram') {
    insights.push(`Distribution: Spread of ${yCol || xCol} values`);
  }

  body.innerHTML = insights.map(i => `<div class="chart-insight-item">${parseMarkdown(i)}</div>`).join('');
  panel.style.display = 'block';
}

/** Build a safe filename slug from a chart title. */
function _chartFileSlug(text) {
  const slug = String(text || 'chart')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug || 'chart';
}

/** Trigger a browser download for a data: or blob: URL. */
function downloadDataUrl(url, filename) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

/**
 * Export a rendered Chart.js instance.
 * PNG is generated entirely client-side from the canvas (always accurate).
 * PDF/DOCX/XLSX are built server-side from the chart image + data + insights.
 */
async function downloadChartExport(fmt, chartInstance, spec, insights, filenameBase) {
  if (!chartInstance) {
    showToast('Generate a chart first, then export it.', 'warning');
    return;
  }

  const image = chartInstance.toBase64Image('image/png', 1.0);

  if (fmt === 'png') {
    downloadDataUrl(image, `${filenameBase}.png`);
    showToast(`${filenameBase}.png downloaded.`, 'success');
    return;
  }

  const series = (spec.series && spec.series[0]) || {};
  try {
    const res = await fetch(`/visualize/export-chart/${fmt}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: spec.title || 'Chart',
        x_label: spec.xLabel || '',
        y_label: spec.yLabel || '',
        series_label: series.label || spec.yLabel || 'Value',
        labels: series.labels || spec.labels || [],
        data: series.data || [],
        insights: insights || [],
        image,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Export failed (${res.status})`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    downloadDataUrl(url, `${filenameBase}.${fmt}`);
    URL.revokeObjectURL(url);
    showToast(`${filenameBase}.${fmt} downloaded.`, 'success');
  } catch (err) {
    console.error('Chart export failed:', err);
    showToast(err.message || 'Chart export failed. Please try again.', 'error');
  }
}

async function exportCustomChart(fmt, btn) {
  if (!_customChartInstance || !_customChartState) {
    showToast('Generate a chart first, then export it.', 'warning');
    return;
  }
  const { spec, insights } = _customChartState;

  // PNG is generated client-side and downloads instantly; PDF/Excel/Word
  // require a server round-trip, so show a brief loading state on the button.
  if (btn && fmt !== 'png') {
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="ti ti-spinner"></i> Exporting...';
    try {
      await downloadChartExport(fmt, _customChartInstance, spec, insights, _chartFileSlug(spec.title));
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
    return;
  }

  downloadChartExport(fmt, _customChartInstance, spec, insights, _chartFileSlug(spec.title));
}


/* ═══════════════════════════════════════════════════════════════
   MARKDOWN PARSER
════════════════════════════════════════════════════════════════ */
function parseMarkdown(md) {
  if (!md) return '';
  let html = md
    .replace(/&/g, '&')
    .replace(/</g, '<')
    .replace(/>/g, '>');

  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim,  '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim,   '<h1>$1</h1>');
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/g,     '<em>$1</em>');
  html = html.replace(/`(.*?)`/g,       '<code>$1</code>');
  html = html.replace(/^>\s*\[!TIP\]\s*-?\s*(.*$)/gim,     '<div class="md-tip">$1</div>');
  html = html.replace(/^>\s*\[!WARNING\]\s*-?\s*(.*$)/gim, '<div class="md-warning">$1</div>');
  html = html.replace(/^>\s*(.*$)/gim, '<blockquote>$1</blockquote>');
  html = html.replace(/^\s*-\s+(.*$)/gim, '<li>$1</li>');
  html = html.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>');

  const lines = html.split('\n');
  let inTable = false, tableHtml = '';
  const outLines = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('|') && line.endsWith('|')) {
      if (!inTable) { inTable = true; tableHtml = '<table>'; }
      if (/^\|[-:\s|]+\|$/.test(line)) continue;
      const parts = line.slice(1, -1).split('|').map(p => p.trim());
      const tag = tableHtml === '<table>' ? 'th' : 'td';
      tableHtml += '<tr>' + parts.map(p => `<${tag}>${p}</${tag}>`).join('') + '</tr>';
      outLines.push('');
    } else {
      if (inTable) { tableHtml += '</table>'; outLines.push(tableHtml); tableHtml = ''; inTable = false; }
      outLines.push(lines[i]);
    }
  }
  if (inTable) outLines.push(tableHtml + '</table>');
  html = outLines.join('\n');
  // Collapse 3+ consecutive <br> into max 1, and collapse 2 into 1
  html = html.replace(/(<br\s*\/??>\s*){2,}/gi, '<br>');
  html = html.replace(/\n/g, '<br>');
  // Final pass: collapse any remaining double-br
  html = html.replace(/(<br\s*\/??>\s*){2,}/gi, '<br>');
  return html;
}