#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-jetson@192.168.17.130}"
REMOTE_WS="${REMOTE_WS:-/home/jetson/ros_ws}"
LOCAL_WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ssh "${REMOTE_HOST}" "mkdir -p '${REMOTE_WS}/src'"

rsync -av --delete \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "${LOCAL_WS}/src/" \
  "${REMOTE_HOST}:${REMOTE_WS}/src/"
