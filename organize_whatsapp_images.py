#!/usr/bin/env python3
"""
Move WhatsApp image files into date-based subdirectories.

Parses filenames like:
    WhatsApp Image 2026-04-01 at 15.45.24.jpg
    WhatsApp Image 2026-04-01 at 15.45.24 (1).jpg
    WhatsApp Image 2026-04-28 at 14.44.39 (1).png

And moves each into a subdirectory named after the date, e.g.:
    2026-04-01/
    2026-04-28/

Usage:
    python organize_whatsapp_images.py <target_directory>
"""

import argparse
import re
import shutil
from pathlib import Path

# Pattern: "WhatsApp Image YYYY-MM-DD at HH.MM.SS[ (n)]"
FILENAME_PATTERN = re.compile(
    r"^WhatsApp Image (\d{4}-\d{2}-\d{2}) at \d{2}\.\d{2}\.\d{2}(?: \(\d+\))?",
    re.IGNORECASE,
)


def extract_date(filename: str) -> str | None:
    """Return the date string (YYYY-MM-DD) if the filename matches, else None."""
    match = FILENAME_PATTERN.match(filename)
    if match:
        return match.group(1)
    return None


def organize_images(target_dir: Path) -> None:
    """Move matching files in target_dir into date-named subdirectories."""
    if not target_dir.is_dir():
        print(f"Error: '{target_dir}' is not a directory or does not exist.")
        return

    moved_count = 0

    for filepath in target_dir.iterdir():
        if not filepath.is_file():
            continue

        date_str = extract_date(filepath.name)
        if date_str is None:
            continue

        dest_dir = target_dir / date_str
        dest_dir.mkdir(exist_ok=True)

        dest_path = dest_dir / filepath.name
        shutil.move(str(filepath), str(dest_path))
        print(f"  {filepath.name}  ->  {date_str}/")
        moved_count += 1

    print(f"\nDone. Moved {moved_count} file(s).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Organize WhatsApp image files into date-based subdirectories."
    )
    parser.add_argument(
        "directory",
        type=str,
        help="Path to the directory containing WhatsApp image files.",
    )
    args = parser.parse_args()

    target_dir = Path(args.directory).resolve()
    organize_images(target_dir)


if __name__ == "__main__":
    main()
