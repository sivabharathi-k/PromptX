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
  if (!file.name.toLowerCase().endsWith('.csv')) {
    showUploadError('Only CSV files are supported.');
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

  // Initialize master entry for visualizations
  state.tableData['master'] = { columns: data.columns, allRows: [], page: 0, sql: 'SELECT * FROM dataset' };

  // Dataset Overview in Sidebar
  populateOverview(data);

  uploadScreen.style.display = 'none';
  chatScreen.style.display   = 'flex';
  inputBarWrap.classList.add('visible');
  chatInput.focus();
}

function populateOverview(data) {
  const cols = data.columns || [];
  
  // Use master schema for NUM/DATE/TEXT breakdown if available
  let numCols, catCols;
  if (Object.keys(state.masterSchema).length > 0) {
    const classified = classifyColumnsFromSchema(cols);
    numCols = classified.numCols;
    catCols = classified.catCols;
  } else {
    // Fallback: old heuristic-based classification
    const numericHints = /id|num|count|qty|amount|price|sales|revenue|age|score|gpa|salary|total|rate|value|profit|cost|quantity|percent|ratio/;
    const dateHints    = /date|time|year|month|day|period|created|updated/;
    numCols = cols.filter(c => numericHints.test(c.toLowerCase()));
    catCols = cols.filter(c => !numericHints.test(c.toLowerCase()) && !dateHints.test(c.toLowerCase()));
  }

  // Target Sidebar IDs
  const elRows = document.getElementById('sbRows');
  const elCols = document.getElementById('sbCols');
  const elNum  = document.getElementById('sbNum');
  const elCat  = document.getElementById('sbCat');

  if (elRows) elRows.textContent = data.rows.toLocaleString();
  if (elCols) elCols.textContent = cols.length;
  if (elNum)  elNum.textContent  = numCols.length;
  if (elCat)  elCat.textContent  = catCols.length;
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
  state.vizModal = { msgId: null, chart: null };

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

/* ═══════════════════════════════════════════════════════════════
   AI INSIGHTS DASHBOARD (12-section enterprise module)
════════════════════════════════════════════════════════════════ */
async function loadInsights() {
  if (!state.uploaded) return;

  emptyState.style.display = 'none';
  messagesContainer.innerHTML = '';

  const loadingId = 'ins-load-' + Date.now();
  const row = document.createElement('div');
  row.className = 'msg-row msg-ai msg-loading';
  row.id = loadingId;
  row.innerHTML = `
    <div class="msg-ai-wrap">
      <div class="msg-ai-avatar" aria-hidden="true">${iconBot()}</div>
      <div class="msg-ai-card">
        <div class="loading-dots"><span></span><span></span><span></span></div>
        <div class="loading-text">Running AI analysis across all dimensions…</div>
      </div>
    </div>`;
  messagesContainer.appendChild(row);
  scrollToBottom();

  try {
    const res = await fetch('/insights', { method: 'POST' });
    const data = await res.json();
    removeMsg(loadingId);

    if (!res.ok || data.success === false) {
      appendErrorMsg(data.error || 'Insights generation failed.');
      return;
    }

    renderInsightsDashboard(data);
    scrollToBottom();
  } catch (e) {
    removeMsg(loadingId);
    appendErrorMsg('Could not reach the server for insights.');
  }
}

/* ── Main Dashboard Renderer ── */
function renderInsightsDashboard(data) {
  if (!data || data.success === false) {
    appendErrorMsg(data?.error || 'No insight data available.');
    return;
  }

  const msgId = 'insights-dash-' + Date.now();
  const row = document.createElement('div');
  row.className = 'msg-row msg-ai';
  row.id = msgId;
  row.innerHTML = `
    <div class="msg-ai-wrap">
      <div class="msg-ai-avatar" aria-hidden="true">${iconBot()}</div>
      <div class="msg-ai-card">
        <div class="insights-dashboard" id="${msgId}-dash"></div>
      </div>
    </div>`;
  messagesContainer.appendChild(row);

  const dash = document.getElementById(msgId + '-dash');
  
  // Build all 12 sections
  buildSection1Overview(dash, data);
  buildSection2Findings(dash, data);
  buildSection3Stats(dash, data);
  buildSection4Trends(dash, data);
  buildSection5Performers(dash, data);
  buildSection6Outliers(dash, data);
  buildSection7Correlations(dash, data);
  buildSection8Quality(dash, data);
  buildSection9Visuals(dash, data, msgId);
  buildSection10Business(dash, data);
  buildSection11Predictive(dash, data);
  buildSection12Executive(dash, data);

  // Render charts
  requestAnimationFrame(() => {
    renderInsightCharts(data, msgId);
  });
}

/* ── Section 1: Dataset Overview ── */
function buildSection1Overview(dash, data) {
  const ov = data.dataset_overview || {};
  const sec = createSection(dash, '1', '📊', 'Dataset Overview', 'Summary of your data');
  
  const grid = document.createElement('div');
  grid.className = 'insights-overview-grid';
  
  const kpis = [
    { label: 'Total Rows', value: (ov.total_rows || 0).toLocaleString(), desc: 'Records' },
    { label: 'Columns', value: ov.total_columns || 0, desc: `${ov.numeric_columns || 0} num · ${ov.categorical_columns || 0} cat` },
    { label: 'Type', value: ov.dataset_type || 'Generic', desc: 'Detected domain' },
    { label: 'Missing', value: (ov.total_missing_values || 0).toLocaleString(), desc: 'Empty cells' },
    { label: 'Duplicates', value: (ov.total_duplicate_records || 0).toLocaleString(), desc: 'Repeated rows' },
    { label: 'Memory', value: (ov.memory_usage_mb || 0) + ' MB', desc: 'RAM usage' },
  ];
  
  kpis.forEach(k => {
    const card = document.createElement('div');
    card.className = 'insights-kpi-card';
    card.innerHTML = `
      <div class="insights-kpi-label">${escHtml(k.label)}</div>
      <div class="insights-kpi-value">${escHtml(k.value)}</div>
      <div class="insights-kpi-desc">${escHtml(k.desc)}</div>`;
    grid.appendChild(card);
  });
  sec.appendChild(grid);
  
  if (ov.description) {
    const desc = document.createElement('div');
    desc.className = 'insights-desc-card';
    desc.innerHTML = parseMarkdown(ov.description || '');
    sec.appendChild(desc);
  }
}

/* ── Section 2: Key Findings ── */
function buildSection2Findings(dash, data) {
  const findings = data.key_findings || [];
  if (!findings.length) return;
  
  const sec = createSection(dash, '2', '🔍', 'Key Findings', 'Most important patterns discovered');
  const grid = document.createElement('div');
  grid.className = 'insights-findings-grid';
  
  findings.forEach(f => {
    const type = f.type || 'discovery';
    const card = document.createElement('div');
    card.className = 'insights-finding-card';
    card.innerHTML = `
      <div class="insights-finding-type finding-type-${type}">${escHtml(type)}</div>
      <div class="insights-finding-title">${escHtml(f.title || '')}</div>
      <div class="insights-finding-desc">${escHtml(f.explanation || '')}</div>
      <div class="insights-confidence-badge confidence-${(f.confidence || 'medium').toLowerCase()}">${escHtml(f.confidence || 'MEDIUM')}</div>`;
    grid.appendChild(card);
  });
  sec.appendChild(grid);
}

/* ── Section 3: Statistical Analysis ── */
function buildSection3Stats(dash, data) {
  const stats = data.statistical_analysis || [];
  if (!stats.length) return;
  
  const sec = createSection(dash, '3', '📈', 'Statistical Analysis', 'Mean, median, distribution & variability');
  
  const wrap = document.createElement('div');
  wrap.className = 'insights-stats-wrap';
  let html = `<table class="insights-stats-table"><thead><tr>
    <th>Column</th><th>Count</th><th>Mean</th><th>Median</th><th>Mode</th><th>Std</th><th>Min</th><th>Max</th><th>Q1</th><th>Q3</th><th>Skew</th><th>Variability</th>
  </tr></thead><tbody>`;
  
  stats.forEach(s => {
    html += `<tr>
      <td><strong>${escHtml(s.column)}</strong></td>
      <td>${s.count}</td>
      <td>${s.mean !== null && s.mean !== undefined ? s.mean : '—'}</td>
      <td>${s.median !== null && s.median !== undefined ? s.median : '—'}</td>
      <td>${s.mode !== null && s.mode !== undefined ? s.mode : '—'}</td>
      <td>${s.std !== null && s.std !== undefined ? s.std : '—'}</td>
      <td>${s.min !== null && s.min !== undefined ? s.min : '—'}</td>
      <td>${s.max !== null && s.max !== undefined ? s.max : '—'}</td>
      <td>${s.q1 !== null && s.q1 !== undefined ? s.q1 : '—'}</td>
      <td>${s.q3 !== null && s.q3 !== undefined ? s.q3 : '—'}</td>
      <td>${escHtml(s.skewness || '—')}</td>
      <td>${escHtml(s.variability || '—')}</td>
    </tr>`;
  });
  
  html += '</tbody></table>';
  wrap.innerHTML = html;
  sec.appendChild(wrap);
  
  // Notable stats
  const notable = data.notable_statistics || [];
  if (notable.length) {
    const list = document.createElement('div');
    list.className = 'insights-notable-list';
    notable.forEach(n => {
      const item = document.createElement('div');
      item.className = 'insights-notable-item';
      item.textContent = n;
      list.appendChild(item);
    });
    sec.appendChild(list);
  }
}

/* ── Section 4: Trends & Patterns ── */
function buildSection4Trends(dash, data) {
  const trends = data.trends || [];
  if (!trends.length) {
    // Skip gracefully - no date columns
    return;
  }
  
  const sec = createSection(dash, '4', '📉', 'Trends & Patterns', 'Time-based patterns detected');
  
  trends.forEach(t => {
    const card = document.createElement('div');
    card.className = 'insights-trend-card';
    card.innerHTML = `
      <div class="insights-trend-header">
        <div class="insights-trend-title">${escHtml(t.metric || '')} over ${escHtml(t.date_column || 'time')}</div>
        <div class="insights-trend-direction trend-${t.direction || 'upward'}">${escHtml(t.direction || '')} (${escHtml(t.strength || '')})</div>
      </div>
      <div class="insights-trend-detail">
        Slope: ${t.slope || 0} · ${t.periods || 0} time periods analyzed<br>
        <strong>Direction:</strong> ${escHtml(t.direction || 'stable')} · <strong>Strength:</strong> ${escHtml(t.strength || 'moderate')}
      </div>`;
    
    // Add monthly data preview
    if (t.monthly_data && t.monthly_data.length) {
      const dataList = document.createElement('div');
      dataList.style.marginTop = '8px';
      dataList.style.fontSize = '11px';
      dataList.style.color = 'var(--text-faint)';
      dataList.innerHTML = '<strong>Periods:</strong> ' + t.monthly_data.slice(-5).map(m => `${escHtml(m.period)} (${m.mean})`).join(' · ');
      card.appendChild(dataList);
    }
    
    sec.appendChild(card);
  });
}

/* ── Section 5: Top Performers ── */
function buildSection5Performers(dash, data) {
  const performers = data.top_performers || [];
  if (!performers.length) return;
  
  const sec = createSection(dash, '5', '🏆', 'Top Performers', 'Best entities by key metric');
  
  performers.forEach(p => {
    const card = document.createElement('div');
    card.className = 'insights-performer-card';
    card.innerHTML = `
      <div class="insights-performer-header">
        <div class="insights-performer-title">By ${escHtml(p.category_column || 'category')}</div>
        <div class="insights-performer-sub">Metric: ${escHtml(p.metric || '')} · Total: ${p.total !== null && p.total !== undefined ? p.total.toLocaleString() : 'N/A'}</div>
      </div>
      <div class="insights-performer-list">`;
    
    (p.top_items || []).slice(0, 5).forEach((item, i) => {
      const rank = i + 1;
      card.innerHTML += `
        <div class="insights-performer-item">
          <div class="performer-rank">${rank}</div>
          <div class="performer-name">${escHtml(item.name || '')}</div>
          <div class="performer-value">${item.mean !== null && item.mean !== undefined ? item.mean.toFixed(2) : '—'}</div>
          <div class="performer-pct">${item.contribution_pct !== null && item.contribution_pct !== undefined ? item.contribution_pct.toFixed(1) + '%' : ''}</div>
        </div>`;
    });
    
    card.innerHTML += '</div>';
    sec.appendChild(card);
  });
}

/* ── Section 6: Outliers & Anomalies ── */
function buildSection6Outliers(dash, data) {
  const outliers = data.outliers_anomalies || [];
  if (!outliers.length) return;
  
  const sec = createSection(dash, '6', '⚠️', 'Outliers & Anomalies', 'Statistical outliers detected via IQR');
  
  outliers.forEach(o => {
    const sev = (o.severity || 'low').toLowerCase();
    const card = document.createElement('div');
    card.className = 'insights-outlier-card';
    card.innerHTML = `
      <div class="insights-outlier-header">
        <div class="insights-outlier-title">${escHtml(o.column || '')}</div>
        <div class="insights-outlier-severity severity-${sev}">${escHtml(o.severity || 'LOW')}</div>
      </div>
      <div class="insights-outlier-detail">
        ${o.total_outliers || 0} outliers (${o.outlier_pct || 0}% of values)
      </div>
      <div class="insights-outlier-stats">
        <span class="insights-outlier-stat">▼ Low: ${o.low_outliers || 0}</span>
        <span class="insights-outlier-stat">▲ High: ${o.high_outliers || 0}</span>
        <span class="insights-outlier-stat">Q1: ${o.q1 || '—'}</span>
        <span class="insights-outlier-stat">Q3: ${o.q3 || '—'}</span>
        <span class="insights-outlier-stat">IQR: ${o.iqr || '—'}</span>
      </div>`;
    sec.appendChild(card);
  });
}

/* ── Section 7: Correlation Analysis ── */
function buildSection7Correlations(dash, data) {
  const corr = data.correlation_analysis || {};
  const pos = corr.strong_positive || [];
  const neg = corr.strong_negative || [];
  
  if (!pos.length && !neg.length) return;
  
  const sec = createSection(dash, '7', '🔗', 'Correlation Analysis', 'Strong relationships between variables');
  const grid = document.createElement('div');
  grid.className = 'insights-corr-grid';
  
  if (pos.length) {
    pos.slice(0, 5).forEach(p => {
      const card = document.createElement('div');
      card.className = 'insights-corr-card';
      card.innerHTML = `
        <div class="insights-corr-type corr-positive">Strong Positive</div>
        <div class="insights-corr-pair">${escHtml(p.var1 || '')} ↔ ${escHtml(p.var2 || '')}</div>
        <div class="insights-corr-value">r = ${p.r !== null && p.r !== undefined ? p.r.toFixed(3) : '—'}</div>`;
      grid.appendChild(card);
    });
  }
  
  if (neg.length) {
    neg.slice(0, 5).forEach(n => {
      const card = document.createElement('div');
      card.className = 'insights-corr-card';
      card.innerHTML = `
        <div class="insights-corr-type corr-negative">Strong Negative</div>
        <div class="insights-corr-pair">${escHtml(n.var1 || '')} ↔ ${escHtml(n.var2 || '')}</div>
        <div class="insights-corr-value">r = ${n.r !== null && n.r !== undefined ? n.r.toFixed(3) : '—'}</div>`;
      grid.appendChild(card);
    });
  }
  
  sec.appendChild(grid);
}

/* ── Section 8: Data Quality Report ── */
function buildSection8Quality(dash, data) {
  const q = data.data_quality_report || {};
  const missing = q.missing_values || {};
  const dupes = q.duplicates || {};
  
  const sec = createSection(dash, '8', '🛡️', 'Data Quality Report', 'Completeness and cleanliness');
  const grid = document.createElement('div');
  grid.className = 'insights-quality-grid';
  
  // Missing values card
  const missingCard = document.createElement('div');
  missingCard.className = 'insights-quality-card';
  missingCard.innerHTML = `
    <div class="insights-quality-header">
      <div class="insights-quality-label">Missing Values</div>
      <div class="insights-quality-severity severity-${(missing.columns_with_missing > 0 ? 'medium' : 'low')}">${missing.columns_with_missing > 0 ? 'Has Missing' : 'Clean'}</div>
    </div>
    <div style="font-size:12px;color:var(--text-muted);line-height:1.6;">
      Total missing cells: <strong>${(missing.total_missing_cells || 0).toLocaleString()}</strong><br>
      Columns affected: <strong>${missing.columns_with_missing || 0}</strong> / ${q.total_columns || 0}
    </div>`;
  grid.appendChild(missingCard);
  
  // Missing column details
  if (missing.column_details && missing.column_details.length) {
    missing.column_details.slice(0, 5).forEach(d => {
      const sev = (d.severity || 'low').toLowerCase();
      const card = document.createElement('div');
      card.className = 'insights-quality-card';
      card.innerHTML = `
        <div class="insights-quality-header">
          <div class="insights-quality-label">${escHtml(d.column || '')}</div>
          <div class="insights-quality-severity severity-${sev}">${escHtml(d.severity || 'LOW')}</div>
        </div>
        <div style="font-size:12px;color:var(--text-muted);">
          ${d.total_missing || 0} missing · ${d.missing_pct || 0}% of values
          ${d.nulls > 0 ? ` · ${d.nulls} nulls` : ''}
          ${d.blanks > 0 ? ` · ${d.blanks} blanks` : ''}
        </div>`;
      grid.appendChild(card);
    });
  }
  
  // Duplicates card
  if (dupes.total_duplicate_rows > 0) {
    const dupeCard = document.createElement('div');
    dupeCard.className = 'insights-quality-card';
    dupeCard.innerHTML = `
      <div class="insights-quality-header">
        <div class="insights-quality-label">Duplicate Records</div>
        <div class="insights-quality-severity severity-${(dupes.severity || 'low').toLowerCase()}">${escHtml(dupes.severity || 'LOW')}</div>
      </div>
      <div style="font-size:12px;color:var(--text-muted);">
        ${dupes.total_duplicate_rows || 0} duplicate rows (${dupes.duplicate_pct || 0}% of data)
      </div>`;
    grid.appendChild(dupeCard);
  }
  
  sec.appendChild(grid);
}

/* ── Section 9: Visual Insights ── */
function buildSection9Visuals(dash, data, msgId) {
  const visuals = data.visual_insights || [];
  if (!visuals.length) return;
  
  const sec = createSection(dash, '9', '🎨', 'Visual Insights', 'Auto-generated charts from your data');
  const grid = document.createElement('div');
  grid.className = 'insights-viz-grid';
  
  visuals.forEach((v, i) => {
    const vizId = `${msgId}-viz-${i}`;
    const card = document.createElement('div');
    card.className = 'insights-viz-card';
    card.innerHTML = `
      <div class="insights-viz-title">${escHtml(v.title || 'Chart')}</div>
      <div class="insights-viz-canvas-wrap">
        <canvas id="${vizId}"></canvas>
      </div>
      <div class="insights-viz-explanation">${escHtml(v.title || '')} — ${escHtml(v.chart_type || '')} visualization</div>`;
    grid.appendChild(card);
    
    // Store canvas info for later rendering
    card.dataset.vizId = vizId;
    card.dataset.chartType = v.chart_type || 'bar';
    card.dataset.chartData = JSON.stringify(v.chart_data || {});
  });
  
  sec.appendChild(grid);
}

/* ── Section 10: Business Insights ── */
function buildSection10Business(dash, data) {
  const biz = data.business_insights || [];
  if (!biz.length) return;
  
  const sec = createSection(dash, '10', '💡', 'Business Insights', 'Actionable data-driven recommendations');
  const grid = document.createElement('div');
  grid.className = 'insights-biz-grid';
  
  biz.forEach(b => {
    const pri = (b.priority || 'medium').toLowerCase();
    const card = document.createElement('div');
    card.className = 'insights-biz-card';
    card.innerHTML = `
      <div class="insights-biz-priority priority-${pri}">${escHtml(b.priority || 'MEDIUM')} Priority</div>
      <div class="insights-biz-title">${escHtml(b.title || '')}</div>
      <div class="insights-biz-desc">${escHtml(b.description || '')}</div>
      ${b.action ? `<div class="insights-biz-action">${escHtml(b.action)}</div>` : ''}`;
    grid.appendChild(card);
  });
  
  sec.appendChild(grid);
}

/* ── Section 11: Predictive Opportunities ── */
function buildSection11Predictive(dash, data) {
  const preds = data.predictive_opportunities || [];
  if (!preds.length) return;
  
  const sec = createSection(dash, '11', '🤖', 'Predictive Opportunities', 'Machine Learning potential');
  const grid = document.createElement('div');
  grid.className = 'insights-pred-grid';
  
  preds.forEach(p => {
    const fea = (p.feasibility || 'medium').toLowerCase();
    const feaColor = fea === 'high' ? '#86EFAC' : fea === 'medium' ? '#FCD34D' : '#FCA5A5';
    const card = document.createElement('div');
    card.className = 'insights-pred-card';
    card.innerHTML = `
      <div class="insights-pred-title">${escHtml(p.title || '')}</div>
      <div class="insights-pred-desc">${escHtml(p.description || '')}</div>
      ${p.target ? `<div style="font-size:11px;color:var(--text-faint);margin-top:4px;">Target: <strong>${escHtml(p.target)}</strong></div>` : ''}
      <div class="insights-pred-feasibility" style="color:${feaColor}">Feasibility: ${escHtml(p.feasibility || 'MEDIUM')}</div>`;
    grid.appendChild(card);
  });
  
  sec.appendChild(grid);
}

/* ── Section 12: Executive Summary ── */
function buildSection12Executive(dash, data) {
  const exec = data.executive_summary || [];
  if (!exec.length) return;
  
  const sec = createSection(dash, '12', '📋', 'AI Executive Summary', 'Key takeaways and recommendations');
  const list = document.createElement('div');
  list.className = 'insights-exec-list';
  
  exec.forEach((point, i) => {
    const item = document.createElement('div');
    item.className = 'insights-exec-item';
    item.innerHTML = `
      <div class="insights-exec-bullet">${i + 1}</div>
      <div>${parseMarkdown(point || '')}</div>`;
    list.appendChild(item);
  });
  
  sec.appendChild(list);
}

/* ── Helper: Create a section container ── */
function createSection(parent, num, icon, title, subtitle) {
  const section = document.createElement('div');
  section.className = 'insights-section';
  section.innerHTML = `
    <div class="insights-section-header">
      <div class="insights-section-icon">${icon}</div>
      <div>
        <div class="insights-section-title">${title}</div>
        <div class="insights-section-subtitle">${subtitle}</div>
      </div>
    </div>`;
  parent.appendChild(section);
  return section;
}

/* ── Render Insight Charts (after DOM ready) ── */
function renderInsightCharts(data, msgId) {
  const visuals = data.visual_insights || [];
  visuals.forEach((v, i) => {
    const vizId = `${msgId}-viz-${i}`;
    const canvas = document.getElementById(vizId);
    if (!canvas) return;
    
    const chartData = v.chart_data || {};
    const chartType = v.chart_type || 'bar';
    
    let spec = null;
    if (chartType === 'bar' || chartType === 'histogram') {
      const labels = chartData.labels || [];
      const series = chartData.series?.[0]?.data || [];
      if (labels.length && series.length) {
        spec = { plotType: 'bar', title: v.title || '', xLabel: v.x_label || '', yLabel: v.y_label || '', labels, series: [{ label: 'Value', data: series, labels }] };
      }
    } else if (chartType === 'line') {
      const labels = chartData.labels || [];
      const series = chartData.series?.[0]?.data || [];
      if (labels.length && series.length) {
        spec = { plotType: 'line', title: v.title || '', xLabel: v.x_label || '', yLabel: v.y_label || '', labels, series: [{ label: 'Value', data: series, labels }] };
      }
    } else if (chartType === 'pie') {
      const labels = chartData.labels || [];
      const series = chartData.series?.[0]?.data || [];
      if (labels.length && series.length) {
        spec = { plotType: 'pie', title: v.title || '', labels, series: [{ label: 'Distribution', data: series, labels }] };
      }
    } else if (chartType === 'heatmap') {
      // Heatmaps are data tables, skip Chart.js rendering
      return;
    } else if (chartType === 'box') {
      return;
    }
    
    if (spec) {
      try {
        _renderChart(vizId, spec);
      } catch (e) {
        // Silently skip chart render errors
      }
    }
  });
}


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
          <button class="toolbar-btn" onclick="toggleDlMenu('${msgId}')">⬇ Export ▾</button>
          <div class="dl-menu" id="dlmenu-${msgId}">
            <button class="dl-opt" onclick="dlFmt('xlsx')">Excel (.xlsx)</button>
            <button class="dl-opt" onclick="dlFmt('pdf')">📄 PDF (.pdf)</button>
            <button class="dl-opt" onclick="dlFmt('docx')">📝 Word (.docx)</button>
            <button class="dl-opt" onclick="dlFmt('png')">🖼 Image (.png)</button>
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
    recs.push({ type: 'line',      icon: '📈', label: 'Line Chart' });
    recs.push({ type: 'area',      icon: '🏔', label: 'Area Chart' });
  } else if (catCols.length >= 1 && numCols.length >= 1) {
    const uniqueVals = catCols.length; // approximate
    if (/pie|proportion|share|percent|distribution/i.test(q) || catCols.length === 1) {
      recs.push({ type: 'pie',   icon: '🥧', label: 'Pie Chart' });
      recs.push({ type: 'donut', icon: '🍩', label: 'Donut Chart' });
      recs.push({ type: 'bar',   icon: '📊', label: 'Bar Chart' });
    } else {
      recs.push({ type: 'bar',   icon: '📊', label: 'Bar Chart' });
      recs.push({ type: 'pie',   icon: '🥧', label: 'Pie Chart' });
      recs.push({ type: 'donut', icon: '🍩', label: 'Donut Chart' });
    }
  } else if (numCols.length >= 2) {
    recs.push({ type: 'scatter',   icon: '⚡', label: 'Scatter Plot' });
    recs.push({ type: 'histogram', icon: '📉', label: 'Histogram' });
  } else if (numCols.length >= 1) {
    recs.push({ type: 'histogram', icon: '📉', label: 'Histogram' });
    recs.push({ type: 'bar',       icon: '📊', label: 'Bar Chart' });
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
          📊 <span>${escHtml(spec.title || chartType + ' Chart')}</span>
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
    state.chartMap[msgId + '-inline'] = _renderChart(cid, spec);
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
  state.chartMap[msgId + '-inline'] = _renderChart(cid, spec);
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
    alert('Please wait while I load a data sample for visualization...');
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
  vizPreviewChart.style.display = 'block';

  requestAnimationFrame(() => {
    state.vizModal.chart = _renderChart('vizModalCanvas', spec);
  });
});

/* ═══════════════════════════════════════════════════════════════
   SPEC BUILDERS
════════════════════════════════════════════════════════════════ */
function buildSpecFromDataWithAxes(chartType, columns, rows, xCol, yCol, agg) {
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
    const col  = yCol || xCol;
    const vals = rows.map(r => Number(r[col])).filter(v => !isNaN(v));
    return buildHistogramSpec(col, vals);
  }

  // Aggregate xCol → yCol
  const aggMap = {};
  rows.forEach(r => {
    const k = String(r[xCol] ?? '(blank)');
    const v = Number(r[yCol]) || 0;
    if (!aggMap[k]) aggMap[k] = { sum: 0, count: 0, min: Infinity, max: -Infinity, vals: [] };
    aggMap[k].sum   += v;
    aggMap[k].count += 1;
    aggMap[k].min    = Math.min(aggMap[k].min, v);
    aggMap[k].max    = Math.max(aggMap[k].max, v);
    aggMap[k].vals.push(v);
  });

  const getValue = (entry) => {
    switch (agg) {
      case 'avg':   return entry.count ? entry.sum / entry.count : 0;
      case 'count': return entry.count;
      case 'max':   return entry.max;
      case 'min':   return entry.min;
      default:      return entry.sum;
    }
  };

  const sorted = Object.entries(aggMap).sort((a, b) => getValue(b[1]) - getValue(a[1])).slice(0, 20);
  const labels = sorted.map(e => e[0]);
  const data   = sorted.map(e => +getValue(e[1]).toFixed(2));

  return {
    plotType: chartType,
    title: `${agg.toUpperCase()}(${yCol}) by ${xCol}`,
    xLabel: xCol, yLabel: yCol,
    labels,
    series: [{ label: yCol, data, labels }]
  };
}

function buildSpecFromData(chartType, columns, rows, numCols, catCols) {
  const MAX = 20;
  const limited = rows.slice(0, MAX);

  if (chartType === 'scatter' && numCols.length >= 2) {
    const xc = numCols[0], yc = numCols[1];
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

  const agg = {};
  rows.forEach(r => {
    const k = String(r[xCol] ?? '(blank)');
    const v = Number(r[yCol]) || 0;
    agg[k] = (agg[k] || 0) + v;
  });
  const sorted = Object.entries(agg).sort((a, b) => b[1] - a[1]).slice(0, 15);
  const labels = sorted.map(e => e[0]);
  const data   = sorted.map(e => e[1]);

  return {
    plotType: chartType,
    title: `${yCol} by ${xCol}`,
    xLabel: xCol, yLabel: yCol,
    labels,
    series: [{ label: yCol, data, labels }]
  };
}

function buildHistogramSpec(col, vals) {
  const min  = Math.min(...vals), max = Math.max(...vals);
  const bins = Math.min(15, Math.ceil(Math.sqrt(vals.length)));
  const binSize = (max - min) / bins || 1;
  const counts  = Array(bins).fill(0);
  const labels  = [];
  for (let i = 0; i < bins; i++)
    labels.push(`${(min + i * binSize).toFixed(1)}–${(min + (i+1) * binSize).toFixed(1)}`);
  vals.forEach(v => {
    const idx = Math.min(Math.floor((v - min) / binSize), bins - 1);
    counts[idx]++;
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
    if (!res.ok) { console.error(data.error); return; }
    renderChartInMsg(msgId, data.spec, 'chart-' + msgId);
  } catch (err) {
    console.error('switchVizType error:', err);
  }
}

/* ═══════════════════════════════════════════════════════════════
   CHART.JS RENDERERS
════════════════════════════════════════════════════════════════ */
const CHART_COLORS = [
  '#2563EB','#3B82F6','#60A5FA','#F59E0B','#EF4444',
  '#8B5CF6','#EC4899','#14B8A6','#F97316','#6366F1',
  '#0EA5E9','#D946EF','#84CC16','#F43F5E','#06B6D4',
];

function renderChartInMsg(msgId, spec, canvasId) {
  if (!spec) return;
  const existing = state.chartMap[msgId];
  if (existing) { existing.destroy(); delete state.chartMap[msgId]; }
  const chart = _renderChart(canvasId, spec);
  if (chart) state.chartMap[msgId] = chart;
}

function _renderChart(canvasId, spec) {
  if (!spec) return null;
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;

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

  const dataset = {
    label:           series?.label || spec.yLabel || 'Data',
    data:            values,
    backgroundColor: isPie ? CHART_COLORS : 'rgba(37,99,235,0.18)',
    borderColor:     isPie ? CHART_COLORS.map(c => c + 'cc') : '#2563EB',
    borderWidth:     2,
    pointRadius:     chartJsType === 'scatter' ? 4 : 3,
    fill:            isArea ? true : undefined,
    tension:         chartJsType === 'line' ? 0.35 : undefined,
  };

  const useLabels = !isPie && chartJsType !== 'scatter';

  return new Chart(canvas.getContext('2d'), {
    type: chartJsType,
    data: {
      labels:   useLabels ? labels : undefined,
      datasets: [dataset],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      animation: { duration: 450 },
      plugins: {
        legend: {
          display: isPie,
          position: 'bottom',
          labels: { boxWidth: 12, font: { size: 11 } },
        },
        title: {
          display: !!spec.title,
          text:    spec.title || '',
          font:    { size: 13, weight: '600' },
          color:   '#374151',
          padding: { bottom: 12 },
        },
        tooltip: {
          callbacks: {
            label: ctx => {
              const v = ctx.parsed?.y ?? ctx.parsed;
              return ` ${ctx.dataset.label}: ${typeof v === 'number' ? v.toLocaleString() : v}`;
            }
          }
        }
      },
      scales: isPie ? {} : {
        x: {
          ticks: { maxRotation: 35, font: { size: 11 }, color: '#6B7280', maxTicksLimit: 14 },
          grid:  { color: '#F3F4F6' },
        },
        y: {
          beginAtZero: true,
          ticks: { font: { size: 11 }, color: '#6B7280',
            callback: v => typeof v === 'number' && v >= 1000 ? v.toLocaleString() : v },
          grid:  { color: '#F3F4F6' },
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

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function scrollToBottom() {
  chatMain.scrollTo({ top: chatMain.scrollHeight, behavior: 'smooth' });
}

/* ═══════════════════════════════════════════════════════════════
   MARKDOWN PARSER (unchanged)
════════════════════════════════════════════════════════════════ */
function parseMarkdown(md) {
  if (!md) return '';
  let html = md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

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
