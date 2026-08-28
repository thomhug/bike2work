# Stufe 1 — Seite bauen
FROM alpine:edge AS build
RUN apk add --no-cache hugo git
WORKDIR /opt/site
COPY . .
ARG HUGO_BASEURL="https://velo.tom.li/"
RUN hugo --gc --minify --baseURL="${HUGO_BASEURL}"

# Stufe 2 — ausliefern
FROM nginx:1.27-alpine
WORKDIR /usr/share/nginx/html
COPY --from=build /opt/site/public .
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80/tcp
