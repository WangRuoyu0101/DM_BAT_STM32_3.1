#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-jetson@192.168.17.130}"
REMOTE_WS="${REMOTE_WS:-/home/jetson/ros_ws}"
LOCAL_WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rsync -av --delete \
  --exclude 'build/' \
  --exclude 'install/' \
  --exclude 'log/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "${REMOTE_HOST}:${REMOTE_WS}/src/" \
  "${LOCAL_WS}/src/"
