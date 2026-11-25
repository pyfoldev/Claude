# --- сборка ---
FROM golang:1.24-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/staika ./cmd/staika

# --- запуск ---
FROM alpine:3.20
RUN apk add --no-cache ca-certificates tzdata && adduser -D -u 10001 staika
WORKDIR /app
COPY --from=build /out/staika /app/staika
RUN mkdir -p /app/data/workspaces && chown -R staika /app
USER staika
ENV PORT=8080 STAIKA_WORKSPACES_DIR=/app/data/workspaces
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -qO- http://127.0.0.1:8080/health || exit 1
ENTRYPOINT ["/app/staika"]
