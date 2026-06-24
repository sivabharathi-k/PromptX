/* ═══════════════════════════════════════════════════════════════
   STATE
════════════════════════════════════════════════════════════════ */
const state = {
  uploaded:    false,
  querying:    false,
  dataset:     { name: '', rows: 0, columns: [] },
  masterSchema: {},   // { column_name: "NUM"|"TEXT"|"DATE" } - single source of truth
  tableData:   {},   // msgId -> { columns, allRows, page, sql }
  sidebarOpen: true,
  leftSidebarOpen: true,
  lastSQL:     '',
  overview:    null,
  _toastTimers: {}, // track toast auto-dismiss timers
  // Replace missing values state
  rmColumns: [],
  rmSelectedColumn: null,
  rmSelectedMethod: null,
  rmSortAsc: false,
  rmBeforeTotal: 0,
  // Dashboard state
  dashboardFilters: {},
  dashboardPage: 1,
  dashboardSearch: '',
  dashboardSortColumn: null,
  dashboardSortDir: 'ASC',
  dashboardTableTotalCount: 0,
  tempWorkbookFilename: '',
  tempWorkbookSheets: [],
  activeSheet: null,
  allSheets: [],
  // Insights state
  insights: null,
  insightsFilters: {},
  insightsPage: 1,
  insightsSearch: '',
  insightsSortColumn: null,
  insightsSortDir: 'ASC',
  insightsTableTotalCount: 0,
  insightsCharts: {},
  insightsChartCache: {},
  activeInsightsTab: 'all',
  selectedInsightId: null,
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
const insightsPage      = document.getElementById('insightsPage');


const inputBarWrap      = document.querySelector('.input-bar-wrap');
const chatInput         = document.getElementById('chatInput');
const sendBtn           = document.getElementById('sendBtn');

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

    if (data.multi_sheet) {
      // Workbook with multiple sheets: prompt user to pick one
      state.tempWorkbookFilename = data.filename;
      state.tempWorkbookSheets   = data.sheets;
      state.activeSheet          = null;
      state.allSheets            = data.sheets;

      // Hide all standard pages and empty states
      closeAllPages();
      noDatasetEmpty.style.display = 'none';
      datasetEmpty.style.display   = 'none';
      messagesContainer.style.display = 'none';
      emptyState.style.display     = 'flex';

      const sheetSelectEmpty = document.getElementById('multiSheetSelectEmpty');
      if (sheetSelectEmpty) {
        sheetSelectEmpty.style.display = 'flex';
        const selector = document.getElementById('uploadSheetSelector');
        if (selector) {
          selector.innerHTML = data.sheets.map(sh => `<option value="${escHtml(sh)}">${escHtml(sh)}</option>`).join('');
        }
      }
      showToast(`"${file.name}" uploaded successfully. Please select a sheet to analyze.`, 'info');
    } else {
      // Single sheet or CSV
      state.dataset        = { name: file.name, rows: data.rows, columns: data.columns };
      state.uploaded       = true;
      state.masterSchema   = data.schema || {};
      state.previewTruncated = !!data.preview_truncated;
      state.previewRowCount  = data.preview_row_count || 0;
      state.activeSheet    = null;
      state.allSheets      = [];

      const sheetSelectEmpty = document.getElementById('multiSheetSelectEmpty');
      if (sheetSelectEmpty) sheetSelectEmpty.style.display = 'none';

      onDatasetLoaded(data);
      showToast(`"${file.name}" uploaded — ${data.rows.toLocaleString()} rows, ${data.columns.length} columns.`, 'success');
    }

  } catch (err) {
    showToast('Upload failed. Please check your connection.', 'error');
    console.error(err);
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

  // Enable dashboard navigation item in sidebar
  const navDb = document.getElementById('navDashboard');
  if (navDb) {
    navDb.classList.remove('disabled');
    navDb.disabled = false;
    navDb.removeAttribute('title');
  }

  // Populate dashboard sheet selector if multiple sheets are available
  const dbSheetWrap = document.getElementById('dbSheetSelectWrap');
  const dbSheetSelector = document.getElementById('dbSheetSelector');
  if (state.allSheets && state.allSheets.length > 1) {
    dbSheetWrap.style.display = 'block';
    dbSheetSelector.innerHTML = state.allSheets.map(sh => `
      <option value="${escHtml(sh)}" ${sh === state.activeSheet ? 'selected' : ''}>${escHtml(sh)}</option>
    `).join('');
  } else {
    dbSheetWrap.style.display = 'none';
  }

  document.querySelectorAll('.sidebar-nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === 'dashboard');
  });

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
   AI INSIGHTS & UTILITY PAGES
   (Dashboard, Insights, Reports, Settings controllers)
════════════════════════════════════════════════════════════════ */
function showDashboardView() {
  if (!state.uploaded) return;

  closeAllPages();
  
  // Hide chat containers to render full dashboard SPA
  messagesContainer.style.display = 'none';
  emptyState.style.display = 'none';
  inputBarWrap.classList.remove('visible');

  const dbPage = document.getElementById('dashboardPage');
  if (dbPage) dbPage.style.display = 'block';

  document.querySelectorAll('.sidebar-nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === 'dashboard');
  });

  // Set header dataset label
  const dbDatasetName = document.getElementById('dbDatasetName');
  if (dbDatasetName) {
    dbDatasetName.textContent = state.activeSheet
      ? `${state.dataset.name} (${state.activeSheet})`
      : state.dataset.name;
  }

  // Reset page, sorting, search for clean entry
  state.dashboardFilters = {};
  state.dashboardPage = 1;
  state.dashboardSearch = "";
  state.dashboardSortColumn = null;
  state.dashboardSortDir = "ASC";
  
  const searchInput = document.getElementById('dbTableSearchInput');
  if (searchInput) searchInput.value = "";

  fetchDashboardData();
}

function closeDashboardPage() {
  const dbPage = document.getElementById('dashboardPage');
  if (dbPage) dbPage.style.display = 'none';

  messagesContainer.style.display = 'flex';
  emptyState.style.display = messagesContainer.children.length ? 'none' : 'flex';
  inputBarWrap.classList.add('visible');

  document.querySelectorAll('.sidebar-nav-item').forEach(item => item.classList.remove('active'));
  chatInput.focus();
}

async function loadSelectedExcelSheet() {
  const selector = document.getElementById('uploadSheetSelector');
  const loadBtn = document.getElementById('uploadSheetBtn');
  if (!selector || !loadBtn) return;

  const sheetName = selector.value;
  if (!sheetName) {
    showToast('Please select a sheet.', 'error');
    return;
  }

  loadBtn.disabled = true;
  const originalHtml = loadBtn.innerHTML;
  loadBtn.innerHTML = iconSpinner() + ' Loading Worksheet...';

  try {
    const res = await fetch('/api/select-sheet', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: state.tempWorkbookFilename,
        sheet_name: sheetName
      })
    });

    const response = await res.json();
    if (!res.ok || !response.success) {
      showToast(response.error || 'Failed to load sheet.', 'error');
      return;
    }

    state.dataset = { name: state.tempWorkbookFilename, rows: response.rows, columns: response.columns };
    state.uploaded = true;
    state.masterSchema = response.schema || {};
    state.previewTruncated = !!response.preview_truncated;
    state.previewRowCount = response.preview_row_count || 0;
    state.activeSheet = sheetName;
    state.allSheets = state.tempWorkbookSheets;

    const sheetSelectEmpty = document.getElementById('multiSheetSelectEmpty');
    if (sheetSelectEmpty) sheetSelectEmpty.style.display = 'none';

    onDatasetLoaded(response);
    showToast(`"${state.tempWorkbookFilename}" (${sheetName}) loaded — ${response.rows.toLocaleString()} rows.`, 'success');

  } catch (err) {
    showToast('Failed to load worksheet.', 'error');
    console.error(err);
  } finally {
    loadBtn.disabled = false;
    loadBtn.innerHTML = originalHtml;
  }
}

async function onDashboardSheetChanged() {
  const dbSheetSelector = document.getElementById('dbSheetSelector');
  if (!dbSheetSelector) return;
  const sheetName = dbSheetSelector.value;
  if (!sheetName) return;

  const loading = document.getElementById('dbLoading');
  const content = document.getElementById('dbContent');
  const error = document.getElementById('dbError');

  loading.style.display = 'flex';
  content.style.display = 'none';
  error.style.display = 'none';

  try {
    const res = await fetch('/api/select-sheet', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: state.dataset.name,
        sheet_name: sheetName
      })
    });

    const response = await res.json();
    if (!res.ok || !response.success) {
      showToast(response.error || 'Failed to switch sheet.', 'error');
      loading.style.display = 'none';
      error.textContent = response.error || 'Failed to switch sheet.';
      error.style.display = 'block';
      return;
    }

    state.dataset = { name: state.dataset.name, rows: response.rows, columns: response.columns };
    state.masterSchema = response.schema || {};
    state.previewTruncated = !!response.preview_truncated;
    state.previewRowCount = response.preview_row_count || 0;
    state.activeSheet = sheetName;

    // Reset components & caches
    state.overview = null;
    state.insights = null;
    populateOverview(response);

    state.dashboardFilters = {};
    state.dashboardPage = 1;
    state.dashboardSearch = "";
    state.dashboardSortColumn = null;
    state.dashboardSortDir = "ASC";
    
    const searchInput = document.getElementById('dbTableSearchInput');
    if (searchInput) searchInput.value = "";

    showToast(`Switched sheet to "${sheetName}" — ${response.rows.toLocaleString()} rows.`, 'success');
    await fetchDashboardData();

  } catch (err) {
    showToast('Failed to switch sheet.', 'error');
    console.error(err);
    loading.style.display = 'none';
    error.textContent = 'Failed to switch sheet.';
    error.style.display = 'block';
  }
}

async function fetchDashboardData() {
  const loading = document.getElementById('dbLoading');
  const content = document.getElementById('dbContent');
  const error = document.getElementById('dbError');

  if (content.style.display === 'none') {
    loading.style.display = 'flex';
  }

  try {
    const res = await fetch('/api/dashboard/data', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filters: state.dashboardFilters || {},
        page: state.dashboardPage || 1,
        page_size: 20,
        search: state.dashboardSearch || "",
        sort_column: state.dashboardSortColumn,
        sort_dir: state.dashboardSortDir || "ASC"
      })
    });

    const response = await res.json();
    if (!res.ok || !response.success) {
      throw new Error(response.error || 'Failed to load dashboard data.');
    }

    renderDashboard(response);

    loading.style.display = 'none';
    content.style.display = 'block';
    error.style.display = 'none';
  } catch (err) {
    console.error(err);
    loading.style.display = 'none';
    error.textContent = err.message || 'An error occurred while loading dashboard metrics.';
    error.style.display = 'block';
  }
}

function renderDashboard(data) {
  // 1. Render KPIs
  const icons = {
    "total_records": "ti-list-numbers",
    "sum_value": "ti-sum",
    "avg_value": "ti-math-avg",
    "top_category": "ti-tags"
  };
  
  const deck = document.getElementById('dbKpiDeck');
  if (deck) {
    deck.innerHTML = data.kpis.map(kpi => `
      <div class="overview-stat-card" style="display: flex; align-items: center; gap: 12px; padding: 16px;">
        <div class="metric-icon-box" style="width: 42px; height: 42px; border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; background: var(--primary-dim); color: var(--primary); font-size: 18px;">
          <i class="ti ${icons[kpi.id] || 'ti-calculator'}"></i>
        </div>
        <div>
          <span class="stat-label" style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; color: var(--text-muted); display: block;">${escHtml(kpi.label)}</span>
          <strong class="stat-value" style="font-size: 18px; font-weight: 700; color: var(--text); display: block; margin-top: 2px;">${escHtml(kpi.value)}</strong>
        </div>
      </div>
    `).join('');
  }

  // 2. Render Active Filters
  const filtersBar = document.getElementById('dbFiltersBar');
  const chipsContainer = document.getElementById('dbActiveFilterChips');
  if (filtersBar && chipsContainer) {
    const filterEntries = Object.entries(state.dashboardFilters);
    if (filterEntries.length > 0) {
      filtersBar.style.display = 'flex';
      chipsContainer.innerHTML = filterEntries.map(([col, val]) => `
        <span class="db-filter-chip">
          <span>${escHtml(col)}: ${escHtml(Array.isArray(val) ? val.join(', ') : val)}</span>
          <button onclick="removeDashboardFilter('${escHtml(col)}')"><i class="ti ti-x"></i></button>
        </span>
      `).join('');
    } else {
      filtersBar.style.display = 'none';
    }
  }

  // 3. Render Insights
  const insightsList = document.getElementById('dbInsightsList');
  if (insightsList) {
    const getInsightClass = (text) => {
      const t = text.toLowerCase();
      if (t.includes('quality') || t.includes('missing') || t.includes('duplicate')) return 'insight-quality';
      if (t.includes('outlier')) return 'insight-outliers';
      if (t.includes('concentration') || t.includes('dominant')) return 'insight-concentration';
      if (t.includes('correlation')) return 'insight-correlation';
      if (t.includes('trend')) return 'insight-trend';
      return '';
    };

    const getInsightIcon = (text) => {
      const t = text.toLowerCase();
      if (t.includes('quality') || t.includes('missing') || t.includes('duplicate')) return 'ti-alert-triangle';
      if (t.includes('outlier')) return 'ti-chart-candle';
      if (t.includes('concentration') || t.includes('dominant')) return 'ti-chart-pie';
      if (t.includes('correlation')) return 'ti-chart-dots';
      if (t.includes('trend')) return 'ti-trending-up';
      return 'ti-info-circle';
    };

    insightsList.innerHTML = data.insights.map(ins => `
      <div class="db-insight-card ${getInsightClass(ins)}">
        <i class="ti ${getInsightIcon(ins)}"></i>
        <div>${escHtml(ins)}</div>
      </div>
    `).join('');
  }

  // 4. Render Recommended Charts
  renderDashboardCharts(data.chart_recommendations);

  // 5. Render Source Table
  const tableHead = document.getElementById('dbTableHead');
  const tableBody = document.getElementById('dbTableBody');
  if (tableHead && tableBody && data.table_data) {
    state.dashboardTableTotalCount = data.table_data.total_count;

    // Head
    const headers = data.table_data.columns.map(col => {
      const isSorted = state.dashboardSortColumn === col;
      const icon = isSorted ? (state.dashboardSortDir === 'ASC' ? ' ▲' : ' ▼') : '';
      return `<th onclick="onDashboardTableSort('${escHtml(col)}')" style="cursor: pointer; user-select: none;">
        ${escHtml(col)}${icon}
      </th>`;
    }).join('');
    tableHead.innerHTML = `<tr>${headers}</tr>`;

    // Body
    if (data.table_data.rows.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="${data.table_data.columns.length}" style="text-align: center; color: var(--text-muted); padding: 2rem;">No matching entries found</td></tr>`;
    } else {
      tableBody.innerHTML = data.table_data.rows.map(row => `
        <tr>
          ${data.table_data.columns.map(col => `<td>${escHtml(String(row[col] !== undefined && row[col] !== null ? row[col] : ''))}</td>`).join('')}
        </tr>
      `).join('');
    }

    // Pagination Indicators
    const totalCountEl = document.getElementById('dbTableTotalCount');
    const pageIndicatorEl = document.getElementById('dbTablePageIndicator');
    const prevBtn = document.getElementById('dbTablePrevBtn');
    const nextBtn = document.getElementById('dbTableNextBtn');

    if (totalCountEl) {
      const start = data.table_data.total_count === 0 ? 0 : ((data.table_data.page - 1) * data.table_data.page_size) + 1;
      const end = Math.min(data.table_data.page * data.table_data.page_size, data.table_data.total_count);
      totalCountEl.textContent = `Showing ${start} to ${end} of ${data.table_data.total_count.toLocaleString()} entries`;
    }

    const maxPages = Math.max(1, Math.ceil(data.table_data.total_count / data.table_data.page_size));
    if (pageIndicatorEl) {
      pageIndicatorEl.textContent = `Page ${data.table_data.page} of ${maxPages}`;
    }

    if (prevBtn) prevBtn.disabled = data.table_data.page <= 1;
    if (nextBtn) nextBtn.disabled = data.table_data.page >= maxPages;
  }
}

function renderDashboardCharts(chartRecs) {
  const container = document.getElementById('dbChartsGrid');
  if (!container) return;

  if (!state.dashboardCharts) {
    state.dashboardCharts = {};
  }
  Object.values(state.dashboardCharts).forEach(chart => chart.destroy());
  state.dashboardCharts = {};

  container.innerHTML = "";

  if (!chartRecs || chartRecs.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1; padding: 3rem; text-align: center; color: var(--text-muted); border: 1px dashed var(--border); border-radius: var(--radius);">
        <i class="ti ti-chart-bar-off" style="font-size: 36px; display: block; margin-bottom: 0.5rem; color: var(--text-faint);"></i>
        No visualizations could be recommended for this worksheet layout.
      </div>
    `;
    return;
  }

  chartRecs.forEach(chart => {
    const card = document.createElement('div');
    card.className = 'db-chart-card';
    card.innerHTML = `
      <div class="db-chart-title-wrap">
        <h3 class="db-chart-title">${escHtml(chart.title)}</h3>
        <p class="db-chart-reason">${escHtml(chart.reason)}</p>
      </div>
      <div class="db-chart-canvas-wrap">
        <canvas id="canvas_${chart.id}"></canvas>
      </div>
    `;
    container.appendChild(card);

    const ctx = document.getElementById(`canvas_${chart.id}`).getContext('2d');
    const isDark = document.body.getAttribute('data-theme') === 'dark';
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
    const textColor = isDark ? '#D1D1D1' : '#353740';

    const palette = [
      'rgba(37, 99, 235, 0.8)',
      'rgba(168, 85, 247, 0.8)',
      'rgba(245, 158, 11, 0.8)',
      'rgba(22, 163, 74, 0.8)',
      'rgba(249, 115, 22, 0.8)',
      'rgba(14, 116, 144, 0.8)',
    ];

    const borderPalette = [
      '#2563EB', '#A855F7', '#D97706', '#16A34A', '#F97316', '#0E7490'
    ];

    let chartConfig = {
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: chart.type === 'pie',
            position: 'bottom',
            labels: {
              color: textColor,
              font: { family: 'Inter', size: 10 }
            }
          },
          tooltip: {
            titleFont: { family: 'Inter', weight: 'bold' },
            bodyFont: { family: 'Inter' }
          }
        },
        scales: {},
        onClick: (evt, activeElements) => {
          if (activeElements.length > 0) {
            const activePoint = activeElements[0];
            const index = activePoint.index;

            if (chart.type === 'scatter') return;

            const clickedValue = chart.spec.labels[index];
            if (clickedValue !== undefined && clickedValue !== "Others" && clickedValue !== "Null" && clickedValue !== "Missing") {
              applyDashboardFilter(chart.x_column, clickedValue);
            }
          }
        }
      }
    };

    if (chart.type !== 'pie') {
      chartConfig.options.scales = {
        x: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { family: 'Inter', size: 9 } }
        },
        y: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { family: 'Inter', size: 9 } }
        }
      };
    }

    if (chart.type === 'scatter') {
      chartConfig.type = 'scatter';
      chartConfig.data = {
        datasets: chart.spec.series.map((s, idx) => ({
          label: s.label,
          data: s.data,
          backgroundColor: palette[idx % palette.length],
          borderColor: borderPalette[idx % borderPalette.length],
          pointRadius: 4,
          pointHoverRadius: 6
        }))
      };
      
      chartConfig.options.scales.x.title = {
        display: true,
        text: chart.x_column.replace(/_/g, ' '),
        color: textColor,
        font: { family: 'Inter', size: 10, weight: 'bold' }
      };
      chartConfig.options.scales.y.title = {
        display: true,
        text: chart.y_column.replace(/_/g, ' '),
        color: textColor,
        font: { family: 'Inter', size: 10, weight: 'bold' }
      };
    } else if (chart.type === 'pie') {
      chartConfig.type = 'doughnut';
      chartConfig.data = {
        labels: chart.spec.labels,
        datasets: [{
          data: chart.spec.series[0].data,
          backgroundColor: palette.slice(0, chart.spec.labels.length),
          borderColor: isDark ? '#171717' : '#FFFFFF',
          borderWidth: 1.5
        }]
      };
    } else if (chart.type === 'area') {
      chartConfig.type = 'line';
      chartConfig.data = {
        labels: chart.spec.labels,
        datasets: chart.spec.series.map((s, idx) => ({
          label: s.label,
          data: s.data,
          backgroundColor: palette[idx % palette.length].replace('0.8', '0.2'),
          borderColor: borderPalette[idx % borderPalette.length],
          borderWidth: 2,
          fill: true,
          tension: 0.15
        }))
      };
    } else {
      chartConfig.type = chart.type;
      chartConfig.data = {
        labels: chart.spec.labels,
        datasets: chart.spec.series.map((s, idx) => ({
          label: s.label,
          data: s.data,
          backgroundColor: chart.type === 'bar' ? palette[idx % palette.length] : palette[idx % palette.length].replace('0.8', '0.05'),
          borderColor: borderPalette[idx % borderPalette.length],
          borderWidth: 2,
          fill: false,
          tension: 0.15
        }))
      };
    }

    state.dashboardCharts[chart.id] = new Chart(ctx, chartConfig);
  });
}

function applyDashboardFilter(column, value) {
  if (!state.dashboardFilters) {
    state.dashboardFilters = {};
  }
  state.dashboardFilters[column] = [value];
  state.dashboardPage = 1;
  fetchDashboardData();
}

function removeDashboardFilter(column) {
  if (state.dashboardFilters && state.dashboardFilters[column]) {
    delete state.dashboardFilters[column];
    state.dashboardPage = 1;
    fetchDashboardData();
  }
}

function clearAllDashboardFilters() {
  state.dashboardFilters = {};
  state.dashboardPage = 1;
  state.dashboardSearch = "";
  
  const searchInput = document.getElementById('dbTableSearchInput');
  if (searchInput) searchInput.value = "";
  
  fetchDashboardData();
}

function onDashboardTableSearch() {
  const searchInput = document.getElementById('dbTableSearchInput');
  if (!searchInput) return;

  state.dashboardSearch = searchInput.value;
  state.dashboardPage = 1;

  if (state._dbSearchTimeout) {
    clearTimeout(state._dbSearchTimeout);
  }
  state._dbSearchTimeout = setTimeout(() => {
    fetchDashboardData();
  }, 250);
}

function onDashboardTableSort(column) {
  if (state.dashboardSortColumn === column) {
    state.dashboardSortDir = state.dashboardSortDir === 'ASC' ? 'DESC' : 'ASC';
  } else {
    state.dashboardSortColumn = column;
    state.dashboardSortDir = 'ASC';
  }
  fetchDashboardData();
}

function changeDashboardPage(delta) {
  const page = state.dashboardPage || 1;
  const newPage = page + delta;
  if (newPage < 1) return;

  const maxPages = Math.ceil(state.dashboardTableTotalCount / 20);
  if (newPage > maxPages && delta > 0) return;

  state.dashboardPage = newPage;
  fetchDashboardData();
}

async function exportDashboardTable() {
  const btn = document.querySelector('.overview-export-btn');
  if (!btn) return;
  const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = iconSpinner() + ' Exporting...';

  try {
    const res = await fetch('/api/dashboard/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filters: state.dashboardFilters || {},
        search: state.dashboardSearch || "",
        sort_column: state.dashboardSortColumn,
        sort_dir: state.dashboardSortDir || "ASC",
        format: "csv"
      })
    });

    if (!res.ok) throw new Error('Export failed');

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${state.dataset.name.split('.')[0]}_dashboard_export.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    showToast('Dashboard data exported successfully.', 'success');
  } catch (err) {
    showToast('Failed to export dashboard data.', 'error');
    console.error(err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

function closeInsightsPage() {
  if (!insightsPage) return;
  insightsPage.style.display = 'none';
  messagesContainer.style.display = 'flex';
  emptyState.style.display = messagesContainer.children.length ? 'none' : 'flex';
  inputBarWrap.classList.add('visible');
  document.querySelectorAll('.sidebar-nav-item').forEach(item => item.classList.remove('active'));
  chatInput.focus();
}



async function showInsightsPage() {
  if (!state.uploaded) {
    showToast('Please upload a dataset first.', 'error');
    return;
  }

  closeAllPages();
  insightsPage.style.display = 'block';
  document.querySelectorAll('.sidebar-nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === 'insights');
  });
  chatMain.scrollTo({ top: 0, behavior: 'smooth' });

  const loading = document.getElementById('insightsLoading');
  const content = document.getElementById('insightsContent');
  const error = document.getElementById('insightsError');
  const status = document.getElementById('insightsLoadingStatus');
  const bar = document.getElementById('insightsLoadingBar');

  loading.style.display = 'flex';
  content.style.display = 'none';
  error.style.display = 'none';

  bar.style.width = '10%';
  status.textContent = 'Analyzing dataset...';

  // Sequential status update triggers
  const stages = [
    { text: 'Analyzing dataset...', pct: 15 },
    { text: 'Detecting business context...', pct: 35 },
    { text: 'Finding key events...', pct: 60 },
    { text: 'Generating insights...', pct: 80 },
    { text: 'Building report...', pct: 95 }
  ];

  let stageIdx = 0;
  const progressInterval = setInterval(() => {
    if (stageIdx < stages.length) {
      status.textContent = stages[stageIdx].text;
      bar.style.width = stages[stageIdx].pct + '%';
      stageIdx++;
    }
  }, 750);

  try {
    // Reset insights state on clean page open
    state.insightsFilters = {};
    state.insightsPage = 1;
    state.insightsSearch = '';
    state.insightsSortColumn = null;
    state.insightsSortDir = 'ASC';
    state.selectedInsightId = null;
    state.activeInsightsTab = 'all';

    const searchInput = document.getElementById('insTableSearchInput');
    if (searchInput) searchInput.value = '';

    const insights = state.insights || await fetchInsights();
    state.insights = insights;

    clearInterval(progressInterval);
    bar.style.width = '100%';

    setTimeout(() => {
      loading.style.display = 'none';
      content.style.display = 'block';
      
      // Update header details
      const insDatasetName = document.getElementById('insDatasetName');
      if (insDatasetName) {
        insDatasetName.textContent = state.activeSheet
          ? `${state.dataset.name} (${state.activeSheet})`
          : state.dataset.name;
      }
      const insLastUpdated = document.getElementById('insLastUpdated');
      if (insLastUpdated) {
        const now = new Date();
        insLastUpdated.textContent = `Last Updated: ${now.toLocaleTimeString()}`;
      }

      renderInsights(insights);
      fetchInsightsTableData(); // Initial load of drill-down table
    }, 300);

  } catch (err) {
    clearInterval(progressInterval);
    loading.style.display = 'none';
    error.textContent = err.message || 'Unable to generate insights.';
    error.style.display = 'block';
  }
}

async function fetchInsights() {
  const response = await fetch('/insights');
  const data = await response.json();
  if (!response.ok || !data.success) {
    throw new Error(data.error || 'Failed to retrieve insights from the server.');
  }
  return data;
}

function getQuestionDetails(question) {
  switch (question) {
    case 'WHAT_HAPPENED':
      return { qBorderClass: 'q-what-happened', qLabel: 'What Happened' };
    case 'WHY_IT_HAPPENED':
      return { qBorderClass: 'q-why-it-happened', qLabel: 'Why it Happened' };
    case 'WHAT_TO_DO':
      return { qBorderClass: 'q-what-to-do', qLabel: 'What to Do' };
    case 'WHAT_NEXT':
      return { qBorderClass: 'q-what-next', qLabel: 'What Next' };
    case 'WHAT_IS_UNUSUAL':
      return { qBorderClass: 'q-what-is-unusual', qLabel: 'Unusual' };
    case 'CAN_I_TRUST':
      return { qBorderClass: 'q-can-i-trust', qLabel: 'Trust' };
    default:
      return { qBorderClass: '', qLabel: question || '' };
  }
}

function formatMetadataValue(val) {
  if (val === null || val === undefined) {
    return '<span style="color: var(--text-muted); font-weight: normal;">—</span>';
  }
  const s = String(val).trim();
  if (s === '' || s.toLowerCase() === 'none') {
    return '<span style="color: var(--text-muted); font-weight: normal;">—</span>';
  }
  return escHtml(s.replace(/_/g, ' '));
}

function renderInsights(insights) {
  // 1. Render Trust Scoring Banner
  const trustScore = insights.dataset_summary.trust_score !== undefined ? insights.dataset_summary.trust_score : 100;
  const insTrustScoreIcon = document.getElementById('insTrustScoreIcon');
  if (insTrustScoreIcon) {
    insTrustScoreIcon.textContent = `${trustScore}%`;
    if (trustScore >= 85) {
      insTrustScoreIcon.style.borderColor = 'var(--success)';
      insTrustScoreIcon.style.color = 'var(--success)';
      insTrustScoreIcon.style.backgroundColor = 'var(--success-bg)';
    } else if (trustScore >= 60) {
      insTrustScoreIcon.style.borderColor = 'var(--warning)';
      insTrustScoreIcon.style.color = 'var(--warning)';
      insTrustScoreIcon.style.backgroundColor = 'var(--warning-bg)';
    } else {
      insTrustScoreIcon.style.borderColor = 'var(--error)';
      insTrustScoreIcon.style.color = 'var(--error)';
      insTrustScoreIcon.style.backgroundColor = 'var(--error-bg)';
    }
  }

  const insTrustScoreText = document.getElementById('insTrustScoreText');
  if (insTrustScoreText) {
    const flags = insights.dataset_summary.data_quality_flags || [];
    if (flags.length > 0) {
      insTrustScoreText.textContent = `Quality flags raised: ${flags.join(', ')}`;
    } else {
      insTrustScoreText.textContent = 'Completeness, unique values, and formatting parameters verified.';
    }
  }

  const insForecastSafetyBadge = document.getElementById('insForecastSafetyBadge');
  if (insForecastSafetyBadge) {
    const safetyStatus = insights.dataset_summary.forecast_safety_status || '';
    if (safetyStatus.toLowerCase() === 'safe') {
      insForecastSafetyBadge.textContent = 'Forecast Safe';
      insForecastSafetyBadge.className = 'confidence-badge confidence-high';
      insForecastSafetyBadge.removeAttribute('title');
    } else {
      insForecastSafetyBadge.textContent = 'Forecast Unavailable';
      insForecastSafetyBadge.className = 'confidence-badge confidence-low';
      insForecastSafetyBadge.title = safetyStatus;
    }
  }

  // 2. Render Section 1: Dataset Summary Profile Cards
  const elDomain = document.getElementById('idsDomain');
  if (elDomain) elDomain.textContent = insights.dataset_summary.domain || 'N/A';
  document.getElementById('idsGrain').textContent = insights.dataset_summary.grain || 'N/A';
  document.getElementById('idsRows').textContent = (insights.dataset_summary.row_count || 0).toLocaleString();
  document.getElementById('idsDateRange').textContent = insights.dataset_summary.date_range || 'N/A';
  
  const dqCount = insights.dataset_summary.data_quality_flags ? insights.dataset_summary.data_quality_flags.length : 0;
  document.getElementById('idsQuality').textContent = dqCount > 0 ? `${dqCount} Flags Raised` : 'Excellent';

  // Render Metrics badges
  const metricsContainer = document.getElementById('idsMetrics');
  const detectedMetrics = insights.dataset_summary.metrics || [];
  metricsContainer.innerHTML = detectedMetrics.map(m => `
    <span class="overview-type-badge overview-type-num" style="padding: 4px 10px; border-radius: var(--radius-sm); font-size: 12px; font-weight: 600; background: var(--primary-dim); color: var(--primary);">${escHtml(m)}</span>
  `).join('');

  // Render Dimensions badges
  const dimensionsContainer = document.getElementById('idsDimensions');
  const detectedDimensions = insights.dataset_summary.dimensions || [];
  dimensionsContainer.innerHTML = detectedDimensions.map(d => `
    <span class="overview-type-badge overview-type-text" style="padding: 4px 10px; border-radius: var(--radius-sm); font-size: 12px; font-weight: 600; background: var(--surface-2); border: 1px solid var(--border); color: var(--text-secondary);">${escHtml(d)}</span>
  `).join('');

  // Render Quality flags
  const flagsWrap = document.getElementById('idsQualityFlagsWrap');
  const flagsList = document.getElementById('idsQualityFlags');
  const flags = insights.dataset_summary.data_quality_flags || [];
  if (flags.length > 0) {
    flagsWrap.style.display = 'block';
    flagsList.innerHTML = flags.map(f => `<li>${escHtml(f)}</li>`).join('');
  } else {
    flagsWrap.style.display = 'none';
  }

  // 3. Update all 7 tab badges
  const allCount = (insights.insights || []).length;
  const whatHappenedCount = (insights.insights || []).filter(ins => ins.question === 'WHAT_HAPPENED').length;
  const whyItHappenedCount = (insights.insights || []).filter(ins => ins.question === 'WHY_IT_HAPPENED').length;
  const whatToDoCount = (insights.insights || []).filter(ins => ins.question === 'WHAT_TO_DO').length;
  const whatNextCount = (insights.insights || []).filter(ins => ins.question === 'WHAT_NEXT').length;
  const whatIsUnusualCount = (insights.insights || []).filter(ins => ins.question === 'WHAT_IS_UNUSUAL').length;
  const canITrustCount = (insights.insights || []).filter(ins => ins.question === 'CAN_I_TRUST').length;

  document.getElementById('tab-badge-all').textContent = allCount;
  document.getElementById('tab-badge-what-happened').textContent = whatHappenedCount;
  document.getElementById('tab-badge-why-it-happened').textContent = whyItHappenedCount;
  document.getElementById('tab-badge-what-to-do').textContent = whatToDoCount;
  document.getElementById('tab-badge-what-next').textContent = whatNextCount;
  document.getElementById('tab-badge-what-is-unusual').textContent = whatIsUnusualCount;
  document.getElementById('tab-badge-can-i-trust').textContent = canITrustCount;

  // Set active class on active tab button
  const activeTab = state.activeInsightsTab || 'all';
  const tabButtons = document.querySelectorAll('#insightsTabsBar .insights-tab-btn');
  tabButtons.forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab.toLowerCase() === activeTab.toLowerCase());
  });

  // Bind tab click listener
  const tabContainer = document.getElementById('insightsTabsBar');
  if (tabContainer && !tabContainer.dataset.listenerBound) {
    tabContainer.dataset.listenerBound = 'true';
    tabContainer.addEventListener('click', (e) => {
      const btn = e.target.closest('.insights-tab-btn');
      if (!btn) return;
      state.activeInsightsTab = btn.dataset.tab;
      renderInsights(state.insights);
    });
  }

  // Render Active Filter chips bar
  const filtersBar = document.getElementById('insFiltersBar');
  const chipsContainer = document.getElementById('insActiveFilterChips');
  if (filtersBar && chipsContainer) {
    const filterEntries = Object.entries(state.insightsFilters);
    if (filterEntries.length > 0) {
      filtersBar.style.display = 'flex';
      chipsContainer.innerHTML = filterEntries.map(([col, val]) => `
        <span class="db-filter-chip">
          <span>${escHtml(col)}: ${escHtml(Array.isArray(val) ? val.join(', ') : val)}</span>
          <button onclick="removeInsightsFilter('${escHtml(col)}')"><i class="ti ti-x"></i></button>
        </span>
      `).join('');
    } else {
      filtersBar.style.display = 'none';
    }
  }

  // Filter list of insights
  const filteredInsights = (insights.insights || []).filter(ins => {
    if (activeTab === 'all') return true;
    return ins.question.toLowerCase() === activeTab.toLowerCase();
  });

  // Clear existing sparkline Chart.js references
  if (!state.insightsCharts) {
    state.insightsCharts = {};
  }
  Object.values(state.insightsCharts).forEach(chart => chart.destroy());
  state.insightsCharts = {};

  // 4. Render Insights Cards Grid
  const grid = document.getElementById('insightsAgentGrid');
  if (filteredInsights.length === 0) {
    grid.innerHTML = `
      <div style="grid-column: 1 / -1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 4rem 2rem; text-align: center; background: var(--surface); border: 1px dashed var(--border); border-radius: var(--radius); color: var(--text-secondary);">
        <i class="ti ti-bulb" style="font-size: 2.5rem; margin-bottom: 0.8rem; color: var(--text-muted);"></i>
        <h3 style="font-size: 1.1rem; font-weight: 700; margin: 0 0 0.4rem 0;">No insights in this category</h3>
        <p style="font-size: 0.85rem; color: var(--text-muted); margin: 0;">There are no findings matching this specific question.</p>
      </div>
    `;
    return;
  }

  grid.innerHTML = filteredInsights.map(ins => {
    const sevClass = (ins.severity || 'medium').toLowerCase();
    const { qBorderClass, qLabel } = getQuestionDetails(ins.question);

    const confVal = (ins.confidence || 'medium').toUpperCase();
    let confClass = 'confidence-medium';
    if (confVal === 'HIGH') confClass = 'confidence-high';
    else if (confVal === 'LOW') confClass = 'confidence-low';

    const isSelected = ins.id === state.selectedInsightId;

    return `
      <div class="insights-card ${qBorderClass} ${isSelected ? 'selected' : ''}" id="ins-card-${ins.id}" style="position: relative; display: flex; flex-direction: column; gap: 1rem; padding: 1.5rem; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); box-shadow: var(--shadow-sm); transition: transform 0.2s ease, box-shadow 0.2s ease;">
        
        <!-- Header row -->
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
          <span style="font-size: 11px; font-weight: 700; color: var(--text-muted); font-family: var(--font-mono, monospace);">${escHtml(ins.id)}</span>
          <div style="display: flex; gap: 6px; align-items: center;">
            <span class="question-badge">${escHtml(qLabel)}</span>
            <span class="impact-badge badge-${sevClass}">${escHtml(ins.severity)}</span>
            <span class="confidence-badge ${confClass}">${escHtml(confVal)}</span>
          </div>
        </div>

        <!-- Title -->
        <h3 style="font-size: 15px; font-weight: 700; margin: 0; color: var(--text); line-height: 1.3;">${escHtml(ins.title)}</h3>

        <!-- Description -->
        <p style="font-size: 13px; line-height: 1.5; color: var(--text-secondary); margin: 0; flex-grow: 1;">${escHtml(ins.description)}</p>

        <!-- Mini Sparkline evidence chart if not none -->
        ${ins.chart_type && ins.chart_type !== 'none' ? `
        <div class="ins-mini-chart-wrap" style="height: 100px; min-height: 100px;">
          <canvas id="chart_${ins.id}"></canvas>
        </div>
        ` : ''}

        <!-- Metadata Grid -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; padding: 0.8rem; background: var(--surface-2); border-radius: var(--radius-sm); border: 1px solid var(--border); font-size: 12px; line-height: 1.4;">
          <div>
            <span style="color: var(--text-muted); display: block; font-size: 10px; text-transform: uppercase; font-weight: 600; letter-spacing: 0.02em;">Metric</span>
            <strong style="color: var(--text);">${formatMetadataValue(ins.metric)}</strong>
          </div>
          <div>
            <span style="color: var(--text-muted); display: block; font-size: 10px; text-transform: uppercase; font-weight: 600; letter-spacing: 0.02em;">Dimension</span>
            <strong style="color: var(--text);">${formatMetadataValue(ins.dimension)}</strong>
          </div>
          <div>
            <span style="color: var(--text-muted); display: block; font-size: 10px; text-transform: uppercase; font-weight: 600; letter-spacing: 0.02em;">Period</span>
            <strong style="color: var(--text);">${formatMetadataValue(ins.period)}</strong>
          </div>
          <div>
            <span style="color: var(--text-muted); display: block; font-size: 10px; text-transform: uppercase; font-weight: 600; letter-spacing: 0.02em;">Magnitude</span>
            <strong style="color: var(--text);">${formatMetadataValue(ins.magnitude)}</strong>
          </div>
        </div>

        <!-- Evidence -->
        <div style="border-top: 1px solid var(--border); padding-top: 0.8rem; font-size: 12px; color: var(--text-muted); line-height: 1.5; margin-bottom: 0.5rem;">
          <strong>Evidence:</strong> ${parseSimpleMarkdown(ins.evidence)}
        </div>

      </div>
    `;
  }).join('');

  // 5. Initialize mini sparkline charts with caching support
  if (!state.insightsChartCache) {
    state.insightsChartCache = {};
  }

  filteredInsights.forEach(ins => {
    if (!ins.chart_type || ins.chart_type === 'none') return;
    const canvas = document.getElementById(`chart_${ins.id}`);
    if (!canvas) return;

    const cacheKey = JSON.stringify({
      metric: ins.metric,
      dimension: ins.dimension,
      filters: ins.filters || {},
      chart_type: ins.chart_type
    });

    if (state.insightsChartCache[cacheKey]) {
      const resData = state.insightsChartCache[cacheKey];
      drawSparkline(canvas, ins.id, ins.chart_type, resData.labels, resData.data, resData.metric_label);
    } else {
      fetch('/api/insights/chart-data', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          metric: ins.metric,
          dimension: ins.dimension,
          filters: ins.filters || {},
          chart_type: ins.chart_type
        })
      })
      .then(res => res.json())
      .then(resData => {
        if (!resData.success) return;
        state.insightsChartCache[cacheKey] = resData;
        drawSparkline(canvas, ins.id, ins.chart_type, resData.labels, resData.data, resData.metric_label);
      })
      .catch(err => console.error('Error drawing sparkline:', err));
    }
  });

  // 6. Bind card selection click listeners
  filteredInsights.forEach(ins => {
    const cardEl = document.getElementById(`ins-card-${ins.id}`);
    if (cardEl) {
      cardEl.addEventListener('click', (e) => {
        // Ignore clicks if clicking links, buttons, or charts
        if (e.target.closest('a, button, canvas')) return;
        toggleInsightCardSelection(ins);
      });
    }
  });
}

function drawSparkline(canvas, insId, chartType, labels, data, metricLabel) {
  const ctx = canvas.getContext('2d');
  const isDark = document.body.getAttribute('data-theme') === 'dark';
  const textColor = isDark ? '#9B9B9B' : '#6E6E80';
  const gridColor = isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.04)';

  const accentColor = '#2563EB';

  let config = {
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          titleFont: { family: 'Inter', size: 9 },
          bodyFont: { family: 'Inter', size: 9 }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: textColor, font: { family: 'Inter', size: 8 } }
        },
        y: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { family: 'Inter', size: 8 } }
        }
      }
    }
  };

  if (chartType === 'pie') {
    config.type = 'doughnut';
    config.data = {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: [
          'rgba(37, 99, 235, 0.8)',
          'rgba(168, 85, 247, 0.8)',
          'rgba(245, 158, 11, 0.8)',
          'rgba(22, 163, 74, 0.8)',
          'rgba(249, 115, 22, 0.8)',
        ].slice(0, labels.length),
        borderColor: isDark ? '#171717' : '#FFFFFF',
        borderWidth: 1
      }]
    };
    config.options.scales = {};
  } else if (chartType === 'line' || chartType === 'area') {
    config.type = 'line';
    config.data = {
      labels: labels,
      datasets: [{
        label: metricLabel,
        data: data,
        borderColor: accentColor,
        backgroundColor: 'rgba(37, 99, 235, 0.06)',
        borderWidth: 1.5,
        fill: chartType === 'area',
        tension: 0.15,
        pointRadius: labels.length > 20 ? 0 : 2,
        pointHoverRadius: 4
      }]
    };
  } else {
    // bar chart sparkline
    config.type = 'bar';
    config.data = {
      labels: labels,
      datasets: [{
        label: metricLabel,
        data: data,
        backgroundColor: accentColor,
        borderRadius: 2
      }]
    };
  }

  state.insightsCharts[insId] = new Chart(ctx, config);
}

function toggleInsightCardSelection(ins) {
  if (state.selectedInsightId === ins.id) {
    state.selectedInsightId = null;
    state.insightsFilters = {};
  } else {
    state.selectedInsightId = ins.id;
    state.insightsFilters = ins.filters || {};
  }

  state.insightsPage = 1;
  renderInsights(state.insights);
  fetchInsightsTableData();
}

function clearAllInsightsFilters() {
  state.insightsFilters = {};
  state.selectedInsightId = null;
  state.insightsPage = 1;
  state.insightsSearch = '';

  const searchInput = document.getElementById('insTableSearchInput');
  if (searchInput) searchInput.value = '';

  renderInsights(state.insights);
  fetchInsightsTableData();
}

function removeInsightsFilter(column) {
  if (state.insightsFilters && state.insightsFilters[column]) {
    delete state.insightsFilters[column];
    state.selectedInsightId = null;
    state.insightsPage = 1;
    renderInsights(state.insights);
    fetchInsightsTableData();
  }
}

async function fetchInsightsTableData() {
  const tableHead = document.getElementById('insTableHead');
  const tableBody = document.getElementById('insTableBody');
  if (!tableHead || !tableBody) return;

  try {
    const res = await fetch('/api/insights/table-data', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filters: state.insightsFilters || {},
        page: state.insightsPage || 1,
        page_size: 20,
        search: state.insightsSearch || '',
        sort_column: state.insightsSortColumn,
        sort_dir: state.insightsSortDir || 'ASC'
      })
    });

    const response = await res.json();
    if (!res.ok || !response.success) {
      throw new Error(response.error || 'Failed to load insights table data.');
    }

    renderInsightsTable(response.table_data);

  } catch (err) {
    console.error(err);
    tableBody.innerHTML = `<tr><td colspan="100" style="text-align: center; color: var(--error); padding: 2rem;">Error: ${escHtml(err.message)}</td></tr>`;
  }
}

function renderInsightsTable(tableData) {
  const tableHead = document.getElementById('insTableHead');
  const tableBody = document.getElementById('insTableBody');
  if (!tableHead || !tableBody) return;

  state.insightsTableTotalCount = tableData.total_count;

  // Render headers
  const headers = tableData.columns.map(col => {
    const isSorted = state.insightsSortColumn === col;
    const icon = isSorted ? (state.insightsSortDir === 'ASC' ? ' ▲' : ' ▼') : '';
    return `<th onclick="onInsightsTableSort('${escHtml(col)}')" style="cursor: pointer; user-select: none;">
      ${escHtml(col)}${icon}
    </th>`;
  }).join('');
  tableHead.innerHTML = `<tr>${headers}</tr>`;

  // Render rows
  if (tableData.rows.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="${tableData.columns.length}" style="text-align: center; color: var(--text-muted); padding: 2rem;">No matching entries found</td></tr>`;
  } else {
    tableBody.innerHTML = tableData.rows.map(row => `
      <tr>
        ${tableData.columns.map(col => `<td>${escHtml(String(row[col] !== undefined && row[col] !== null ? row[col] : ''))}</td>`).join('')}
      </tr>
    `).join('');
  }

  // Pagination Indicators
  const totalCountEl = document.getElementById('insTableTotalCount');
  const pageIndicatorEl = document.getElementById('insTablePageIndicator');
  const prevBtn = document.getElementById('insTablePrevBtn');
  const nextBtn = document.getElementById('insTableNextBtn');

  if (totalCountEl) {
    const start = tableData.total_count === 0 ? 0 : ((tableData.page - 1) * tableData.page_size) + 1;
    const end = Math.min(tableData.page * tableData.page_size, tableData.total_count);
    totalCountEl.textContent = `Showing ${start} to ${end} of ${tableData.total_count.toLocaleString()} entries`;
  }

  const maxPages = Math.max(1, Math.ceil(tableData.total_count / tableData.page_size));
  if (pageIndicatorEl) {
    pageIndicatorEl.textContent = `Page ${tableData.page} of ${maxPages}`;
  }

  if (prevBtn) prevBtn.disabled = tableData.page <= 1;
  if (nextBtn) nextBtn.disabled = tableData.page >= maxPages;
}

function onInsightsTableSort(column) {
  if (state.insightsSortColumn === column) {
    state.insightsSortDir = state.insightsSortDir === 'ASC' ? 'DESC' : 'ASC';
  } else {
    state.insightsSortColumn = column;
    state.insightsSortDir = 'ASC';
  }
  fetchInsightsTableData();
}

function changeInsightsPage(delta) {
  const page = state.insightsPage || 1;
  const newPage = page + delta;
  if (newPage < 1) return;

  const maxPages = Math.ceil(state.insightsTableTotalCount / 20);
  if (newPage > maxPages && delta > 0) return;

  state.insightsPage = newPage;
  fetchInsightsTableData();
}

function onInsightsTableSearch() {
  const searchInput = document.getElementById('insTableSearchInput');
  if (!searchInput) return;

  state.insightsSearch = searchInput.value;
  state.insightsPage = 1;

  if (state._insSearchTimeout) {
    clearTimeout(state._insSearchTimeout);
  }
  state._insSearchTimeout = setTimeout(() => {
    fetchInsightsTableData();
  }, 250);
}

async function exportInsightsTable() {
  const btn = document.querySelector('#insightsPage .overview-export-btn');
  if (!btn) return;
  const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = iconSpinner() + ' Exporting...';

  try {
    const res = await fetch('/api/dashboard/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filters: state.insightsFilters || {},
        search: state.insightsSearch || '',
        sort_column: state.insightsSortColumn,
        sort_dir: state.insightsSortDir || 'ASC',
        format: 'csv'
      })
    });

    if (!res.ok) throw new Error('Export failed');

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${state.dataset.name.split('.')[0]}_insights_export.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    showToast('Insights data exported successfully.', 'success');
  } catch (err) {
    showToast('Failed to export insights data.', 'error');
    console.error(err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

// Utility to parse basic bold/italic markdown into HTML safely
function parseSimpleMarkdown(txt) {
  if (!txt) return '';
  return txt
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>');
}

/* ═══════════════════════════════════════════════════════════════
   NEW DATASET / RESET
════════════════════════════════════════════════════════════════ */
function resetToNoDataset() {
  state.tableData    = {};
  state.uploaded     = false;
  state.dataset      = { name: '', rows: 0, columns: [] };
  state.querying     = false;
  state.lastSQL      = '';
  state.overview     = null;
  state.insights     = null;
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
  if (data.message) {
    inner += `<div class="ai-summary">${parseMarkdown(data.message)}</div>`;
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

  // Render visualization chart block removed
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

// smartRecommend removed

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

// renderInlineChart and switchInlineChart removed



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
// toggleVizSubMenu removed

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

// closeAutoVisualization removed



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

// ── Theme Switcher Initialization & Event Handling ──
document.addEventListener('DOMContentLoaded', () => {
  const toggleBtn = document.getElementById('themeToggleBtn');
  const toggleIcon = document.getElementById('themeToggleIcon');
  
  if (!toggleBtn || !toggleIcon) return;
  
  function updateToggleUI(theme) {
    if (theme === 'dark') {
      toggleIcon.className = 'ti ti-sun';
      toggleBtn.title = 'Switch to Light Mode';
      toggleBtn.setAttribute('aria-label', 'Switch to Light Mode');
    } else {
      toggleIcon.className = 'ti ti-moon';
      toggleBtn.title = 'Switch to Dark Mode';
      toggleBtn.setAttribute('aria-label', 'Switch to Dark Mode');
    }
  }

  const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
  document.body.setAttribute('data-theme', currentTheme);
  updateToggleUI(currentTheme);

  toggleBtn.addEventListener('click', () => {
    const activeTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', activeTheme);
    document.body.setAttribute('data-theme', activeTheme);
    localStorage.setItem('theme', activeTheme);
    updateToggleUI(activeTheme);
  });

  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (!localStorage.getItem('theme')) {
      const systemTheme = e.matches ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', systemTheme);
      document.body.setAttribute('data-theme', systemTheme);
      updateToggleUI(systemTheme);
    }
  });
});