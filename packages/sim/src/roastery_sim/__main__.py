"""`python -m roastery_sim tiny --out DIR [--seed N] [--until ISO] [--store memory|sqlite]`,
`volume --out DIR [--seed N]` and `release --out DIR [--tiny DIR] [--volume DIR]`.

Plays the script, faults the export (not when `--until` cuts the play short, W39), and writes
`DIR/tiny.sql`, the data folder `DIR/data` and the landing's csv files `DIR/landing`. One line
is printed per file written.

`volume` plays the two years once on sqlite and writes `DIR/full/data`, `DIR/month/data` and
the month's landing `DIR/month/landing`. `release` zips the built folders into the three files
of `roastery-data-1.0.0`, the same bytes for the same folders.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.metadata
import sys
from collections.abc import Sequence
from pathlib import Path

from roastery_sim import build, release


def _moment(text: str) -> dt.datetime:
    moment = dt.datetime.fromisoformat(text)
    if moment.utcoffset() is None:
        raise argparse.ArgumentTypeError(f'{text}: a moment needs its offset, as +00:00')
    return moment


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='python -m roastery_sim')
    commands = parser.add_subparsers(dest='command', required=True)
    tiny = commands.add_parser('tiny', help='play the week and write tiny')
    tiny.add_argument('--out', type=Path, required=True, help='the folder to write into')
    tiny.add_argument('--seed', type=int, default=0)
    tiny.add_argument('--until', type=_moment, default=None, help='play only steps before it')
    tiny.add_argument('--store', choices=('memory', 'sqlite'), default='memory')
    volume = commands.add_parser('volume', help='play two years and write full and month')
    volume.add_argument('--out', type=Path, required=True, help='the folder to write into')
    volume.add_argument('--seed', type=int, default=0)
    zips = commands.add_parser('release', help='zip the built folders into the release')
    zips.add_argument('--out', type=Path, required=True, help='the folder for the zips')
    zips.add_argument('--tiny', type=Path, default=Path('build/tiny'), help='the built tiny')
    zips.add_argument('--volume', type=Path, default=Path('build/volume'), help='the built volume')
    return parser


def _print(paths: Sequence[Path]) -> None:
    for path in paths:
        sys.stdout.write(f'{path.as_posix()}\n')


def _volume(args: argparse.Namespace) -> int:
    _print(build.volume(args.out, seed=args.seed, packages=build.installed()))
    return 0


def _release(args: argparse.Namespace) -> int:
    _print(release.release(args.out, tiny=args.tiny, volume=args.volume))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command; 0 on success. An error in the play is raised, never hidden."""
    args = _parser().parse_args(argv)
    if args.command == 'volume':
        return _volume(args)
    if args.command == 'release':
        return _release(args)
    built = build.build(seed=args.seed, until=args.until, store=args.store)
    written = build.write(
        built,
        args.out,
        seed=args.seed,
        shop_version=importlib.metadata.version('roastery'),
        until=args.until,
    )
    for path in written:
        sys.stdout.write(f'{path.as_posix()}\n')
    sys.stdout.write(f'{len(built.defects)} defects in the manifest\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
