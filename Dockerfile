FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (docker client needs some libs)
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy All Repository Code
COPY . .
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

# Set Python Path
ENV PYTHONPATH=/app

# Default Command
CMD ["./entrypoint.sh"]
