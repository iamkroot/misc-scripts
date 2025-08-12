#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "guessit",
# ]
# ///

from argparse import ArgumentParser
import argparse
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
import guessit
import subprocess as sp
from pathlib import Path


@dataclass(frozen=True)
class FormatInfo:
    kind: Literal["tv", "animu", "movie"]
    filebot_fmt: str
    filebot_db: Literal["TVmaze", "TheMovieDB", "TheMovieDB::TV"]
    dirname: str

    @classmethod
    def from_kind(cls, kind: str):
        # FIXME: Don't hardcode the quality.
        # Problem- libmediainfo is broken in filebot, so `{vf}` doesn't work
        return {
            "tv": FormatInfo("tv", "{n} [1080p]/Season {s.pad(2)}/{s00e00} - {t}", "TVmaze", "TV"),
                "animu": FormatInfo("animu", "{n} [1080p]/{e.pad(2)} - {t}", "TheMovieDB::TV", "Anime"),
                "movie": FormatInfo("movie", "{n} ({y}) [1080p]/{n} ({y}) [1080p]", "TheMovieDB", "Movies"),
        }[kind]


def get_files(files: Iterable[Path]):
    # convert dirs to files
    res: list[Path] = []
    for file in files:
        if file.is_dir():
            res.extend(get_files(file.iterdir()))
        elif file.is_file():
            # TODO: Handle featurettes too
            res.append(file)
        else:
            raise ValueError(f"Unknown file type {file}")
    return res


def get_title(files: list[Path], expected_type: Literal['movie', 'episode']):
    """"Use guessit to extract common title to be used as hint for filebot.

    The plan is to eventually extend this to return all info, and replace filebot
    entirely.
    """
    assert files
    for file in files:
        assert file.is_file()
    res0 = guessit.guessit(str(files[0]), {"type": expected_type})
    assert res0['type'] == expected_type, f"Expected {expected_type} got {res0}"
    if len(files) > 1:
        res1 = guessit.guessit(str(files[1]), {"type": expected_type})
        assert res0['type'] == res1['type'], f"Mismatched types:\n{res0}\n{res1}"
        assert res0['title'] == res1['title'], f"Mismatched titles:\n{res0}\n{res1}"
    return res0['title'], res0.get("year")


def filebot_rename(root_dir: Path, format_info: FormatInfo, files, filebot_query: str, strict=True):
    CMD = ["filebot", "-rename"]
    if not strict:
        CMD += ["-non-strict"]
    res_dir = root_dir / format_info.dirname
    res_dir.mkdir(exist_ok=True)
    CMD += ["--output", res_dir, "--db", format_info.filebot_db, "--format", format_info.filebot_fmt,  "--q", filebot_query]
    CMD += files
    res = sp.run(CMD)
    return res.returncode == 0


def main():
    parser = ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("kind", choices=FormatInfo.__dataclass_fields__['kind'].type.__args__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--title", type=str, help="Specify title manually")
    parser.add_argument("--year", type=int, help="Specify year manually")
    parser.add_argument("--root-dir", type=Path, default=Path.home() / "Videos", help="Output directory root")
    args = parser.parse_args()

    print(args.files)
    format_info = FormatInfo.from_kind(args.kind)
    guessit_type = "movie" if args.kind == "movie" else "episode"
    files = get_files(args.files)
    if args.title:
        title, year = args.title, args.year
    else:
        title, year = get_title(files, guessit_type)
    print(title)
    if year:
        title_with_year = f"{title} {year}"
        if filebot_rename(args.root_dir, format_info, files, title_with_year):
            return
        if filebot_rename(args.root_dir, format_info, files, title_with_year, strict=False):
            return
    if filebot_rename(args.root_dir, format_info, files, title):
        return
    if filebot_rename(args.root_dir, format_info, files, title, strict=False):
        return
    print("Failed to rename :(")


if __name__ == '__main__':
    main()
