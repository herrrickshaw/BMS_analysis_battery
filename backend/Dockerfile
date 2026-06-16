# ─────────────────────────────────────────────────────────────────────────────
# What is a Dockerfile?
#   A Dockerfile is a recipe that tells Docker how to package your app into a
#   "container image" — a self-contained box that includes Python, all your
#   libraries, and your code.  Anyone with Docker installed can run this image
#   and get the exact same environment, regardless of their operating system.
# ─────────────────────────────────────────────────────────────────────────────

# Step 1 — Choose a base image.
#   We start from an official Python 3.12 image.  "slim" means it's a smaller
#   version that strips out things we don't need (compilers, docs, etc.),
#   keeping the final image size small.
FROM python:3.12-slim

# Step 2 — Set the working directory inside the container.
#   All subsequent commands (COPY, RUN, CMD) will be relative to /app.
#   Think of it as "cd /app" — if /app doesn't exist, Docker creates it.
WORKDIR /app

# Step 3 — Install OS-level system packages.
#   We only need `curl` here — it's used by the HEALTHCHECK below.
#   --no-install-recommends keeps the install lean.
#   We delete the apt cache afterwards so it doesn't bloat the image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Step 4 — Install Python dependencies BEFORE copying the rest of the code.
#   Why this order?  Docker caches each step as a "layer".
#   requirements.txt rarely changes, so Docker can reuse the cached pip install
#   layer on rebuilds — making subsequent builds much faster.
#   If we copied all files first, any code change would bust the pip cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 5 — Copy the rest of the backend source code into the container.
#   The .dockerignore file (in this same directory) lists things to exclude,
#   like __pycache__, .env files, and the uploads/ folder.
COPY . .

# Step 6 — Document which port this container listens on.
#   EXPOSE doesn't actually open the port — it's just metadata.
#   docker-compose.yml maps this port to a port on your machine.
EXPOSE 8000

# Step 7 — Tell Docker how to check if the app is healthy.
#   Docker will curl /healthz every 30 seconds.  If it fails 3 times in a row,
#   the container is marked "unhealthy" and docker-compose can restart it.
#   start_period=20s gives the app time to fully boot before checks begin.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Step 8 — The command to run when the container starts.
#   uvicorn is the ASGI server that runs our FastAPI app.
#   --host 0.0.0.0 means "accept connections from any network interface inside
#   the container" — required so traffic from outside can reach it.
#   In development we use --reload, but NOT here: reloading inside a container
#   is wasteful and can cause issues with file watchers.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
