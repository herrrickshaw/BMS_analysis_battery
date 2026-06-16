# ─────────────────────────────────────────────────────────────────────────────
# Multi-stage Dockerfile for the React/Vite frontend.
#
# "Multi-stage" means we use two separate FROM instructions in one file.
# Stage 1 (build): uses a full Node.js image to compile the React app into
#   static HTML/CSS/JS files (the "dist" folder).
# Stage 2 (serve): uses a tiny nginx image to serve those static files.
#   The Node.js compiler and all node_modules are DISCARDED at this point —
#   the final image only contains nginx + the compiled output, so it's tiny.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build ───────────────────────────────────────────────────────────
# "AS build" gives this stage a name so Stage 2 can reference its output.
FROM node:20-slim AS build

WORKDIR /app

# Copy package files first (same caching trick as the backend Dockerfile).
# npm ci is like npm install but stricter: it reads package-lock.json exactly,
# giving reproducible installs in CI and Docker.
COPY package*.json ./
RUN npm ci

# Copy source code and compile.
# "npm run build" runs Vite, which bundles and minifies all JS/CSS/HTML into
# the dist/ folder — a set of static files ready for any web server.
COPY . .
RUN npm run build

# ── Stage 2: Serve ───────────────────────────────────────────────────────────
# nginx:alpine is an extremely small (< 10 MB) web server image.
FROM nginx:alpine

# Grab only the compiled dist/ output from the build stage above.
# Everything else (Node.js, node_modules, source files) is left behind.
COPY --from=build /app/dist /usr/share/nginx/html

# Drop in our custom nginx config (see nginx.conf in this folder).
# This replaces nginx's default config with one that knows how to:
#   1. Proxy /api/ requests to the backend
#   2. Handle React's client-side routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

# nginx listens on port 80 by default.
EXPOSE 80

# Health check: wget hits the nginx root.  If nginx is up, we get a 200.
# (We use wget instead of curl because nginx:alpine has wget but not curl.)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost/ > /dev/null 2>&1 || exit 1
