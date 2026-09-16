#!/bin/zsh
set -eu
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${0:A:h:h}/src"
export MPLCONFIGDIR=/tmp/fly-behavior-v10-implementation/mpl
export XDG_CACHE_HOME=/tmp/fly-behavior-v10-implementation/cache
export NUMBA_CACHE_DIR=/tmp/fly-behavior-v10-implementation/numba
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
exec /Users/lexa/Desktop/lexa/omega/fly-arena/.venv/bin/python -m flyarena.experiments.mechanical_v10 "$@"
