#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="miqat-list"
CONTAINER_NAME="miqat-list"
PORT=8080

usage() {
  echo "Usage: $0 [-p host_port] [-n container_name] [-i image_name]"
  exit 1
}

while getopts "p:n:i:h" opt; do
  case "$opt" in
    p) PORT="$OPTARG" ;;
    n) CONTAINER_NAME="$OPTARG" ;;
    i) IMAGE_NAME="$OPTARG" ;;
    h|*) usage ;;
  esac
done

cd "$(dirname "$0")"

echo "Building image '$IMAGE_NAME'..."
docker build -t "$IMAGE_NAME" .

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Removing existing container '$CONTAINER_NAME'..."
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

echo "Starting container '$CONTAINER_NAME' on http://localhost:$PORT ..."
echo "(Ctrl+C to stop)"
docker run --rm --name "$CONTAINER_NAME" -p "${PORT}:8080" "$IMAGE_NAME"
