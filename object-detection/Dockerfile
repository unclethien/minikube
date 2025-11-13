# Optimized single-stage build with aggressive cleanup
FROM python:3.11.7-slim

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies and wget in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-privileged user
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/home/appuser" \
    --shell "/sbin/nologin" \
    --uid "10001" \
    appuser

# Copy requirements
COPY requirements.txt .

# Install Python packages with CPU-only PyTorch and clean up in one layer
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt && \
    rm requirements.txt && \
    find /usr/local/lib/python3.11 -type d -name "tests" -o -name "test" -o -name "__pycache__" | xargs rm -rf && \
    find /usr/local/lib/python3.11 -type f -name "*.pyc" -o -name "*.pyo" | xargs rm -f && \
    rm -rf /root/.cache

# Download YOLO12 model and clean up
RUN wget -q https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo12n.pt -O /app/yolo12n.pt && \
    chmod 644 /app/yolo12n.pt && \
    apt-get remove -y wget && \
    apt-get autoremove -y

# Copy application code
COPY --chown=appuser:appuser src/ ./src/

# Create cache directories
RUN mkdir -p /home/appuser/.config/matplotlib /home/appuser/.config/Ultralytics && \
    chown -R appuser:appuser /home/appuser /app

# Switch to non-privileged user
USER appuser

# Expose port
EXPOSE 8000

# Set environment variables
ENV PORT=8000 \
    CONFIDENCE_THRESHOLD=0.25 \
    IOU_THRESHOLD=0.45 \
    MAX_DETECTIONS=300 \
    MPLCONFIGDIR=/home/appuser/.config/matplotlib \
    YOLO_CONFIG_DIR=/home/appuser/.config/Ultralytics

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run the application
CMD ["python", "src/server.py"]
