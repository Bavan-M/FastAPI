# ============================================================
# STAGE 1 — Builder
# Install dependencies, compile packages
# This stage is discarded after build
# ============================================================

FROM python:3.12-slim AS builder 

# Set environment variables
# PYTHONDONTWRITEBYTECODE → no .pyc files (saves space)
# PYTHONUNBUFFERED → logs appear immediately (not buffered)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Now move to build folder
WORKDIR /build

# Copy ONLY requirements first
# Docker caches each layer — if requirements.txt hasn't changed,
# this expensive pip install step is skipped on rebuild
# Copies to /build/ (not root)
COPY requirements.txt .

# Update pip to the latest version, then install all Python packages into a custom folder called /build/packages.
# Install dependencies into /build/wheels
# --no-deps → don't install sub-dependencies (already in requirements)
RUN pip install --upgrade pip && \
    pip install --prefix=/build/packages -r requirements.txt


# ============================================================
# STAGE 2 — Runner
# Minimal image with only what's needed to run
# ============================================================

FROM python:3.12-slim AS runner 

# Hey Python, my code lives in the /app folder. Don't forget to look there!
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Create non-root user — security best practice
# Never run containers as root
# groupadd --gid 1000 appuser ==> Make a team called appuser with groupid=1000
# && ==> then
# useradd --uid 1000 --gid appuser ==> Make a person called appuser in that team with userid=1000
# --shell /bin/bash ==> Let them use the terminal
# --create-home ==> Creates home folder /home/appuser
# appuser ==> The username
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy installed packages from builder stage
# ONLY the packages — not pip, not build tools
# Take the packages from the builder stage (located at /build/packages) and paste them into the runner stage at /usr/local
COPY --from=builder /build/packages /usr/local

# Copy application code
# Copy my application code from the app/ folder on my computer into the container's /app/ folder, and make appuser the owner of these files
# chown change owner
COPY --chown=appuser:appuser app/ ./app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check — Docker monitors this
# Docker will regularly check if my app is still alive and working properly
# --interval → check every 30s
# --timeout  → fail if no response in 10s
# --retries  → mark unhealthy after 3 failures
# why httpx because you are installed in requirements.txt file 

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit=1

# Run the app
# Use exec form (JSON array) not shell form
# exec form → signals go directly to Python process (enables graceful shutdown)
# shell form → signals go to shell wrapper (graceful shutdown broken)
# When container starts, run FastAPI with 1 worker on port 8000, accept connections from anywhere, and trust proxy headers for real user IPs
CMD ["uvicorn","app.main:app", \
    "--host","0.0.0.0", \
    "--port","8000", \
    "--workers","1", \
    "--proxy-headers", \
    "--forwarded-allow-ips","*"]
