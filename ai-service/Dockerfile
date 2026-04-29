# Use the slim variant to keep the image small.
# 3.12 is the target Python version for all AI library compatibility.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies as a separate layer BEFORE copying application code.
# Docker caches layers — if requirements.txt hasn't changed, this layer is
# reused on rebuild even if main.py changed. This makes rebuilds much faster.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code.
# In development this layer is overridden by the volume mount in docker-compose,
# so changes to .py files are picked up by uvicorn --reload without a rebuild.
COPY . .

# Expose the port FastAPI listens on
EXPOSE 8001

# --reload watches for file changes and restarts the server automatically.
# This only matters in development — the volume mount in docker-compose.ai.yml
# makes local file edits instantly visible inside the container.
# In production, remove --reload and pin workers instead.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
