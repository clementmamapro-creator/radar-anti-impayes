FROM python:3.12-slim

# libgomp est nécessaire à LightGBM
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml config.yaml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY site ./site

# Par défaut : données réelles. Le paquet de service (base allégée + modèle) est
# publié chaque semaine par le pipeline dans la release GitHub « modele ».
# DEMO=1 : données fictives générées et modèle entraîné au build (local, CI).
ARG DEMO=0
ARG MODEL_URL=https://github.com/clementmamapro-creator/radar-anti-impayes/releases/download/modele/acquit-serve.tar.gz
ENV RADAR_DEMO=${DEMO}
# Les hébergeurs mutualisés annoncent plus de cœurs qu'ils n'en allouent :
# on limite les threads pour éviter l'engorgement (build et service).
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    LOKY_MAX_CPU_COUNT=1
RUN if [ "$DEMO" = "1" ]; then python -m radar demo && python -m radar build && python -m radar train; \
    else python -m radar fetch "$MODEL_URL"; fi

EXPOSE 8000
CMD ["sh", "-c", "uvicorn radar.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
