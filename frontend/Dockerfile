# ─────────────────────────────────────────────────────────────────────────────
# TruthStream Frontend — Dockerfile
# Two-stage: Node build → nginx serve
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

# Install dependencies first (cached layer) — only invalidated when package*.json changes
COPY package.json package-lock.json ./
RUN npm ci --prefer-offline

# Copy source
COPY . .

# Build-time env var: the base URL the frontend uses for API calls.
# In Docker Compose, nginx proxies /api → backend, so we use relative paths (empty string).
# Override at build time if deploying to a CDN or external domain.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ── Stage 2: Serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Remove the default nginx page
RUN rm -rf /usr/share/nginx/html/*

# Copy the Vite build output
COPY --from=build /app/dist /usr/share/nginx/html

# Copy our custom nginx config (with API proxy and SSE headers)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
