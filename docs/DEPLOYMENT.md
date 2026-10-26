# Deployment

Portfolio Lab is a single Streamlit process backed by one SQLite file. Two deployment routes are documented: Docker (verified) and Streamlit Community Cloud (needs one extra step, below).

> **Simulation only. NOT investment advice. Virtual money, no real brokerage connection.**

## Docker (local machine or any VM)

Requires Docker Desktop or Docker Engine with Compose.

```bash
docker compose up --build
```

Open <http://localhost:8501>.

What happens on start (`docker-entrypoint.sh`):

1. If `data/portfolio.db` is missing or has no prices, `python -m src.data_pipeline` cleans the supplied CSV, uses `data/market_cache.csv` if it is complete, otherwise downloads about five years of NSE history with yfinance, and loads one price source into SQLite.
2. `python -m src.signals` recomputes SMA/RSI signals.
3. Streamlit starts on port 8501 as non-root UID 1000, with a health check on `/_stcore/health`.

`./data` is bind-mounted, so the virtual portfolio and the market cache survive restarts.

| Task | Command |
| --- | --- |
| Stop | `docker compose down` |
| Reset the virtual portfolio | stop the container, delete `data/portfolio.db`, start again |
| Refresh market data | stop the container, delete `data/market_cache.csv` and `data/portfolio.db`, start again |
| Check health | `docker inspect --format "{{.State.Health.Status}}" <container>` |

Without network access the pipeline falls back to the supplied 500-row synthetic CSV. The app then withholds annualised risk and ML metrics (fewer than 252 observations).

## Streamlit Community Cloud

Community Cloud runs `streamlit run` only. It does **not** run `docker-entrypoint.sh`, and `data/portfolio.db` is git-ignored, so a plain deploy of this repository starts with *"The database is not ready."* Seed the database once and commit it:

1. Build a fresh database locally (see Quick Start in the README), with no virtual trades in it:

   ```bash
   rm -f data/portfolio.db   # PowerShell: Remove-Item data\portfolio.db -ErrorAction SilentlyContinue
   python -m src.data_pipeline
   python -m src.signals
   ```

2. Force-add the ignored file (about 3 MB) and push:

   ```bash
   git add -f data/portfolio.db
   git commit -m "chore: add seeded demo database for Streamlit Cloud"
   git push
   ```

3. At <https://share.streamlit.io>, choose **Create app**, pick the repository and branch `main`, and set **Main file path** to `app/main.py`.
4. Under **Advanced settings**, choose **Python 3.11**, the version the pins in `requirements.txt` were tested on.
5. Deploy, then put the app URL into the `[Live Demo](YOUR_STREAMLIT_URL)` link in the README.

Limits to know before sharing the link:

- **One shared portfolio.** The app uses a single portfolio (`id = 1`). Every visitor sees and changes the same cash and holdings.
- **Ephemeral storage.** The container filesystem resets on redeploy or reboot, so virtual trades are lost and the database returns to the committed seed.
- **Snapshot prices.** Prices are those in the committed database; the app never refreshes them on its own, and the dashboard labels quotes as cached.
- **No automatic refresh.** To refresh data, rebuild the database locally and commit it again.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| "The database is not ready" | `data/portfolio.db` missing or empty | Run `python -m src.data_pipeline` (local) or commit a seeded database (Cloud) |
| Risk/ML cards show "—" | Fewer than 252 observations, so the supplied synthetic data is active | Run the pipeline with network access to download real history |
| `docker compose` cannot reach the daemon | Docker Desktop not running | Start Docker Desktop and retry |
| Port 8501 already in use | Another Streamlit instance | Change the left side of `8501:8501` in `docker-compose.yml` |
