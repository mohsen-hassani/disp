# syntax=docker/dockerfile:1

FROM node:22-alpine AS builder

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
# Full install, not --prod: the build toolchain itself (vite, typescript,
# @tanstack/router-plugin, tailwindcss, vite-plugin-pwa, ...) lives in
# devDependencies. Only the runtime stage below excludes node_modules
# entirely — that's where this repo's actual builder/runtime split lives,
# not here.
RUN pnpm install --frozen-lockfile

COPY index.html tailwind.config.ts tsconfig.json tsconfig.node.json vite.config.ts ./
COPY public ./public
COPY src ./src
RUN pnpm build

FROM nginx:1.27-alpine AS runtime

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf security-headers.conf /etc/nginx/

# Non-root: reuse the nginx image's own built-in `nginx` user (uid 101)
# rather than creating a new one (unlike the root Dockerfile, whose base
# Python image ships no such user at all).
RUN chown -R nginx:nginx /var/cache/nginx /usr/share/nginx/html \
    && touch /var/run/nginx.pid \
    && chown nginx:nginx /var/run/nginx.pid

USER nginx

# Non-root nginx can't bind :80 — see nginx.conf's `listen` directive and
# docker-compose.yml's matching `loadbalancer.server.port=8080` label;
# invisible externally, Traefik still serves the public site on 443/80.
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:8080/ || exit 1
