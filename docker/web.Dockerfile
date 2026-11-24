# Web build of the Expo app (react-native-web) + the team findings hub, served by nginx.

FROM node:22-bookworm-slim AS build
ENV CI=1 EXPO_NO_TELEMETRY=1
WORKDIR /app
COPY mobile-implementation/ .
# postinstall runs scripts/build-map.mjs (bundles the map page), so the sources go in first
RUN npm ci --no-audit --no-fund
# Empty = the browser calls the API on the page's own host, port 8787 (src/live/config.ts)
ARG EXPO_PUBLIC_LIVE_API_URL=
ENV EXPO_PUBLIC_LIVE_API_URL=${EXPO_PUBLIC_LIVE_API_URL}
RUN npx expo export --platform web --output-dir dist


FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/ /usr/share/nginx/html/
COPY findings/ /usr/share/nginx/html/findings/
COPY reports/ /usr/share/nginx/html/findings/reports/
COPY notebooks/figures/ /usr/share/nginx/html/findings/figures/
COPY TECHNICAL_NOTE.md notebooks/EDA_FINDINGS.md docs/ML_PLAN.md /usr/share/nginx/html/findings/docs/
