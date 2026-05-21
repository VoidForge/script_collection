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
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis


# ---------------------------------------------------------------------------
# Known non-audio extensions to skip silently
# ---------------------------------------------------------------------------

NON_AUDIO_EXTENSIONS = frozenset({
    # Lyrics / text
    ".lrc", ".txt", ".md", ".nfo", ".cue", ".log", ".m3u", ".m3u8", ".pls",
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif",
    ".svg", ".ico", ".heic", ".heif", ".raw", ".cr2", ".nef", ".arw",
    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    # Archives / other
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
})


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_audio_files(directory, verbose=0):
    """
    Recursively yield (relative_path, mutagen_file) for all audio files in
    *directory*. Non-audio files (where mutagen.File returns None) are skipped.
    With verbose >= 1, warnings are printed to stderr.
    """
    root = Path(directory).resolve()
    count = 0

    for filepath in sorted(root.rglob("*")):
        if not filepath.is_file():
            continue

        # Silently skip known non-audio extensions
        if filepath.suffix.lower() in NON_AUDIO_EXTENSIONS:
            continue

        rel = filepath.relative_to(root)

        try:
            audio = _load_audio(filepath)
        except Exception as exc:
            if verbose >= 1:
                print(f"Warning: cannot read {rel}: {exc}", file=sys.stderr)
            continue

        if audio is None:
            if verbose >= 1:
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

def cmd_read_fields(directory, verbose=0):
    """Print the union of all non-empty metadata field names across all files."""
    all_keys = set()

    for _rel, audio in find_audio_files(directory, verbose=verbose):
        all_keys |= _non_empty_keys(audio)

    for key in sorted(all_keys):
        print(key)


# ---------------------------------------------------------------------------
# Mode 1.2: print a specific field's value for each file
# ---------------------------------------------------------------------------

def cmd_read_data(directory, field, verbose=0):
    """Print <relative_path>: <value> for the given field in each file."""
    for rel, audio in find_audio_files(directory, verbose=verbose):
        value = _get_field_value(audio, field)
        print(f"{rel}: {value}")


# ---------------------------------------------------------------------------
# Mode 2.1: write a value to a given field on all files
# ---------------------------------------------------------------------------

def cmd_write(directory, field, value, verbose=0):
    """Write *value* to *field* on every audio file, overwriting any existing."""
    success = 0
    failed = 0

    for rel, audio in find_audio_files(directory, verbose=verbose):
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

        try:
            audio.tags[field] = [value]
        except KeyError:
            print(
                f"Error: key \"{field}\" is not a recognised EasyID3 key for {rel}.\n"
                f"       EasyID3 keys are format-specific; this key may not exist for MP3/ID3.",
                file=sys.stderr,
            )
            failed += 1
            continue
        except ValueError as exc:
            print(f"Error: invalid value for \"{field}\" in {rel}: {exc}", file=sys.stderr)
            failed += 1
            continue

        try:
            audio.save()
            if verbose >= 2:
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
# Mode 3: remove a field from all files
# ---------------------------------------------------------------------------

# EasyID3 field names that map to raw ID3 frames not handled by EasyID3's
# default key set.  cmd_remove uses these to delete the frame directly.
_COMPLEX_ID3_FIELDS = {
    "comment": "COMM",
}


def cmd_remove(directory, field, frame=None, verbose=0):
    """Remove *field* (or raw *frame* ID) from every audio file."""
    success = 0
    failed = 0
    root = Path(directory).resolve()

    for rel, audio in find_audio_files(directory, verbose=verbose):
        try:
            if frame is not None:
                # Raw ID3 frame deletion (advanced – no fallback)
                _remove_id3_frame(root / rel, rel, frame)
            elif field in _COMPLEX_ID3_FIELDS:
                # Complex field: try raw ID3 deletion first, fall back to
                # generic tag deletion for non-ID3 formats (OGG, FLAC, etc.)
                try:
                    _remove_id3_frame(root / rel, rel, _COMPLEX_ID3_FIELDS[field])
                except MutagenError:
                    # Not an ID3 file – use the pre-loaded EasyID3/generic wrapper
                    if hasattr(audio, "tags") and audio.tags and field in audio.tags:
                        del audio.tags[field]
                    audio.save()
            else:
                # EasyID3 / generic tag key deletion (works across all formats)
                if hasattr(audio, "tags") and audio.tags and field in audio.tags:
                    del audio.tags[field]
                audio.save()

            if verbose >= 2:
                print(f"OK: {rel}")
            success += 1
        except KeyError:
            print(
                f"Error: key \"{field}\" is not a recognised EasyID3 key for {rel}.",
                file=sys.stderr,
            )
            failed += 1
        except MutagenError as exc:
            print(f"Error: cannot save {rel}: {exc}", file=sys.stderr)
            failed += 1
        except Exception as exc:
            print(f"Error: cannot remove from {rel}: {exc}", file=sys.stderr)
            failed += 1

    # Summary
    if failed:
        print(f"\nDone. {success} file(s) updated, {failed} error(s).", file=sys.stderr)
    else:
        print(f"\nDone. {success} file(s) updated successfully.")


def _remove_id3_frame(full_path, rel, frame_id):
    """
    Reload *full_path* as raw ID3, delete *frame_id*, and save.
    Raises MutagenError if the file does not have ID3 tags.
    """
    from mutagen.id3 import ID3

    try:
        tags = ID3(str(full_path))
    except Exception as exc:
        raise MutagenError(f"cannot open ID3 tags on {rel}: {exc}") from exc
    tags.delall(frame_id)
    tags.save()


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
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity: -v enables warnings, -vv also enables OK messages",
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
        "--value",
        required=True,
        help="Value to write to the field",
    )

    # -- remove -------------------------------------------------------------
    remove_parser = subparsers.add_parser("remove", help="Remove metadata")
    remove_parser.add_argument(
        "--field", "-f",
        required=True,
        help="Metadata field name to remove (EasyID3 key, e.g. artist, comment)",
    )
    remove_parser.add_argument(
        "--frame",
        default=None,
        help="Raw ID3 frame ID to delete instead (advanced, e.g. COMM, TIT2). "
             "Overrides --field for ID3 formats.",
    )

    args = parser.parse_args()

    # Dispatch
    if args.mode == "read":
        if args.read_mode == "fields":
            cmd_read_fields(args.directory, verbose=args.verbose)
        elif args.read_mode == "data":
            cmd_read_data(args.directory, args.field, verbose=args.verbose)
    elif args.mode == "write":
        cmd_write(args.directory, args.field, args.value, verbose=args.verbose)
    elif args.mode == "remove":
        cmd_remove(args.directory, args.field, frame=args.frame, verbose=args.verbose)


if __name__ == "__main__":
    main()