"""Export anatomical context alongside public replays for static deployments.

python scripts/bundle_anatomy.py --data data --output web/dist/examples/anatomy
The file is named for the canonical connectome already used by the replay.
"""
import argparse
from pathlib import Path
from flyarena.anatomy import build_anatomy
from flyarena.common import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    anatomy = build_anatomy(args.data / 'connectome')
    target = args.output / (anatomy['connectome_sha256'] + '.json')
    write_json(target, anatomy)
    print(f"{target}: {anatomy['position_count']} positions; {anatomy['missing_position_count']} absent")


if __name__ == '__main__':
    main()
