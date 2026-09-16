#!/bin/sh
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/tmp/fly-arena-embodied-v7/src
export NUMBA_CACHE_DIR=/tmp/fly-arena-embodied-v7/var/embodied-v7/cache/numba
export MPLCONFIGDIR=/tmp/fly-arena-embodied-v7/var/embodied-v7/cache/matplotlib
export XDG_CACHE_HOME=/tmp/fly-arena-embodied-v7/var/embodied-v7/cache
exec /Users/lexa/Desktop/lexa/omega/fly-arena/.venv/bin/python "$@"
