#!/bin/sh
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/tmp/fly-arena-contact-v8/src
export NUMBA_CACHE_DIR=/tmp/fly-v8-implementation/cache/numba
export MPLCONFIGDIR=/tmp/fly-v8-implementation/cache/matplotlib
export XDG_CACHE_HOME=/tmp/fly-v8-implementation/cache
export OMP_NUM_THREADS=1
exec /Users/lexa/Desktop/lexa/omega/fly-arena/.venv/bin/python "$@"
