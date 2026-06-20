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
  _toastTimers: {}, // track toast auto-dismiss timers
  // Replace missing values state
  rmColumns: [],
  rmSelectedColumn: null,
  rmSelectedMethod: null,
  rmSortAsc: false,
  rmBeforeTotal: 0,
};

const PAGE_SIZE = 20;

/* ═══════════════════════════════════════════════════════════════
   DOM REFS
════════════════════════════════════════════════════════════════ */
const chatScreen        = document.getElementById('chatScreen');
const fileInput         = document.getElementById('fileInput');
const attachBtn         = document.getElementById('attachBtn');

const datasetName          = document.getElementById('datasetName');
const datasetMeta          = document.getElementById('datasetMeta');
const datasetBadgeStatus   = document.getElementById('datasetBadgeStatus');
const noDatasetEmpty       = document.getElementById('noDatasetEmpty');
const datasetEmpty         = document.getElementById('datasetEmpty');
const newChatBtn        = document.getElementById('newChatBtn');
const chatMain          = document.getElementById('chatMain');
const emptyState        = document.getElementById('emptyState');
const messagesContainer = document.getElementById('messagesContainer');
const leftSidebar       = document.getElementById('leftSidebar');
const leftSidebarToggle = document.getElementById('leftSidebarToggle');
const leftSidebarClose  = document.getElementById('leftSidebarClose');
const sidebarScrim      = document.getElementById('sidebarScrim');
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
   UPLOAD — via + button in input bar
════════════════════════════════════════════════════════════════ */
const _attachIcon = attachBtn.innerHTML;  // capture original icon to restore after upload

attachBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => {
  if (fileInput.files.length) doUpload(fileInput.files[0]);
});

async function doUpload(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['csv', 'xlsx', 'xls', 'tsv', 'txt'].includes(ext)) {
    showToast('Only CSV, Excel (.xlsx/.xls), TSV, or TXT files are supported.', 'error');
    fileInput.value = '';
    return;
  }

  attachBtn.disabled = true;
  attachBtn.innerHTML = iconSpinner();
  attachBtn.classList.add('spinning');

  const fd = new FormData();
  fd.append('file', file);

  try {
    const res  = await fetch('/upload', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || 'Upload failed.', 'error');
      return;
    }

    state.dataset        = { name: file.name, rows: data.rows, columns: data.columns };
    state.uploaded       = true;
    state.masterSchema   = data.schema || {};
    state.previewTruncated = !!data.preview_truncated;
    state.previewRowCount  = data.preview_row_count || 0;

    onDatasetLoaded(data);
    showToast(`"${file.name}" uploaded — ${data.rows.toLocaleString()} rows, ${data.columns.length} columns.`, 'success');

  } catch {
    showToast('Upload failed. Please check your connection.', 'error');
  } finally {
    attachBtn.disabled = false;
    attachBtn.innerHTML = _attachIcon;
    attachBtn.classList.remove('spinning');
    fileInput.value = '';
  }
}

/* ═══════════════════════════════════════════════════════════════
   DATASET LOADED — switch empty state, enable input
════════════════════════════════════════════════════════════════ */
function onDatasetLoaded(data) {
  datasetName.textContent = state.dataset.name;
  datasetMeta.textContent = `${data.rows.toLocaleString()} rows · ${data.columns.length} cols`;
  datasetBadgeStatus.textContent = '● Ready';
  datasetBadgeStatus.classList.add('ready');

  state.tableData['master'] = {
    columns: data.columns,
    allRows: data.preview_rows || [],
    page: 0,
    sql: 'SELECT * FROM dataset'
  };

  populateOverview(data);

  // Switch empty state to "ask anything" variant
  noDatasetEmpty.style.display = 'none';
  datasetEmpty.style.display   = 'flex';
  emptyState.style.display     = 'flex';
  messagesContainer.style.display = 'none';

  // Enable input
  chatInput.disabled   = false;
  chatInput.placeholder = 'Ask anything about your dataset...';
  sendBtn.disabled     = chatInput.value.trim() === '';
  chatInput.focus();

  // On tablet/mobile, the sidebar is an overlay drawer — start collapsed
  if (window.innerWidth <= 1100 && state.leftSidebarOpen) {
    state.leftSidebarOpen = false;
    leftSidebar.classList.add('hidden');
    if (sidebarScrim) sidebarScrim.classList.remove('visible');
  }

  // Update replace missing badge
  updateReplaceMissingBadge();
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

  closeAllPages();
  datasetOverview.style.display = 'block';
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
  emptyState.style.display = messagesContainer.children.length ? 'none' : 'flex';
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
  ].join('');

  const mixed = overview.column_types.mixed || 0;
  document.getElementById('overviewTypes').innerHTML = [
    statCard('Numeric Columns',     overview.column_types.numeric,      'ti-numbers'),
    statCard('Categorical Columns', overview.column_types.categorical,   'ti-tags'),
    statCard('Date/Time Columns',   overview.column_types.date,         'ti-calendar'),
    statCard('Boolean Columns',     overview.column_types.boolean,      'ti-toggle-left'),
    ...(mixed > 0 ? [statCard('Mixed-Type Columns', mixed, 'ti-alert-triangle')] : []),
  ].join('');

  // Schema table — includes null count column
  const qMap = {};
  (overview.column_quality || []).forEach(q => { qMap[q.column] = q; });
  document.getElementById('overviewSchemaBody').innerHTML = overview.schema_details.map(item => {
    const q = qMap[item.column_name] || {};
    const issueHtml = (q.issues && q.issues.length)
      ? `<span class="overview-col-issues">${q.issues.map(i => escHtml(i)).join(' · ')}</span>`
      : '';
    return `<tr>
      <td><strong>${escHtml(item.column_name)}</strong>${issueHtml}</td>
      <td><span class="overview-type-badge overview-type-${(item.sqlite_type||'').toLowerCase()}">${escHtml(item.sqlite_type)}</span></td>
      <td class="overview-null-cell">${item.null_count > 0
        ? `<span class="overview-null-warn">${item.null_count.toLocaleString()}</span> / ${overview.total_rows.toLocaleString()}`
        : `<span class="overview-null-ok">0</span> / ${overview.total_rows.toLocaleString()}`}</td>
      <td>${item.sample_values.length
        ? item.sample_values.map(v => escHtml(v)).join(', ')
        : '<span class="overview-muted">—</span>'}</td>
    </tr>`;
  }).join('');

  const detailRow = (label, value, warn) => `
    <div class="overview-detail-row${warn ? ' overview-detail-warn' : ''}">
      <span>${escHtml(label)}</span><strong>${escHtml(String(value))}</strong>
    </div>`;
  const q = overview.data_quality;
  const nOutliers = q.outlier_count || 0;
  const nConst    = q.constant_columns || 0;
  const nMixed    = q.mixed_type_columns || 0;
  const nEnc      = q.encoding_issues || 0;
  const outlierCols = (q.outlier_columns || []).slice(0, 3).join(', ');
  document.getElementById('overviewQuality').innerHTML = [
    detailRow('Total Missing Values',  q.total_missing_values.toLocaleString(),                                         q.total_missing_values > 0),
    detailRow('Missing Value %',       `${q.missing_percentage}%`,                                                      q.missing_percentage > 5),
    detailRow('Duplicate Rows',        q.duplicate_records.toLocaleString(),                                            q.duplicate_records > 0),
    detailRow('Empty Columns',         q.empty_columns,                                                                 q.empty_columns > 0),
    detailRow('Constant Columns',      nConst,                                                                          nConst > 0),
    detailRow('Outlier Values',        nOutliers > 0 ? `${nOutliers.toLocaleString()}${outlierCols ? ' in: ' + outlierCols : ''}` : '0', nOutliers > 0),
    detailRow('Mixed-Type Columns',    nMixed,                                                                          nMixed > 0),
    detailRow('Encoding Issues',       nEnc > 0 ? `${nEnc} chars` : '0',                                               nEnc > 0),
    detailRow('Data Consistency',      `${q.consistency_percentage}%`,                                                  q.consistency_percentage < 95),
  ].join('');

  const keys = overview.key_fields;
  document.getElementById('overviewKeys').innerHTML = [
    detailRow('Primary Identifier', keys.primary_id || 'Not detected'),
    detailRow('Date Column',        keys.date_column || 'Not detected'),
    detailRow('Main Measures',      keys.measure_columns.length ? keys.measure_columns.join(', ') : 'Not detected'),
  ].join('');

  // Issues section
  const issuesSection = document.getElementById('overviewIssuesSection');
  const issuesList    = document.getElementById('overviewIssues');
  const issues = overview.issues || [];
  if (issues.length && issuesSection && issuesList) {
    issuesList.innerHTML = issues.map(i => `
      <div class="overview-issue-item">
        <i class="ti ti-alert-triangle"></i>
        <span>${escHtml(i)}</span>
      </div>`).join('');
    issuesSection.style.display = '';
  } else if (issuesSection) {
    issuesSection.style.display = 'none';
  }
}

function exportDatasetOverview() {
  const format = document.getElementById('overviewExportFormat').value;
  window.location.href = `/dataset-overview/download/${format}`;
}

/* ═══════════════════════════════════════════════════════════════
   NEW DATASET / RESET
════════════════════════════════════════════════════════════════ */
function resetToNoDataset() {
  Object.values(state.chartMap).forEach(c => c && c.destroy && c.destroy());
  if (state.vizModal.chart) { state.vizModal.chart.destroy(); state.vizModal.chart = null; }

  state.chartMap     = {};
  state.tableData    = {};
  state.uploaded     = false;
  state.dataset      = { name: '', rows: 0, columns: [] };
  state.querying     = false;
  state.lastSQL      = '';
  state.overview     = null;
  state.vizModal     = { msgId: null, chart: null };
  state.previewTruncated = false;
  state.previewRowCount  = 0;
  state.masterSchema = {};
  state.rmColumns    = [];

  messagesContainer.innerHTML  = '';
  messagesContainer.style.display = 'flex';
  closeAllPages();

  noDatasetEmpty.style.display = 'flex';
  datasetEmpty.style.display   = 'none';
  emptyState.style.display     = 'flex';
  inputBarWrap.classList.add('visible');

  datasetName.textContent         = 'No dataset';
  datasetMeta.textContent         = 'Upload a file to begin';
  datasetBadgeStatus.textContent  = '● No data';
  datasetBadgeStatus.classList.remove('ready');

  chatInput.value       = '';
  chatInput.style.height = 'auto';
  chatInput.disabled    = true;
  chatInput.placeholder = 'Upload a dataset to get started...';
  sendBtn.disabled      = true;
  fileInput.value       = '';
  closeVizModal();

  // Reset replace missing badge
  const badge = document.getElementById('replaceMissingBadge');
  if (badge) { badge.style.display = 'none'; badge.textContent = '0'; }
}

newChatBtn.addEventListener('click', () => {
  document.body.classList.add('page-transition-out');
  setTimeout(() => { window.location.href = '/'; }, 160);
  setTimeout(() => resetToNoDataset(), 0);
});

/* ═══════════════════════════════════════════════════════════════
   SIDEBAR TOGGLE
     ════════════════════════════════════════════════════════════════ */
if (leftSidebarToggle) leftSidebarToggle.addEventListener('click', toggleLeftSidebar);
if (leftSidebarClose) leftSidebarClose.addEventListener('click', toggleLeftSidebar);

function toggleLeftSidebar() {
  state.leftSidebarOpen = !state.leftSidebarOpen;
  leftSidebar.classList.toggle('hidden', !state.leftSidebarOpen);
  if (sidebarScrim) {
    sidebarScrim.classList.toggle('visible', state.leftSidebarOpen && window.innerWidth <= 1100);
  }
}

if (sidebarScrim) {
  sidebarScrim.addEventListener('click', () => {
    if (state.leftSidebarOpen) toggleLeftSidebar();
  });
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

// Empty-state quick chips - populate input with the example prompt
document.querySelectorAll('.quick-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    const prompt = chip.dataset.prompt;
    if (!prompt) return;
    chatInput.value = prompt;
    chatInput.dispatchEvent(new Event('input'));
    chatInput.focus();
  });
});

/* ═══════════════════════════════════════════════════════════════
   INPUT BAR
════════════════════════════════════════════════════════════════ */
chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 140) + 'px';
  sendBtn.disabled = !state.uploaded || chatInput.value.trim() === '';
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
function toggleTheme(){
  const body = document.body;
  const curr = body.getAttribute('data-theme') || 'light';
  const next = curr === 'dark' ? 'light' : 'dark';
  body.setAttribute('data-theme', next);
  try { localStorage.setItem('theme', next); } catch {}
}

if (themeToggle) themeToggle.addEventListener('click', toggleTheme);

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

  // Generate unique resultId for per-card export
  const resultId = 'msg-' + Date.now();

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
      body:    JSON.stringify({ question: text, resultId: resultId }),
    });
    const data = await res.json();

    removeMsg(loadingId);

    if (!res.ok) {
      appendErrorMsg(data.error || 'Query failed. Please try again.');
      return;
    }

    if (data.type === 'irrelevant') {
      appendIrrelevantMsg(data.message, data.suggestions || []);
      return;
    }

    // Store resultId in the table data for per-card export
    if (data.type === 'query' && data.resultId) {
      // The data will be stored by appendAIMsg; we add resultId to state
      state._lastResultId = data.resultId;
    }

    appendAIMsg(data, text);

  } catch (err) {
    removeMsg(loadingId);
    appendErrorMsg('Could not reach the server. Please check your connection.');
    console.error(err);
  } finally {
    state.querying = false;
    sendBtn.disabled = !state.uploaded || chatInput.value.trim() === '';
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

  row.innerHTML = `
    <div class="msg-ai-wrap">
      <div class="msg-ai-avatar" aria-hidden="true">${iconBot()}</div>
      <div class="msg-ai-card">${inner || '<div class="ai-summary">Done</div>'}</div>
    </div>`;

  messagesContainer.appendChild(row);

  // Register table data for pagination — store resultId for per-card export
  if (data.type !== 'visualization' && data.columns && data.rows) {
    state.tableData[msgId] = {
      columns: data.columns,
      allRows: data.rows,
      page: 0,
      sql: state.lastSQL,
      resultId: data.resultId || msgId  // Use server-returned resultId, fallback to msgId
    };
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
          <button class="toolbar-btn" onclick="toggleDlMenu('${msgId}', event)" aria-haspopup="true" aria-expanded="false"><i class="ti ti-download"></i> Export ▾</button>
          <div class="dl-menu" id="dlmenu-${msgId}">
            <button class="dl-opt" onclick="dlFmt('${msgId}', 'csv')">CSV (.csv)</button>
            <button class="dl-opt" onclick="dlFmt('${msgId}', 'xlsx')">Excel (.xlsx)</button>
            <button class="dl-opt" onclick="dlFmt('${msgId}', 'pdf')">PDF (.pdf)</button>
            <button class="dl-opt" onclick="dlFmt('${msgId}', 'docx')">Word (.docx)</button>
            <button class="dl-opt" onclick="dlFmt('${msgId}', 'json')">JSON (.json)</button>
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
   DOWNLOAD / EXPORT
   FIXED: Export dropdown now properly toggles open/close.
   - Default: hidden via CSS (display: none)
   - Open: CSS rule .dl-menu.open → display: flex
   - Click toggles the menu
   - Click outside closes all menus
   - Escape key closes all menus
   - No auto-open behavior
════════════════════════════════════════════════════════════════════ */
function toggleDlMenu(msgId, event) {
  if (event) event.stopPropagation();

  const menu = document.getElementById(`dlmenu-${msgId}`);
  if (!menu) return;

  const isOpen = menu.classList.contains('open');

  // Close all menus first
  document.querySelectorAll('.dl-menu').forEach(m => m.classList.remove('open'));

  // Toggle: if it was closed, open it; if it was already open, leave it closed
  if (!isOpen) {
    menu.classList.add('open');
    // Update aria-expanded on the triggering button
    const trigger = event ? event.target.closest('[aria-haspopup]') : null;
    if (trigger) trigger.setAttribute('aria-expanded', 'true');
  } else {
    // Update aria-expanded on the triggering button
    const trigger = event ? event.target.closest('[aria-haspopup]') : null;
    if (trigger) trigger.setAttribute('aria-expanded', 'false');
  }
}

document.addEventListener('click', (e) => {
  // Close all export menus when clicking outside
  document.querySelectorAll('.dl-menu.open').forEach(m => {
    const wrap = m.closest('.dl-wrap');
    if (!wrap || !wrap.contains(e.target)) {
      m.classList.remove('open');
      const trigger = wrap ? wrap.querySelector('[aria-haspopup]') : null;
      if (trigger) trigger.setAttribute('aria-expanded', 'false');
    }
  });
});

// Escape key closes all export menus and modals
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.dl-menu.open').forEach(m => m.classList.remove('open'));
    document.querySelectorAll('.dl-menu.open').forEach(m => {
      m.classList.remove('open');
      const wrap = m.closest('.dl-wrap');
      if (wrap) {
        const trigger = wrap.querySelector('[aria-haspopup]');
        if (trigger) trigger.setAttribute('aria-expanded', 'false');
      }
    });
    // Close viz modal
    if (vizModal && vizModal.style.display !== 'none') closeVizModal();
  }
});

function dlFmt(msgId, fmt) {
  // Close all menus
  document.querySelectorAll('.dl-menu').forEach(m => {
    m.classList.remove('open');
    const wrap = m.closest('.dl-wrap');
    if (wrap) {
      const trigger = wrap.querySelector('[aria-haspopup]');
      if (trigger) trigger.setAttribute('aria-expanded', 'false');
    }
  });

  // Get per-card data from state
  const td = state.tableData[msgId];
  if (!td || !td.columns || !td.allRows) {
    showToast('No data available to export for this result card.', 'error');
    return;
  }

  // Disable button and show spinner
  const menu = document.getElementById(`dlmenu-${msgId}`);
  const btns = menu ? menu.querySelectorAll('.dl-opt') : [];
  btns.forEach(b => { b.disabled = true; });

  doExport(msgId, fmt, td.columns, td.allRows)
    .finally(() => {
      btns.forEach(b => { b.disabled = false; });
    });
}

async function doExport(msgId, fmt, columns, rows) {
  // Check if we have a stored resultId for this card
  const td = state.tableData[msgId];
  const resultId = td && td.resultId;

  try {
    let res;

    if (resultId) {
      // NEW FLOW: Use resultId-based export endpoint
      res = await fetch('/api/export-result', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resultId: resultId, format: fmt }),
      });
    } else {
      // FALLBACK: Use legacy export with columns/rows payload
      res = await fetch(`/export/${fmt}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ columns, rows }),
      });
    }

    if (!res.ok) {
      // Check content type before trying to parse JSON
      const contentType = res.headers.get('content-type') || '';
      let errMsg = `Export failed (HTTP ${res.status})`;
      if (contentType.includes('application/json')) {
        try {
          const err = await res.json();
          errMsg = err.error || errMsg;
        } catch (e) {
          // ignore JSON parse failure
        }
      } else {
        // Server returned HTML or other non-JSON error page
        errMsg = `Export failed (HTTP ${res.status}). The server returned an unexpected response.`;
      }
      throw new Error(errMsg);
    }

    // Verify we got a file (check content-type isn't text/html)
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('text/html')) {
      throw new Error('Server returned HTML instead of a file. The export endpoint may not be available.');
    }

    // Use blob for file download — never response.json() for files
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `query_result.${fmt}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast(`Exported as .${fmt}`, 'success');
  } catch (err) {
    showToast(err.message || 'Export failed.', 'error');
  }
}

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

  // Populate axis dropdowns
  state.vizModal.msgId = msgId;

  const columns = td.columns;
  const { numCols, catCols, dateCols } = classifyColumns(columns, td.allRows);

  // Prevent large pie charts
  const isPie = document.querySelector('#vizChartTypeGrid .active')?.dataset.type === 'pie';
  const xSelect = vizXAxis;
  const ySelect = vizYAxis;

  xSelect.innerHTML = '';
  ySelect.innerHTML = '';

  // X-Axis: categories first, then dates, then numeric
  [...catCols, ...dateCols, ...numCols].forEach(col => {
    xSelect.innerHTML += `<option value="${escHtml(col)}">${escHtml(col)}</option>`;
  });
  // Y-Axis: numeric only
  numCols.forEach(col => {
    ySelect.innerHTML += `<option value="${escHtml(col)}">${escHtml(col)}</option>`;
  });

  // Enable y-axis if we have numeric columns
  ySelect.disabled = numCols.length === 0;

  // Show ai recommendation
  const rec = smartRecommend(numCols, catCols, dateCols, '');
  if (rec.length) {
    vizAIRec.style.display = 'flex';
    vizAIRecText.textContent = `Try: ${rec[0].label}`;
  } else {
    vizAIRec.style.display = 'none';
  }

  // Reset preview
  vizPreviewEmpty.style.display = 'flex';
  vizPreviewChart.style.display = 'none';
  if (state.vizModal.chart) {
    state.vizModal.chart.destroy();
    state.vizModal.chart = null;
  }

  // Show rec chips
  if (rec.length > 1) {
    vizRecChips.style.display = 'flex';
    const chipContainer = document.getElementById('vizRecChips');
    chipContainer.innerHTML = `<span class="viz-rec-chips-label">Suggested:</span>` +
      rec.map((r, i) => `<button class="viz-rec-chip-btn${i === 0 ? ' active' : ''}" data-type="${r.type}" onclick="applyRecChart('${r.type}', this)">${r.label}</button>`).join('');
  } else {
    vizRecChips.style.display = 'none';
  }

  vizModal.style.display = 'flex';
}

function closeVizModal() {
  vizModal.style.display = 'none';
  if (state.vizModal.chart) {
    state.vizModal.chart.destroy();
    state.vizModal.chart = null;
  }
  state.vizModal.msgId = null;
}

if (vizModalClose) vizModalClose.addEventListener('click', closeVizModal);
// Click overlay to close
vizModal.addEventListener('click', (e) => {
  if (e.target === vizModal) closeVizModal();
});

function applyRecChart(chartType, btnEl) {
  // Update active state
  document.querySelectorAll('.viz-rec-chip-btn').forEach(b => b.classList.remove('active'));
  if (btnEl) btnEl.classList.add('active');
  
  // Also update chart type grid
  document.querySelectorAll('#vizChartTypeGrid .viz-chart-type-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.type === chartType);
  });
}

// ── Viz modal: chart type selection ──
document.querySelectorAll('#vizChartTypeGrid .viz-chart-type-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#vizChartTypeGrid .viz-chart-type-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    // Also update rec chips
    document.querySelectorAll('.viz-rec-chip-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.type === btn.dataset.type);
    });
  });
});

// ── Viz modal: generate ──
vizGenerateBtn.addEventListener('click', async () => {
  const msgId = state.vizModal.msgId;
  if (!msgId) return;

  const chartType = document.querySelector('#vizChartTypeGrid .active')?.dataset.type || 'bar';
  const xColumn = vizXAxis.value;
  const yColumn = vizYAxis.value;

  if (yColumn && yColumn === xColumn) {
    showToast('X and Y axes must be different columns.', 'error');
    return;
  }

  try {
    vizGenerateBtn.disabled = true;
    vizGenerateBtn.innerHTML = iconSpinner() + ' Generating...';

    const res = await fetch('/visualize/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: chartType, xColumn, yColumn }),
    });
    const data = await res.json();

    if (!res.ok) {
      showToast(data.error || 'Failed to generate chart.', 'error');
      return;
    }

    vizPreviewEmpty.style.display = 'none';
    vizPreviewChart.style.display = 'block';

    // Destroy previous chart
    if (state.vizModal.chart) {
      state.vizModal.chart.destroy();
      state.vizModal.chart = null;
    }

    state.vizModal.chart = renderChart('vizModalCanvas', data.spec);
    showToast('Chart generated successfully.', 'success');
  } catch (err) {
    showToast('Failed to generate chart.', 'error');
    console.error(err);
  } finally {
    vizGenerateBtn.disabled = false;
    vizGenerateBtn.innerHTML = '<span>Generate Chart</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>';
  }
});

// ── Viz modal: axis change triggers auto-update ──
vizXAxis.addEventListener('change', () => vizGenerateBtn.click());
vizYAxis.addEventListener('change', () => vizGenerateBtn.click());

/* ═══════════════════════════════════════════════════════════════
   TOAST
════════════════════════════════════════════════════════════════ */
function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const icons = {
    success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>',
    error:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    info:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
  };

  toast.innerHTML = `
    ${icons[type] || icons.info}
    <span class="toast-message">${escHtml(message)}</span>
    <button class="toast-close" onclick="dismissToast(this.closest('.toast'))" aria-label="Dismiss"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 6 6 18"/><path d="M6 6l12 12"/></svg></button>
  `;

  container.appendChild(toast);

  // Track toast timer for cleanup
  const timerId = setTimeout(() => dismissToast(toast), duration);
  state._toastTimers[toast] = timerId;
}

function dismissToast(toast) {
  if (!toast) return;
  // Clear timer
  if (state._toastTimers[toast]) {
    clearTimeout(state._toastTimers[toast]);
    delete state._toastTimers[toast];
  }
  // Exit animation
  toast.classList.add('toast-exit');
  setTimeout(() => {
    if (toast.parentNode) toast.parentNode.removeChild(toast);
  }, 200);
}

/* ═══════════════════════════════════════════════════════════════
   SIDEBAR NAVIGATION — toggle visualization sub-menu
════════════════════════════════════════════════════════════════ */
function toggleVizSubMenu() {
  const menu = document.getElementById('vizSubMenu');
  const arrow = document.getElementById('vizSubArrow');
  if (!menu) return;
  menu.classList.toggle('open');
  if (arrow) arrow.style.transform = menu.classList.contains('open') ? 'rotate(180deg)' : '';
}

/* ═══════════════════════════════════════════════════════════════
   SHOW / CLOSE PAGE HELPERS
════════════════════════════════════════════════════════════════ */
function closeAllPages() {
  // Hide all dataset-overview-page sections
  document.querySelectorAll('.dataset-overview-page').forEach(el => {
    el.style.display = 'none';
  });
  // Hide chat-messages if any page was open
  messagesContainer.style.display = 'flex';
  emptyState.style.display = 'none';
  inputBarWrap.classList.add('visible');
}

function closeAutoVisualization() {
  const page = document.getElementById('autoVizPage');
  if (page) page.style.display = 'none';
  messagesContainer.style.display = 'flex';
  emptyState.style.display = messagesContainer.children.length ? 'none' : 'flex';
  inputBarWrap.classList.add('visible');
  document.querySelectorAll('.sidebar-nav-item').forEach(item => item.classList.remove('active'));
  chatInput.focus();
}

function closeCustomChartBuilder() {
  const page = document.getElementById('customChartPage');
  if (page) page.style.display = 'none';
  messagesContainer.style.display = 'flex';
  emptyState.style.display = messagesContainer.children.length ? 'none' : 'flex';
  inputBarWrap.classList.add('visible');
  document.querySelectorAll('.sidebar-nav-item').forEach(item => item.classList.remove('active'));
  chatInput.focus();
}

async function showAutoVisualization() {
  if (!state.uploaded) { showToast('Please upload a dataset first.', 'error'); return; }
  closeAllPages();
  const page = document.getElementById('autoVizPage');
  page.style.display = 'block';
  document.querySelectorAll('.sidebar-nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === 'auto-viz');
  });
  chatMain.scrollTo({ top: 0, behavior: 'smooth' });

  const loading = document.getElementById('autoVizLoading');
  const content = document.getElementById('autoVizContent');
  const error = document.getElementById('autoVizError');
  loading.style.display = 'flex';
  content.style.display = 'none';
  error.style.display = 'none';

  try {
    const res = await fetch('/visualize/auto-recommendations', { method: 'POST' });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || 'Failed to generate recommendations.');
    
    renderAutoVisualizations(data);
    loading.style.display = 'none';
    content.style.display = 'block';
  } catch (err) {
    loading.style.display = 'none';
    error.textContent = err.message || 'Unable to generate auto visualization.';
    error.style.display = 'block';
  }
}

function renderAutoVisualizations(data) {
  const profile = data.columns_profile || {};
  const colTypesHtml = [];
  if (profile.numeric) colTypesHtml.push(`<span class="viz-col-pill viz-col-num">${profile.numeric.length} Numeric</span>`);
  if (profile.categorical) colTypesHtml.push(`<span class="viz-col-pill viz-col-cat">${profile.categorical.length} Categorical</span>`);
  if (profile.date) colTypesHtml.push(`<span class="viz-col-pill viz-col-date">${profile.date.length} Date</span>`);
  document.getElementById('vizColumnProfile').innerHTML = `
    <div class="viz-col-profile-bar">${colTypesHtml.join('')}</div>
    <div class="viz-col-names">${[...(profile.numeric || []), ...(profile.categorical || []), ...(profile.date || [])].join(', ')}</div>
  `;

  const grid = document.getElementById('autoVizGrid');
  grid.innerHTML = (data.recommendations || []).map((rec, idx) => {
    const scoreClass = rec.confidence_score >= 85 ? 'score-high' : rec.confidence_score >= 75 ? 'score-mid' : 'score-low';
    const scoreLabel = rec.confidence_score >= 85 ? `${rec.confidence_score}%` : rec.confidence_score >= 75 ? `${rec.confidence_score}%` : `<75%`;
    
    return `
      <div class="auto-viz-card" data-index="${idx}">
        <div class="auto-viz-card-header">
          <div class="auto-viz-card-title">
            <span class="auto-viz-card-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 13l3-3 3 3 4-6"/></svg></span>
            <div>
              <strong>${escHtml(rec.reason || 'Chart')}</strong>
              <div class="auto-viz-card-sub">${escHtml(rec.chart_type)} · X: ${escHtml(rec.x_column)}${rec.y_column ? ' · Y: ' + escHtml(rec.y_column) : ''}</div>
            </div>
          </div>
          <div class="auto-viz-confidence">
            <span class="confidence-badge ${scoreClass}">${scoreLabel}</span>
          </div>
        </div>
        <div class="auto-viz-card-body">
          <div class="auto-viz-chart-shell ${rec.chart_type === 'pie' || rec.chart_type === 'donut' ? 'is-pie' : ''}">
            <div class="auto-viz-chart-mini">
              <canvas id="auto-viz-canvas-${idx}"></canvas>
            </div>
          </div>
          <div class="auto-viz-card-meta">
            <span>${rec.chart_type.charAt(0).toUpperCase() + rec.chart_type.slice(1)}</span>
            <span>X: ${escHtml(rec.x_column)}${rec.y_column ? ` | Y: ${escHtml(rec.y_column)}` : ''}</span>
          </div>
          ${(rec.insights || []).length ? `<ul class="auto-viz-insights">${rec.insights.slice(0, 3).map(i => `<li>${escHtml(i)}</li>`).join('')}</ul>` : ''}
          <div class="auto-viz-card-actions">
            <button class="toolbar-btn toolbar-btn-primary" onclick="expandAutoViz(${idx})" style="flex:1;justify-content:center;">View Full Chart</button>
          </div>
        </div>
      </div>`;
  }).join('');

  // Render mini charts after DOM update
  requestAnimationFrame(() => {
    (data.recommendations || []).forEach((rec, idx) => {
      const canvas = document.getElementById(`auto-viz-canvas-${idx}`);
      if (canvas && rec.spec) {
        try {
          renderChart(`auto-viz-canvas-${idx}`, rec.spec);
        } catch (e) {
          console.warn('Mini chart render failed:', e);
        }
      }
    });
  });
}

// Store expanded auto-viz data for the detail modal
window._autoVizData = null;

function expandAutoViz(index) {
  const grid = document.getElementById('autoVizGrid');
  const card = grid?.children[index];
  if (!card) return;

  // Open the viz modal with pre-filled data
  const rec = window._expandedRecs?.[index];
  if (rec) {
    openVizModal('master');
    // Set chart type
    document.querySelectorAll('#vizChartTypeGrid .viz-chart-type-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.type === rec.chart_type);
    });
    // Set axes
    const xSelect = vizXAxis;
    const ySelect = vizYAxis;
    if (rec.x_column && [...xSelect.options].some(o => o.value === rec.x_column)) xSelect.value = rec.x_column;
    if (rec.y_column && [...ySelect.options].some(o => o.value === rec.y_column)) ySelect.value = rec.y_column;
    // Generate
    vizGenerateBtn.click();
  }
}

function showCustomChartBuilder() {
  if (!state.uploaded) { showToast('Please upload a dataset first.', 'error'); return; }
  closeAllPages();
  const page = document.getElementById('customChartPage');
  page.style.display = 'block';
  document.querySelectorAll('.sidebar-nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === 'custom-chart');
  });
  chatMain.scrollTo({ top: 0, behavior: 'smooth' });
  populateCustomChartBuilder();
}

function resetCustomChartBuilder() {
  const canvas = document.getElementById('customChartCanvas');
  if (canvas && state.chartMap['custom']) {
    state.chartMap['custom'].destroy();
    delete state.chartMap['custom'];
  }
  document.getElementById('customChartEmpty').style.display = 'flex';
  document.getElementById('customChartInsights').style.display = 'none';
  document.getElementById('customChartWarning').style.display = 'none';
}

function populateCustomChartBuilder() {
  const xSelect = document.getElementById('customXAxis');
  const ySelect = document.getElementById('customYAxis');
  xSelect.innerHTML = '';
  ySelect.innerHTML = '';

  const columns = state.dataset.columns || [];
  const { numCols, catCols, dateCols } = classifyColumnsFromSchema(columns);

  [...catCols, ...dateCols, ...numCols].forEach(col => {
    xSelect.innerHTML += `<option value="${escHtml(col)}">${escHtml(col)}</option>`;
  });
  numCols.forEach(col => {
    ySelect.innerHTML += `<option value="${escHtml(col)}">${escHtml(col)}</option>`;
  });
  ySelect.disabled = numCols.length === 0;
}

// Custom chart type selection
document.querySelectorAll('#customChartTypeGrid .viz-chart-type-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#customChartTypeGrid .viz-chart-type-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    // Show note for pie/donut (y-axis is effectively count)
    const note = document.getElementById('customControlsNote');
    if (btn.dataset.type === 'pie' || btn.dataset.type === 'donut') {
      note.style.display = 'block';
      note.textContent = 'Pie/Donut charts use count aggregation. Y-axis selection will be used as values.';
    } else if (btn.dataset.type === 'histogram') {
      note.style.display = 'block';
      note.textContent = 'Histogram shows value distribution. X-axis becomes the value column.';
    } else {
      note.style.display = 'none';
    }
  });
});

// Custom chart generate
document.getElementById('customGenerateBtn').addEventListener('click', async () => {
  if (!state.uploaded) { showToast('Please upload a dataset first.', 'error'); return; }

  const chartType = document.querySelector('#customChartTypeGrid .active')?.dataset.type || 'bar';
  const xColumn = document.getElementById('customXAxis').value;
  const yColumn = document.getElementById('customYAxis').value;
  const aggregation = document.querySelector('#customAggRow .active')?.dataset.agg || 'sum';

  const warning = document.getElementById('customChartWarning');

  // Validate
  if (['pie', 'donut'].includes(chartType)) {
    // Y-axis not strictly needed for pie
  } else if (chartType === 'histogram') {
    // X-axis is the value column
  } else if (!xColumn || !yColumn) {
    warning.style.display = 'block';
    warning.textContent = 'Please select both X and Y axes.';
    setTimeout(() => { warning.style.display = 'none'; }, 3000);
    return;
  }

  if (xColumn === yColumn) {
    warning.style.display = 'block';
    warning.textContent = 'X and Y axes must be different columns.';
    setTimeout(() => { warning.style.display = 'none'; }, 3000);
    return;
  }

  const genBtn = document.getElementById('customGenerateBtn');
  genBtn.disabled = true;
  genBtn.innerHTML = iconSpinner() + ' Generating...';

  try {
    const res = await fetch('/visualize/custom-render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chart_type: chartType, xColumn, yColumn, aggregation }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to render chart.');

    // Hide empty state, show chart
    document.getElementById('customChartEmpty').style.display = 'none';
    const canvas = document.getElementById('customChartCanvas');

    // Destroy previous
    if (state.chartMap['custom']) {
      state.chartMap['custom'].destroy();
    }
    state.chartMap['custom'] = renderChart('customChartCanvas', data.spec);

    // Show insights
    const insightsPanel = document.getElementById('customChartInsights');
    const insightsBody = document.getElementById('customChartInsightsBody');
    if (data.insights && data.insights.length) {
      insightsBody.innerHTML = data.insights.map(i => `<div class="chart-insight-item">${i}</div>`).join('');
      insightsPanel.style.display = 'block';
    } else {
      insightsPanel.style.display = 'none';
    }
  } catch (err) {
    warning.style.display = 'block';
    warning.textContent = err.message || 'Failed to render chart.';
    setTimeout(() => { warning.style.display = 'none'; }, 4000);
  } finally {
    genBtn.disabled = false;
    genBtn.innerHTML = '<i class="ti ti-chart-bar"></i> Build Chart';
  }
});

// Custom chart export
async function exportCustomChart(fmt, btnEl) {
  const canvas = document.getElementById('customChartCanvas');
  if (!canvas || !state.chartMap['custom']) {
    showToast('Generate a chart first before exporting.', 'info');
    return;
  }

  const imageData = canvas.toDataURL('image/png');
  const chartType = document.querySelector('#customChartTypeGrid .active')?.dataset.type || 'bar';
  const xColumn = document.getElementById('customXAxis').value;
  const yColumn = document.getElementById('customYAxis').value;

  // Get labels and data from chart
  let chartLabels = [];
  let chartData = [];
  try {
    const chart = state.chartMap['custom'];
    if (chart && chart.data) {
      if (chart.data.labels) chartLabels = chart.data.labels;
      if (chart.data.datasets && chart.data.datasets[0]) chartData = chart.data.datasets[0].data;
    }
  } catch (e) {}

  btnEl.disabled = true;
  btnEl.innerHTML = iconSpinner();
  try {
    const res = await fetch(`/visualize/export-chart/${fmt}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: `Custom Chart - ${chartType}`,
        x_label: xColumn,
        y_label: yColumn,
        series_label: yColumn,
        labels: chartLabels,
        data: chartData,
        insights: [],
        image: imageData,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Export failed.');
    }

    // Download returned blob
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `custom_chart.${fmt}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast(`Chart exported as .${fmt}`, 'success');
  } catch (err) {
    showToast(err.message || 'Export failed.', 'error');
  } finally {
    btnEl.disabled = false;
    btnEl.innerHTML = `<i class="ti ti-${fmt === 'png' ? 'photo' : fmt === 'pdf' ? 'file-text' : fmt === 'xlsx' ? 'table' : 'file-word'}"></i> ${fmt.toUpperCase()}`;
  }
}

/* ═══════════════════════════════════════════════════════════════
   SWITCH VIZ TYPE (inline)
════════════════════════════════════════════════════════════════ */
function switchVizType(msgId, newType, btnEl) {
  const container = document.getElementById(`chart-container-${msgId}`);
  if (!container) return;

  // Update active state
  const switcher = document.getElementById(`switcher-${msgId}`);
  if (switcher) {
    switcher.querySelectorAll('.viz-type-btn').forEach(b => b.classList.remove('active'));
    btnEl.classList.add('active');
  }

  const allTypes = JSON.parse(container.dataset.allTypes || '[]');
  const xCol = container.dataset.xCol;
  const yCol = container.dataset.yCol;

  // Fetch new spec
  fetch('/visualize/render', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: newType, xColumn: xCol, yColumn: yCol }),
  })
    .then(r => r.json())
    .then(data => {
      if (data.spec) {
        if (state.chartMap[msgId]) {
          state.chartMap[msgId].destroy();
        }
        state.chartMap[msgId] = renderChart('chart-' + msgId, data.spec);
      }
    })
    .catch(console.error);
}

/* ═══════════════════════════════════════════════════════════════
   CHART RENDERING UTILITIES
════════════════════════════════════════════════════════════════ */
function _chartLabel(type) {
  const labels = {
    bar: 'Bar', line: 'Line', area: 'Area', pie: 'Pie',
    donut: 'Donut', scatter: 'Scatter', histogram: 'Histogram'
  };
  return labels[type] || type;
}

function _chartIconSvg(type) {
  const icons = {
    bar: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="14" width="4" height="6"/><rect x="10" y="8" width="4" height="12"/><rect x="16" y="4" width="4" height="16"/></svg>',
    line: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 8 12 12 15 16 7 20 11"/></svg>',
    area: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 18l4-6 4 4 8-8"/><path d="M4 18l4-6 4 4 8-8"/><path d="M4 22h16"/></svg>',
    pie: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 0 1 10 10"/><path d="M12 2v10"/><path d="M12 22A10 10 0 1 1 12 2"/></svg>',
    donut: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 0 1 10 10"/><path d="M12 2v10"/><path d="M12 22A10 10 0 1 1 12 2"/><circle cx="12" cy="12" r="5"/></svg>',
    scatter: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="8" cy="8" r="2"/><circle cx="16" cy="6" r="2"/><circle cx="12" cy="14" r="2"/><circle cx="18" cy="16" r="2"/><circle cx="6" cy="18" r="2"/></svg>',
    histogram: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="12" width="3" height="8"/><rect x="9" y="8" width="3" height="12"/><rect x="14" y="4" width="3" height="16"/><rect x="19" y="10" width="3" height="10"/></svg>',
  };
  return icons[type] || '';
}

function renderChart(canvasId, spec) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;

  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  // Destroy existing chart on this canvas
  const existing = Chart.getChart(canvasId);
  if (existing) existing.destroy();

  if (!spec || !spec.type) return null;

  const config = {
    type: spec.type,
    data: {
      labels: spec.labels || [],
      datasets: (spec.series || []).map((s, i) => ({
        label: s.label || '',
        data: s.data || [],
        backgroundColor: s.backgroundColor || spec.backgroundColor || '#2563EB',
        borderColor: s.borderColor || spec.borderColor || '#2563EB',
        borderWidth: s.borderWidth || spec.borderWidth || 2,
        tension: s.tension || 0,
        fill: s.fill !== undefined ? s.fill : spec.type === 'line',
        pointRadius: s.pointRadius || (spec.type === 'scatter' ? 4 : 3),
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      interaction: {
        intersect: false,
        mode: 'index',
      },
      plugins: {
        legend: {
          display: spec.type === 'pie' || spec.type === 'donut' || (spec.series && spec.series.length > 1),
          position: 'bottom',
          labels: { boxWidth: 12, font: { size: 11 } },
        },
        tooltip: {
          backgroundColor: 'rgba(0,0,0,0.8)',
          titleFont: { size: 12 },
          bodyFont: { size: 12 },
          padding: 8,
        },
      },
      scales: spec.type !== 'pie' && spec.type !== 'donut' ? {
        x: {
          ticks: { font: { size: 10 } },
          grid: { color: 'rgba(0,0,0,0.06)' },
        },
        y: {
          beginAtZero: true,
          ticks: { font: { size: 10 } },
          grid: { color: 'rgba(0,0,0,0.06)' },
        },
      } : {},
    },
  };

  try {
    return new Chart(ctx, config);
  } catch (e) {
    console.error('Chart render error:', e);
    return null;
  }
}

function renderChartInMsg(msgId, spec, canvasId) {
  requestAnimationFrame(() => {
    if (state.chartMap[msgId]) {
      state.chartMap[msgId].destroy();
    }
    state.chartMap[msgId] = renderChart(canvasId, spec);
  });
}

/* ═══════════════════════════════════════════════════════════════
   TABLE PAGINATION
════════════════════════════════════════════════════════════════ */
function changePage(msgId, delta) {
  const td = state.tableData[msgId];
  if (!td) return;

  const totalPages = Math.ceil(td.allRows.length / PAGE_SIZE);
  const newPage = Math.max(0, Math.min(totalPages - 1, td.page + delta));
  if (newPage === td.page) return;
  td.page = newPage;

  const start = newPage * PAGE_SIZE;
  const rows = td.allRows.slice(start, start + PAGE_SIZE);

  const tbody = document.querySelector(`#table-${msgId} tbody`);
  if (tbody) tbody.innerHTML = buildTableRows(td.columns, rows);

  const pageInfo = document.getElementById(`page-info-${msgId}`);
  if (pageInfo) pageInfo.textContent = `Page ${newPage + 1} of ${totalPages}`;

  const prevBtn = document.getElementById(`prev-${msgId}`);
  const nextBtn = document.getElementById(`next-${msgId}`);
  if (prevBtn) prevBtn.disabled = newPage === 0;
  if (nextBtn) nextBtn.disabled = newPage >= totalPages - 1;
}

function buildTableRows(columns, rows) {
  return rows.map(row => {
    const cells = columns.map(col => {
      let val = row[col];
      const isMissing = val === null || val === undefined || val === '' || (typeof val === 'number' && isNaN(val));
      const display = isMissing ? '<span class="cell-missing-indicator">[EMPTY]</span>' : escHtml(String(val));
      return `<td class="${isMissing ? 'cell-missing' : ''}">${display}</td>`;
    });
    return `<tr>${cells.join('')}</tr>`;
  }).join('');
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    chatMain.scrollTop = chatMain.scrollHeight;
  });
}

/* ═══════════════════════════════════════════════════════════════
   ICON HELPERS
════════════════════════════════════════════════════════════════ */
function iconSpinner() {
  return '<svg class="spinner-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>';
}

function iconBot() {
  return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 13l3-3 3 3 4-6"/></svg>';
}

function iconX() {
  return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
}

function iconNo() {
  return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M16 16l-8-8"/><path d="M8 16l8-8"/></svg>';
}

/* ═══════════════════════════════════════════════════════════════
   ESCAPE HTML
════════════════════════════════════════════════════════════════ */
function escHtml(str) {
  if (str === null || str === undefined) return '';
  const d = document.createElement('div');
  d.textContent = String(str);
  return d.innerHTML;
}

/* ═══════════════════════════════════════════════════════════════
   BUILD SPEC FROM DATA
════════════════════════════════════════════════════════════════ */
function buildSpecFromData(chartType, columns, rows, numCols, catCols) {
  // Simplified spec builder for inline charts
  const spec = { type: chartType, series: [] };

  if (chartType === 'histogram') {
    const col = numCols[0] || columns[0];
    const values = rows.map(r => Number(r[col])).filter(v => !isNaN(v));
    const bins = 10;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const binWidth = (max - min) / bins || 1;
    const histogram = Array(bins).fill(0);
    const labels = [];
    for (let i = 0; i < bins; i++) {
      const start = min + i * binWidth;
      const end = start + binWidth;
      labels.push(`${start.toFixed(1)}-${end.toFixed(1)}`);
    }
    values.forEach(v => {
      const idx = Math.min(Math.floor((v - min) / binWidth), bins - 1);
      histogram[idx]++;
    });
    spec.labels = labels;
    spec.series.push({ label: col, data: histogram, backgroundColor: '#2563EB' });
    spec.title = `Distribution of ${col}`;
    return spec;
  }

  if (chartType === 'scatter') {
    const xCol = numCols[0] || columns[0];
    const yCol = numCols[1] || columns[1] || numCols[0];
    const data = rows.map(r => ({ x: Number(r[xCol]), y: Number(r[yCol]) })).filter(p => !isNaN(p.x) && !isNaN(p.y));
    spec.labels = data.map((_, i) => i);
    spec.series.push({ label: `${yCol} vs ${xCol}`, data: data.map(p => p.y), backgroundColor: '#2563EB' });
    spec.title = `${yCol} vs ${xCol}`;
    return spec;
  }

  const catCol = catCols[0] || columns[0];
  const numCol = numCols[0] || (columns[1] || columns[0]);

  if (chartType === 'pie' || chartType === 'donut') {
    const agg = {};
    rows.forEach(r => {
      const key = r[catCol] ?? 'Unknown';
      const val = Number(r[numCol]) || 0;
      agg[key] = (agg[key] || 0) + val;
    });
    const entries = Object.entries(agg).sort((a, b) => b[1] - a[1]).slice(0, 10);
    spec.labels = entries.map(e => String(e[0]));
    spec.series.push({ label: numCol, data: entries.map(e => e[1]), backgroundColor: generateColors(entries.length) });
    spec.title = `${numCol} by ${catCol}`;
    return spec;
  }

  // Bar / Line / Area
  const agg = {};
  rows.forEach(r => {
    const key = r[catCol] ?? 'Unknown';
    const val = Number(r[numCol]) || 0;
    agg[key] = (agg[key] || 0) + val;
  });
  const entries = Object.entries(agg).sort((a, b) => b[1] - a[1]).slice(0, 15);
  spec.labels = entries.map(e => String(e[0]));
  spec.series.push({ label: numCol, data: entries.map(e => e[1]), backgroundColor: '#2563EB' });
  spec.title = `${numCol} by ${catCol}`;

  return spec;
}

/* ═══════════════════════════════════════════════════════════════
   GENERATE COLOURS
════════════════════════════════════════════════════════════════ */
function generateColors(n) {
  const palette = ['#2563EB','#10B981','#F59E0B','#EF4444','#8B5CF6','#EC4899','#06B6D4','#84CC16','#F97316','#6366F1','#14B8A6','#D946EF','#0EA5E9','#22C55E','#EAB308'];
  return Array.from({length: n}, (_, i) => palette[i % palette.length]);
}

/* ═══════════════════════════════════════════════════════════════
   MARKDOWN PARSER (lightweight)
════════════════════════════════════════════════════════════════ */
function parseMarkdown(text) {
  if (!text) return '';
  let html = escHtml(text);
  // Code blocks (``` ... ```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Italic
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  // Links [text](url)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // Tip blocks
  html = html.replace(/^>\s*\[!TIP\]\s*$/gim, '<div class="md-tip">');
  html = html.replace(/^>\s*\[!WARNING\]\s*$/gim, '<div class="md-warning">');
  // Blockquotes
  html = html.replace(/^>\s(.+)$/gm, '<blockquote>$1</blockquote>');
  // Headers
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  // Unordered lists
  html = html.replace(/^\* (.+)$/gm, '<li>$1</li>');
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
  // Ordered lists
  html = html.replace(/^\d+\.\s(.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ol>$&</ol>');
  // Horizontal rules
  html = html.replace(/^---$/gm, '<hr>');
  // Line breaks
  const lines = html.split('\n');
  let inTable = false;
  let tableHtml = '';
  const outLines = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
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

/* ═══════════════════════════════════════════════════════════════
   REPLACE MISSING VALUES — Feature
════════════════════════════════════════════════════════════════ */

// ── Update sidebar badge ──
async function updateReplaceMissingBadge() {
  const badge = document.getElementById('replaceMissingBadge');
  if (!badge || !state.uploaded) {
    if (badge) { badge.style.display = 'none'; badge.textContent = '0'; }
    return;
  }
  try {
    const res = await fetch('/missing-values');
    const data = await res.json();
    if (data.success) {
      const total = data.total_missing || 0;
      badge.textContent = total;
      badge.style.display = total > 0 ? 'inline-flex' : 'none';
    }
  } catch (e) {
    badge.style.display = 'none';
  }
}

// ── Show Replace Missing page ──
async function showReplaceMissingPage() {
  if (!state.uploaded) {
    showToast('Please upload a dataset first.', 'error');
    return;
  }

  closeAllPages();
  const page = document.getElementById('replaceMissingPage');
  page.style.display = 'block';

  // Update active nav
  document.querySelectorAll('.sidebar-nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === 'replace-missing');
  });

  chatMain.scrollTo({ top: 0, behavior: 'smooth' });

  // Reset state
  state.rmSelectedColumn = null;
  state.rmSelectedMethod = null;
  state.rmSortAsc = false;

  // Show loading
  document.getElementById('replaceMissingLoading').style.display = 'flex';
  document.getElementById('replaceMissingContent').style.display = 'none';
  document.getElementById('replaceMissingError').style.display = 'none';
  document.getElementById('replaceMissingQualitySummary').style.display = 'none';

  // Hide detail panel
  document.getElementById('rmDetailPanel').style.display = 'none';
  document.getElementById('rmPreviewSection').style.display = 'none';

  try {
    const res = await fetch('/missing-values');
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Failed to scan missing values.');

    state.rmColumns = data.missing_columns || [];
    state.rmBeforeTotal = data.total_missing || 0;
    state.rmSortAsc = false;

    // Update quality summary
    const qualitySummary = document.getElementById('replaceMissingQualitySummary');
    qualitySummary.style.display = 'flex';
    document.getElementById('rmQualityBefore').textContent = data.total_missing || 0;
    document.getElementById('rmQualityAfter').textContent = data.total_missing || 0;
    document.getElementById('rmQualityResolved').textContent = '0';

    // Render column list
    renderReplaceMissingColumns();

    // Update action bar
    document.getElementById('rmUndoBtn').disabled = true;
    document.getElementById('rmExportBtn').disabled = true;

    document.getElementById('replaceMissingLoading').style.display = 'none';
    document.getElementById('replaceMissingContent').style.display = 'block';
  } catch (err) {
    document.getElementById('replaceMissingLoading').style.display = 'none';
    document.getElementById('replaceMissingError').style.display = 'block';
    document.getElementById('replaceMissingError').textContent = err.message || 'Failed to load missing values.';
  }
}

// ── Render column list ──
function renderReplaceMissingColumns() {
  const list = document.getElementById('rmColumnList');
  const search = (document.getElementById('rmSearchInput').value || '').toLowerCase();

  let columns = state.rmColumns;

  // Filter by search
  if (search) {
    columns = columns.filter(c => c.column_name.toLowerCase().includes(search));
  }

  // Sort by missing count
  if (state.rmSortAsc) {
    columns = [...columns].sort((a, b) => a.missing_count - b.missing_count);
  } else {
    columns = [...columns].sort((a, b) => b.missing_count - a.missing_count);
  }

  if (columns.length === 0) {
    list.innerHTML = '<div class="overview-muted" style="padding:20px;text-align:center;">No columns with missing values found.</div>';
    return;
  }

  list.innerHTML = columns.map(col => {
    const isActive = state.rmSelectedColumn === col.column_name;
    const typeIcon = col.data_type === 'Numeric' ? 'ti-numbers' : col.data_type === 'Date' ? 'ti-calendar' : 'ti-tags';
    return `
      <div class="rm-column-item ${isActive ? 'active' : ''}" onclick="selectReplaceColumn('${escHtml(col.column_name)}')">
        <span class="rm-column-item-icon"><i class="ti ${typeIcon}"></i></span>
        <div class="rm-column-item-info">
          <div class="rm-column-item-name">${escHtml(col.column_name)}</div>
          <div class="rm-column-item-meta">${escHtml(col.data_type)} · ${col.total_rows.toLocaleString()} rows</div>
        </div>
        <span class="rm-column-item-badge">${col.missing_count} Missing</span>
      </div>`;
  }).join('');
}

// ── Filter columns ──
function filterReplaceMissingColumns() {
  renderReplaceMissingColumns();
}

// ── Toggle sort ──
function toggleReplaceMissingSort() {
  state.rmSortAsc = !state.rmSortAsc;
  const btn = document.getElementById('rmSortBtn');
  btn.innerHTML = state.rmSortAsc
    ? '<i class="ti ti-sort-descending"></i> Sort'
    : '<i class="ti ti-sort-ascending"></i> Sort';
  renderReplaceMissingColumns();
}

// ── Select a column ──
async function selectReplaceColumn(columnName) {
  state.rmSelectedColumn = columnName;
  state.rmSelectedMethod = null;
  renderReplaceMissingColumns();

  const panel = document.getElementById('rmDetailPanel');
  panel.style.display = 'block';
  document.getElementById('rmPreviewSection').style.display = 'none';

  // Show loading in detail panel
  document.getElementById('rmDetailColName').textContent = columnName;
  document.getElementById('rmDetailDataType').textContent = 'Loading...';
  document.getElementById('rmDetailTotalRows').textContent = 'Total: —';
  document.getElementById('rmDetailMissingCount').textContent = 'Missing: —';

  // Hide replace options initially
  document.getElementById('rmReplaceOptionsNumeric').style.display = 'none';
  document.getElementById('rmReplaceOptionsCategorical').style.display = 'none';
  document.getElementById('rmPreviewBtn').disabled = true;

  try {
    const res = await fetch(`/missing-values/${encodeURIComponent(columnName)}`);
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Failed to load column details.');

    // Update header
    document.getElementById('rmDetailColName').textContent = data.column_name;
    document.getElementById('rmDetailDataType').textContent = data.data_type;
    document.getElementById('rmDetailTotalRows').textContent = `Total: ${data.total_rows.toLocaleString()}`;
    document.getElementById('rmDetailMissingCount').textContent = `Missing: ${data.missing_count}`;

    // Render values preview
    const scroll = document.querySelector('.rm-values-scroll');
    scroll.innerHTML = (data.preview_values || []).map(v => {
      if (v.is_missing) {
        return `<span class="rm-value-chip rm-value-empty">[EMPTY]</span>`;
      }
      return `<span class="rm-value-chip">${escHtml(v.value)}</span>`;
    }).join('');

    // Show appropriate replace options
    if (data.data_type === 'Numeric') {
      document.getElementById('rmReplaceOptionsNumeric').style.display = 'block';
      document.getElementById('rmReplaceOptionsCategorical').style.display = 'none';
      const stats = data.stats || {};
      document.getElementById('rmMeanValue').textContent = stats.mean !== undefined ? stats.mean : '—';
      document.getElementById('rmMedianValue').textContent = stats.median !== undefined ? stats.median : '—';
      document.getElementById('rmModeValue').textContent = stats.mode !== undefined ? stats.mode : '—';
    } else {
      document.getElementById('rmReplaceOptionsNumeric').style.display = 'none';
      document.getElementById('rmReplaceOptionsCategorical').style.display = 'block';
      const stats = data.stats || {};
      document.getElementById('rmCatModeValue').textContent = stats.mode !== undefined ? `(${escHtml(stats.mode)})` : '—';
    }

    // Reset method selection
    document.querySelectorAll('.rm-option-btn').forEach(b => b.classList.remove('selected'));
    document.getElementById('rmPreviewBtn').disabled = true;

  } catch (err) {
    showToast(err.message || 'Failed to load column details.', 'error');
  }
}

// ── Select replace method ──
function selectReplaceMethod(method) {
  state.rmSelectedMethod = method;

  // Update visual selection
  document.querySelectorAll('.rm-option-btn').forEach(b => b.classList.remove('selected'));
  document.querySelectorAll(`.rm-option-btn[data-method="${method}"]`).forEach(b => b.classList.add('selected'));

  // Show/hide custom input
  document.getElementById('rmCustomInputWrap').style.display = method === 'custom' ? 'block' : 'none';
  document.getElementById('rmCustomInputWrap2').style.display = method === 'custom' ? 'block' : 'none';

  // Enable Preview button if method is selected
  document.getElementById('rmPreviewBtn').disabled = false;
}

// ── Preview replace values ──
async function previewReplaceValues() {
  if (!state.rmSelectedColumn || !state.rmSelectedMethod) {
    showToast('Please select a column and replacement method.', 'error');
    return;
  }

  const column = state.rmSelectedColumn;
  const method = state.rmSelectedMethod;

  // Get value
  let value = null;
  if (method === 'custom') {
    value = document.getElementById('rmCustomInput').value || document.getElementById('rmCustomInput2').value || '';
    if (!value.trim()) {
      showToast('Please enter a replacement value.', 'error');
      return;
    }
  }

  try {
    const res = await fetch('/missing-values/replace', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        column,
        method,
        value: method === 'custom' ? value : undefined,
        preview: true,
      }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Preview failed.');

    // Render preview
    document.getElementById('rmPreviewSection').style.display = 'block';
    const table = document.getElementById('rmPreviewTable');
    table.innerHTML = (data.preview_data || []).map(p => `
      <div class="rm-preview-row">
        <span class="rm-preview-old">${escHtml(p.old)}</span>
        <span class="rm-preview-arrow">→</span>
        <span class="rm-preview-new">${escHtml(p.new)}</span>
      </div>
    `).join('');

    document.getElementById('rmPreviewInfo').textContent = `Affected Rows: ${data.affected_rows}`;

    // Store data for confirmation
    window._rmPreviewData = data;

  } catch (err) {
    showToast(err.message || 'Preview failed.', 'error');
  }
}

// ── Confirm replace values ──
async function confirmReplaceValues() {
  const previewData = window._rmPreviewData;
  if (!previewData) return;

  const column = previewData.column;
  const method = previewData.method;
  let value = previewData.replacement;

  if (method === 'custom') {
    value = document.getElementById('rmCustomInput').value || document.getElementById('rmCustomInput2').value || '';
  }

  const confirmBtn = document.getElementById('rmConfirmBtn');
  confirmBtn.disabled = true;
  confirmBtn.innerHTML = iconSpinner() + ' Saving...';

  try {
    const res = await fetch('/missing-values/replace', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        column,
        method,
        value: method === 'custom' ? value : undefined,
        preview: false,
      }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Failed to save changes.');

    // Update state
    state.rmColumns = data.updated_missing?.missing_columns || [];
    const newTotal = data.updated_missing?.total_missing || 0;

    // Update quality summary
    document.getElementById('rmQualityAfter').textContent = newTotal;
    document.getElementById('rmQualityResolved').textContent = state.rmBeforeTotal - newTotal;

    // Update missing count in detail panel
    document.getElementById('rmDetailMissingCount').textContent = `Missing: ${data.updated_missing?.missing_columns?.find(c => c.column_name === column)?.missing_count || 0}`;

    // Re-render column list
    renderReplaceMissingColumns();

    // Enable undo
    document.getElementById('rmUndoBtn').disabled = false;
    document.getElementById('rmExportBtn').disabled = false;

    // Update sidebar badge
    updateReplaceMissingBadge();

    // Update sidebar data quality card
    const sbMissing = document.getElementById('sbMissing');
    if (sbMissing) {
      const totalPct = data.updated_missing?.total_rows ? ((newTotal / data.updated_missing.total_rows) * 100).toFixed(1) : '0';
      sbMissing.textContent = newTotal > 0 ? `${newTotal.toLocaleString()} (${totalPct}%)` : '0';
    }

    // Hide preview
    document.getElementById('rmPreviewSection').style.display = 'none';
    window._rmPreviewData = null;

    showToast(data.message || `${data.affected_rows} missing values in ${column} were successfully replaced.`, 'success');
  } catch (err) {
    showToast(err.message || 'Failed to save changes.', 'error');
  } finally {
    confirmBtn.disabled = false;
    confirmBtn.innerHTML = '<i class="ti ti-check"></i> Confirm';
  }
}

// ── Cancel preview ──
function cancelReplacePreview() {
  document.getElementById('rmPreviewSection').style.display = 'none';
  window._rmPreviewData = null;
}

// ── Undo last replace ──
async function undoLastReplace() {
  if (!state.rmSelectedColumn) {
    showToast('Please select a column to undo.', 'error');
    return;
  }

  const undoBtn = document.getElementById('rmUndoBtn');
  undoBtn.disabled = true;
  undoBtn.innerHTML = iconSpinner() + ' Undoing...';

  try {
    const res = await fetch('/missing-values/undo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ column: state.rmSelectedColumn }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Failed to undo.');

    // Update state
    state.rmColumns = data.updated_missing?.missing_columns || [];
    const newTotal = data.updated_missing?.total_missing || 0;

    // Update quality summary
    document.getElementById('rmQualityAfter').textContent = newTotal;
    document.getElementById('rmQualityResolved').textContent = state.rmBeforeTotal - newTotal;

    // Re-render
    renderReplaceMissingColumns();

    // Update sidebar
    updateReplaceMissingBadge();
    const sbMissing = document.getElementById('sbMissing');
    if (sbMissing) {
      const totalPct = data.updated_missing?.total_rows ? ((newTotal / data.updated_missing.total_rows) * 100).toFixed(1) : '0';
      sbMissing.textContent = newTotal > 0 ? `${newTotal.toLocaleString()} (${totalPct}%)` : '0';
    }

    // Refresh detail if same column
    if (state.rmSelectedColumn) {
      await selectReplaceColumn(state.rmSelectedColumn);
    }

    undoBtn.disabled = true;
    showToast(data.message || 'Undo successful.', 'success');
  } catch (err) {
    showToast(err.message || 'Failed to undo.', 'error');
    undoBtn.disabled = false;
  } finally {
    undoBtn.innerHTML = '<i class="ti ti-arrow-back-up"></i> Undo Last Change';
  }
}

// ── Toggle Export menu ──
function toggleExportMenu() {
  const menu = document.getElementById('rmExportMenu');
  menu.classList.toggle('open');
}

// Close export menu on click outside
document.addEventListener('click', (e) => {
  const menu = document.getElementById('rmExportMenu');
  const btn = document.getElementById('rmExportBtn');
  if (menu && menu.classList.contains('open') && !e.target.closest('.rm-export-dropdown')) {
    menu.classList.remove('open');
  }
});

// ── Export cleaned dataset ──
function exportCleanedDataset(fmt) {
  const menu = document.getElementById('rmExportMenu');
  menu.classList.remove('open');
  window.location.href = `/export-cleaned-dataset/${fmt}`;
  showToast('Cleaned dataset exported successfully.', 'success');
}

// ── Close Replace Missing page ──
function closeReplaceMissingPage() {
  const page = document.getElementById('replaceMissingPage');
  if (page) page.style.display = 'none';
  messagesContainer.style.display = 'flex';
  emptyState.style.display = messagesContainer.children.length ? 'none' : 'flex';
  inputBarWrap.classList.add('visible');
  document.querySelectorAll('.sidebar-nav-item').forEach(item => item.classList.remove('active'));
  chatInput.focus();
}

// ── Initialize badge on upload ──
// Hook into dataset loading
document.addEventListener('DOMContentLoaded', () => {
  // Check if dataset is already loaded on page load
  if (state.uploaded) {
    updateReplaceMissingBadge();
  }
});

// Also handle data table row rendering with missing value highlighting
// Override buildTableRows to show missing indicators
const _origBuildTableRows = buildTableRows;
buildTableRows = function(columns, rows) {
  return rows.map(row => {
    const cells = columns.map(col => {
      let val = row[col];
      const isMissing = val === null || val === undefined || val === '' || (typeof val === 'number' && isNaN(val));
      const display = isMissing ? '<span class="cell-missing-indicator">[EMPTY]</span>' : escHtml(String(val));
      return `<td class="${isMissing ? 'cell-missing' : ''}">${display}</td>`;
    });
    return `<tr>${cells.join('')}</tr>`;
  }).join('');
};