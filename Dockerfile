FROM python:3.12-slim

# libgomp est nécessaire à LightGBM
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml config.yaml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY site ./site

# Par défaut : mode démo (données fictives générées et modèle entraîné au build).
# Pour les données réelles, montez data/ et models/ produits par `radar ingest/build/train`.
ARG DEMO=1
ENV RADAR_DEMO=${DEMO}
# Les hébergeurs mutualisés annoncent plus de cœurs qu'ils n'en allouent :
# on limite les threads pour éviter l'engorgement (build et service).
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    LOKY_MAX_CPU_COUNT=1
RUN if [ "$DEMO" = "1" ]; then python -m radar demo && python -m radar build && python -m radar train; fi

EXPOSE 8000
CMD ["sh", "-c", "uvicorn radar.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
