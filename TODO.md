# TODO — AI Insights Module Enhancement (backend/services/insights only)

## Plan Steps
- [ ] Inspect current AI insights payload shape and how frontend renders it.
- [ ] Enhance backend insights_engine.py to meet all AI Insights requirements:
  - [ ] Always use currently loaded dataset (already via active_dataset_store) — ensure robustness.
  - [ ] Automatically detect dataset type, column types (numeric/categorical/date), numerical/categorical/date columns.
  - [ ] Relationship detection between fields (correlations + additional relationship cues for categorical pairs).
  - [ ] Key findings: ensure at least 6–10 insight cards with title/explanation/confidence.
  - [ ] Statistical analysis: include mean/median/mode/std/variance/min/max/quartiles/skewness/variability; highlight notable stats.
  - [ ] Trends & patterns: improve monthly/weekly detection from date columns.
  - [ ] Top performers: improve for categorical columns and handle cases like top categories/regions/products/entities.
  - [ ] Outlier & anomaly detection: include suspicious records summary.
  - [ ] Data quality report: include invalid/constant/empty columns + recommended fixes.
  - [ ] Visual insights metadata: return chart-ready data for bar/pie/line/histogram/heatmap/scatter.
  - [ ] Business insights + predictive opportunities: make them data-driven and domain-agnostic.
  - [ ] Executive summary: 5–10 bullet points.
  - [ ] Performance: sample for heavy computations when df > 100k.
  - [ ] Caching: memoize per-request computations where possible.
  - [ ] Failsafes: empty dataset / insufficient data messages never crash.
- [ ] Run backend unit smoke test / minimal execution of generate_insights() locally.
- [ ] Verify no other modules are modified.

