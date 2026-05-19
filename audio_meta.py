#!/usr/bin/env python3
"""
Audio metadata processing tool.

Read or write metadata fields across a directory of audio files (recursively).
Supports all formats that mutagen handles: MP3, FLAC, AAC, MP4, OGG, Opus,
WAV, WMA, and more.

Coded by: DeepSeek V4 Pro

Last Modified: 2026-05-19

Dependencies: pip install mutagen
"""

import argparse
import sys
from pathlib import Path

from mutagen._util import MutagenError
from mutagen.easyid3 import EasyID3
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_audio_files(directory):
    """
    Recursively yield (relative_path, mutagen_file) for all audio files in
    *directory*. Non-audio files (where mutagen.File returns None) are skipped
    with a warning to stderr.
    """
    root = Path(directory).resolve()
    count = 0

    for filepath in sorted(root.rglob("*")):
        if not filepath.is_file():
            continue

        rel = filepath.relative_to(root)

        try:
            # easy=True gives us a dict-like API for common tags.
            # Try the generic File wrapper first; fall back to format-specific
            # loaders for edge cases.
            audio = _load_audio(filepath)
        except Exception as exc:
            print(f"Warning: cannot read {rel}: {exc}", file=sys.stderr)
            continue

        if audio is None:
            print(f"Warning: {rel} is not a recognised audio format", file=sys.stderr)
            continue

        count += 1
        yield rel, audio

    if count == 0:
        print("No audio files found in directory.", file=sys.stderr)
        sys.exit(0)


def _load_audio(filepath):
    """
    Load an audio file with mutagen, trying the generic loader first and then
    format-specific fallbacks for cases where the generic loader doesn't
    return tags properly.
    """
    path_str = str(filepath)

    # Try generic mutagen.File with easy=True first
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(path_str, easy=True)
    except Exception:
        audio = None

    # If that returned None or an object without expected tag support, try
    # format-specific loaders as a fallback.
    if audio is None or not hasattr(audio, "tags"):
        ext = filepath.suffix.lower()
        if ext in (".ogg", ".oga"):
            try:
                audio = OggVorbis(path_str)
            except Exception:
                try:
                    audio = OggOpus(path_str)
                except Exception:
                    pass

    return audio


# ---------------------------------------------------------------------------
# Helper: get non-empty tag keys
# ---------------------------------------------------------------------------

def _non_empty_keys(audio):
    """Return a set of tag keys that have a non-empty value."""
    keys = set()
    for key, values in (audio.tags or {}).items() if hasattr(audio, "tags") and audio.tags else {}:
        # values is a list; join multi-value fields for emptiness check
        joined = " / ".join(str(v) for v in values).strip()
        if joined:
            keys.add(key)
    return keys


def _get_field_value(audio, field):
    """Return a string representation of a tag field, or '<empty>' if absent."""
    if not hasattr(audio, "tags") or not audio.tags:
        return "<empty>"
    values = audio.tags.get(field)
    if not values:
        return "<empty>"
    return " / ".join(str(v) for v in values)


# ---------------------------------------------------------------------------
# Mode 1.1: print union of non-empty field names
# ---------------------------------------------------------------------------

def cmd_read_fields(directory):
    """Print the union of all non-empty metadata field names across all files."""
    all_keys = set()

    for _rel, audio in find_audio_files(directory):
        all_keys |= _non_empty_keys(audio)

    for key in sorted(all_keys):
        print(key)


# ---------------------------------------------------------------------------
# Mode 1.2: print a specific field's value for each file
# ---------------------------------------------------------------------------

def cmd_read_data(directory, field):
    """Print <relative_path>: <value> for the given field in each file."""
    for rel, audio in find_audio_files(directory):
        value = _get_field_value(audio, field)
        print(f"{rel}: {value}")


# ---------------------------------------------------------------------------
# Mode 2.1: write a value to a given field on all files
# ---------------------------------------------------------------------------

def cmd_write(directory, field, value):
    """Write *value* to *field* on every audio file, overwriting any existing."""
    success = 0
    failed = 0

    for rel, audio in find_audio_files(directory):
        # Ensure the audio object has a writable tags container.
        # For mutagen's easy mode, some formats need .tags initialised.
        if not hasattr(audio, "tags") or audio.tags is None:
            # Try to add an empty tags dictionary
            try:
                audio.add_tags()
            except Exception:
                print(f"Error: cannot add tags to {rel} (format may not support tagging)", file=sys.stderr)
                failed += 1
                continue

        audio.tags[field] = [value]

        try:
            audio.save()
            print(f"OK: {rel}")
            success += 1
        except MutagenError as exc:
            print(f"Error: cannot save {rel}: {exc}", file=sys.stderr)
            failed += 1
        except Exception as exc:
            print(f"Error: {rel}: {exc}", file=sys.stderr)
            failed += 1

    # Summary
    if failed:
        print(f"\nDone. {success} file(s) updated, {failed} error(s).", file=sys.stderr)
    else:
        print(f"\nDone. {success} file(s) updated successfully.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Read or write audio file metadata in a directory (recursively)."
    )
    parser.add_argument(
        "directory",
        help="Path to the directory containing audio files",
    )

    subparsers = parser.add_subparsers(dest="mode", required=True, help="Operation mode")

    # -- read ---------------------------------------------------------------
    read_parser = subparsers.add_parser("read", help="Read metadata")
    read_sub = read_parser.add_subparsers(dest="read_mode", required=True)

    # read fields  (1.1)
    read_sub.add_parser("fields", help="Print union of all non-empty field names")

    # read data    (1.2)
    data_parser = read_sub.add_parser("data", help="Print a field's value for each file")
    data_parser.add_argument(
        "--field", "-f",
        required=True,
        help="Metadata field name (e.g. artist, title, album)",
    )

    # -- write --------------------------------------------------------------
    write_parser = subparsers.add_parser("write", help="Write metadata")
    write_parser.add_argument(
        "--field", "-f",
        required=True,
        help="Metadata field name (e.g. artist, title, album, genre)",
    )
    write_parser.add_argument(
        "--value", "-v",
        required=True,
        help="Value to write to the field",
    )

    args = parser.parse_args()

    # Dispatch
    if args.mode == "read":
        if args.read_mode == "fields":
            cmd_read_fields(args.directory)
        elif args.read_mode == "data":
            cmd_read_data(args.directory, args.field)
    elif args.mode == "write":
        cmd_write(args.directory, args.field, args.value)


if __name__ == "__main__":
    main()