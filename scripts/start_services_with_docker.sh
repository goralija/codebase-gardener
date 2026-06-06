#!/usr/bin/env bash
set -euo pipefail

DOCKER=${DOCKER:-docker}
POSTGRES_PORT=${POSTGRES_PORT:-15432}
REDIS_PORT=${REDIS_PORT:-16379}
MINIO_API_PORT=${MINIO_API_PORT:-19000}
MINIO_CONSOLE_PORT=${MINIO_CONSOLE_PORT:-19001}
MINIO_ROOT_USER=${MINIO_ROOT_USER:-local}
MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-localpass123}
OBJECT_STORAGE_BUCKET=${OBJECT_STORAGE_BUCKET:-gardener-analysis}

POSTGRES_CONTAINER=${POSTGRES_CONTAINER:-codebase-gardener-postgres}
REDIS_CONTAINER=${REDIS_CONTAINER:-codebase-gardener-redis}
MINIO_CONTAINER=${MINIO_CONTAINER:-codebase-gardener-minio}
POSTGRES_VOLUME=${POSTGRES_VOLUME:-codebase-gardener-postgres-data}
MINIO_VOLUME=${MINIO_VOLUME:-codebase-gardener-minio-data}

if ! $DOCKER info >/dev/null 2>&1; then
  echo "Docker daemon is not reachable. Start Docker or run with a Docker command that has socket access, for example:" >&2
  echo '  DOCKER="sudo docker" make services' >&2
  echo '  DOCKER="docker --context desktop-linux" make services' >&2
  exit 1
fi

container_exists() {
  $DOCKER ps -a --format '{{.Names}}' | grep -qx "$1"
}

ensure_postgres() {
  $DOCKER volume create "$POSTGRES_VOLUME" >/dev/null

  if container_exists "$POSTGRES_CONTAINER"; then
    $DOCKER start "$POSTGRES_CONTAINER" >/dev/null
    return
  fi

  $DOCKER run -d \
    --name "$POSTGRES_CONTAINER" \
    -e POSTGRES_DB=gardener \
    -e POSTGRES_USER=gardener \
    -e POSTGRES_PASSWORD=gardener \
    -p "$POSTGRES_PORT:5432" \
    -v "$POSTGRES_VOLUME:/var/lib/postgresql/data" \
    --health-cmd 'pg_isready -U gardener -d gardener' \
    --health-interval 5s \
    --health-timeout 5s \
    --health-retries 10 \
    postgres:16 >/dev/null
}

ensure_redis() {
  if container_exists "$REDIS_CONTAINER"; then
    $DOCKER start "$REDIS_CONTAINER" >/dev/null
    return
  fi

  $DOCKER run -d \
    --name "$REDIS_CONTAINER" \
    -p "$REDIS_PORT:6379" \
    --health-cmd 'redis-cli ping' \
    --health-interval 5s \
    --health-timeout 5s \
    --health-retries 10 \
    redis:7 >/dev/null
}

ensure_minio() {
  $DOCKER volume create "$MINIO_VOLUME" >/dev/null

  if container_exists "$MINIO_CONTAINER"; then
    $DOCKER start "$MINIO_CONTAINER" >/dev/null
    return
  fi

  $DOCKER run -d \
    --name "$MINIO_CONTAINER" \
    -e MINIO_ROOT_USER="$MINIO_ROOT_USER" \
    -e MINIO_ROOT_PASSWORD="$MINIO_ROOT_PASSWORD" \
    -p "$MINIO_API_PORT:9000" \
    -p "$MINIO_CONSOLE_PORT:9001" \
    -v "$MINIO_VOLUME:/data" \
    --health-cmd 'mc ready local' \
    --health-interval 5s \
    --health-timeout 5s \
    --health-retries 10 \
    minio/minio server /data --console-address ":9001" >/dev/null
}

ensure_minio_bucket() {
  $DOCKER run --rm \
    --network container:"$MINIO_CONTAINER" \
    --entrypoint /bin/sh \
    minio/mc \
    -c "mc alias set local http://127.0.0.1:9000 '$MINIO_ROOT_USER' '$MINIO_ROOT_PASSWORD' && mc mb --ignore-existing local/'$OBJECT_STORAGE_BUCKET'" >/dev/null
}

wait_healthy() {
  local container=$1
  local status

  for _ in $(seq 1 60); do
    status=$($DOCKER inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || true)
    if [ "$status" = "healthy" ]; then
      return
    fi
    if [ "$status" = "unhealthy" ]; then
      $DOCKER logs "$container" >&2 || true
      exit 1
    fi
    sleep 1
  done

  echo "Timed out waiting for $container healthcheck." >&2
  $DOCKER logs "$container" >&2 || true
  exit 1
}

ensure_postgres
ensure_redis
ensure_minio
wait_healthy "$POSTGRES_CONTAINER"
wait_healthy "$REDIS_CONTAINER"
wait_healthy "$MINIO_CONTAINER"
ensure_minio_bucket
