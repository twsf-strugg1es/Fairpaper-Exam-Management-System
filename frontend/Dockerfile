FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Baked into the static build; set per environment at build time
ARG REACT_APP_API_URL=http://localhost:8000
ENV REACT_APP_API_URL=$REACT_APP_API_URL
# Optional error reports: the web project's DSN (task 5.5)
ARG REACT_APP_SENTRY_DSN=
ENV REACT_APP_SENTRY_DSN=$REACT_APP_SENTRY_DSN
# Webpack's runtime goes in its own file, so the CSP needs no inline scripts
ENV INLINE_RUNTIME_CHUNK=false
RUN npm run build

FROM nginx:1.27-alpine
ARG REACT_APP_API_URL=http://localhost:8000
# The API the browser may call (the CSP's connect-src); override at run time if it differs
ENV API_ORIGIN=$REACT_APP_API_URL
# Where error reports go (e.g. https://o123.ingest.de.sentry.io); empty when reporting is off
ARG SENTRY_ORIGIN=
ENV SENTRY_ORIGIN=$SENTRY_ORIGIN
# nginx renders templates/*.template into conf.d at start, filling in only defined env vars
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
