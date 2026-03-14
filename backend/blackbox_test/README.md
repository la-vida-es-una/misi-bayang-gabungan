# Backend

## Blackbox testing UI (Streamlit)

This repository includes a manual blackbox console for end-to-end checking of the real simulation + MCP tool flow.

### File

- `app_blackbox_streamlit.py`

### Install dev dependencies

```bash
cd backend
uv sync --group dev
```

### Run

```bash
cd backend
uv run streamlit run blackbox_test/streamlit.py
```

### What you can test

- Reset world with deterministic seed and scenario parameters
- Step simulation ticks
- Move a drone, run thermal scan, return to base
- Broadcast alerts
- Inspect live mission state (`mission://state`) and known grid map
