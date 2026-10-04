# Diamond Scorer -- container image for hosting the web version.
FROM python:3.12-slim

# Keep Python output unbuffered and skip .pyc clutter in the image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Store the SQLite database on a mountable volume so data survives restarts.
    BASEBALL_DB=/data/baseball.db

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the application.
COPY backend ./backend
COPY frontend ./frontend
COPY run_web.py ./

# Persist the database here (mount a named volume / platform disk at /data).
RUN mkdir -p /data
VOLUME ["/data"]

# Platforms (Render/Railway/Fly/etc.) inject $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# SQLite is single-writer, so run a single worker to avoid write contention.
# The container binds 0.0.0.0 because the hosting platform's proxy fronts it;
# set DIAMONDSCORER_AUTH=user:pass (or protect it at the proxy) before exposing
# it publicly -- the app itself has no login.
CMD ["sh", "-c", "gunicorn backend.server:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-8000} --workers 1 --timeout 120"]
