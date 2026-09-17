#!/usr/bin/env python3
"""Explicitly prepare the immutable full-graph v2 decoder."""
import argparse
from pathlib import Path
from flyarena.common import DATA
from flyarena.experiments.decoder import prepare
if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--data', type=Path, default=DATA)
    prepare(p.parse_args().data)
