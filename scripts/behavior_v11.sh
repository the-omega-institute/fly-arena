#!/bin/sh
set -eu
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/tmp/fly-arena-behavior-v11/src
export MPLCONFIGDIR=/tmp/fly-v11-realization/matplotlib
export XDG_CACHE_HOME=/tmp/fly-v11-realization/cache
export NUMBA_CACHE_DIR=/tmp/fly-v11-realization/numba
export TMPDIR=/tmp/fly-v11-realization
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
exec /Users/lexa/Desktop/lexa/omega/fly-arena/.venv/bin/python "$@"
