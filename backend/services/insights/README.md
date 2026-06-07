# Insights Engine

This folder contains the enterprise AI Insights engine.

- `insights_engine.py`: deterministic dataset-wide profiling that returns structured insight cards with computed evidence and chart-ready JSON.

Frontend `/insights` endpoint expects insight objects with:
- `id`, `category`, `title`, `summary`, `explanation`
- `impact`, `confidence`
- `chart_type`, `chart_data`
- `evidence`, `recommendation`

All insight evidence must be computed from the dataset (no fabricated numbers).

