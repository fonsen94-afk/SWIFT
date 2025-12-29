# Dockerfile for Streamlit deployment of Swift Alliance app
# Builds a minimal container running the Streamlit UI.
# Usage:
#   docker build -t swift-alliance-streamlit:latest .
#   docker run -p 8501:8501 --rm swift-alliance-streamlit:latest

FROM python:3.11-slim

# OS packages for optional functionality and XML parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy project files
COPY . /app

# Install Python deps
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expose Streamlit port
EXPOSE 8501

# Ensure assets dir exists (persisted files can be mounted)
RUN mkdir -p /app/assets /app/schemas

# Streamlit config: run headless and bind to 0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLE_CORS=false
ENV STREAMLIT_SERVER_PORT=8501

# Default command
CMD ["streamlit", "run", "swift_alliance_streamlit.py", "--server.port=8501", "--server.address=0.0.0.0"]