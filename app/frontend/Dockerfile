# DocuChat React frontend — static build served by an unprivileged nginx.
#
# The SPA talks to a same-origin "/api" prefix; the Ingress routes that prefix
# to the backend Service, so no CORS and no API hostname baked into the bundle.

# --- build stage ----------------------------------------------------------- #
FROM node:20-alpine AS build

WORKDIR /src

ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Same-origin API prefix, and base="/" instead of the GitHub Pages "/docuchat/".
ENV VITE_API_URL=/api
RUN npm run build -- --base=/

# --- runtime stage --------------------------------------------------------- #
# nginx-unprivileged listens on 8080 and runs as uid 101 — no root, no
# capabilities needed, which is what the chart's securityContext requires.
FROM nginxinc/nginx-unprivileged:1.27-alpine

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html

EXPOSE 8080
