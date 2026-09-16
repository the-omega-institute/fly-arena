#!/bin/zsh
set -eu
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${0:A:h:h}/src"
export MPLCONFIGDIR=/tmp/fly-arena-behavior-v12/cache/mpl
export XDG_CACHE_HOME=/tmp/fly-arena-behavior-v12/cache
export NUMBA_CACHE_DIR=/tmp/fly-arena-behavior-v12/cache/numba
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
exec /Users/lexa/Desktop/lexa/omega/fly-arena/.venv/bin/python -m flyarena.experiments.mechanical_v12 "$@"
