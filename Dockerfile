FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HCL_DATA_DIR=/app/data \
    HCL_DB_PATH=/app/data/portfolio.db

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    python -c "import pandas as pd, pyarrow as pa; pa.Table.from_pandas(pd.DataFrame({'value': [1]}))" && \
    pip check && \
    groupadd --gid 1000 app && useradd --uid 1000 --gid app --home /app app

COPY app ./app
COPY src ./src
COPY .streamlit ./.streamlit
COPY data ./data
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x docker-entrypoint.sh && chown -R app:app /app

USER app
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)" || exit 1
ENTRYPOINT ["./docker-entrypoint.sh"]
