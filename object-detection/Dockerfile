# Use Python 3.11 slim image as base
ARG PYTHON_VERSION=3.11.7
FROM python:${PYTHON_VERSION}-slim AS base

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies required for OpenCV and other libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create a non-privileged user with home directory for cache
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/home/appuser" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies with CPU-only PyTorch (much smaller)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip

# Download YOLO12 model directly from GitHub releases
RUN wget -q https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo12n.pt -O /app/yolo12n.pt && \
    chmod 644 /app/yolo12n.pt && \
    ls -lh /app/yolo12n.pt

# Copy application code (only necessary files)
COPY --chown=appuser:appuser src/ ./src/

# Create cache directories and set permissions
RUN mkdir -p /home/appuser/.config/matplotlib /home/appuser/.config/Ultralytics && \
    chown -R appuser:appuser /home/appuser /app

# Switch to non-privileged user
USER appuser

# Expose the application port
EXPOSE 8000

# Set environment variables
ENV PORT=8000
ENV CONFIDENCE_THRESHOLD=0.25
ENV IOU_THRESHOLD=0.45
ENV MAX_DETECTIONS=300
ENV MPLCONFIGDIR=/home/appuser/.config/matplotlib
ENV YOLO_CONFIG_DIR=/home/appuser/.config/Ultralytics

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run the application
CMD ["python", "src/server.py"]
