"""
Ensure both PNG and JPG versions of every image file exist in a directory,
then collect them into `jpg/` and `png/` subdirectories.

Usage: python convert_images.py [directory]

Vibecoded by DeepSeek V4 Pro, thank you!
"""

import argparse
from pathlib import Path

from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def image_files(directory: Path) -> dict[str, set[Path]]:
    """
    Scan *directory* (non-recursive) and return a dict keyed by category:
        'jpg'  -> set of Paths ending in .jpg or .jpeg
        'png'  -> set of Paths ending in .png
        'bmp'  -> set of Paths ending in .bmp
        'webp' -> set of Paths ending in .webp

    Only regular files are considered. Extensions are matched
    case-insensitively.
    """
    categories = {
        'jpg':  set(),
        'png':  set(),
        'bmp':  set(),
        'webp': set(),
    }

    ext_map = {
        '.jpg':  'jpg',
        '.jpeg': 'jpg',
        '.png':  'png',
        '.bmp':  'bmp',
        '.webp': 'webp',
    }

    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        ext = entry.suffix.lower()
        cat = ext_map.get(ext)
        if cat is not None:
            categories[cat].add(entry)

    return categories


def ensure_jpg_and_png(
    stem: str,
    source: Path,
    jpg_dir: Path,
    png_dir: Path,
    existing_png_stems: set[str],
    existing_jpg_stems: set[str],
) -> None:
    """
    Given an image *source* and its *stem*, create a .png and/or .jpg copy
    in *jpg_dir*/*png_dir* if one doesn't already exist for that stem.

    The *existing_*_stems sets are updated in-place so later checks see
    newly created files.
    """
    # -- PNG side -----------------------------------------------------------
    if stem not in existing_png_stems:
        dest = png_dir / f"{stem}.png"
        img = Image.open(source)
        # PNG can hold any mode, so save as-is (Pillow autodetects format)
        img.save(dest, format="PNG")
        existing_png_stems.add(stem)
        print(f"  Created {dest}")

    # -- JPG side -----------------------------------------------------------
    if stem not in existing_jpg_stems:
        dest = jpg_dir / f"{stem}.jpg"
        img = Image.open(source)
        if img.mode in ("RGBA", "LA", "P"):
            # Remove alpha / palette for JPEG compatibility
            rgb = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            rgb.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = rgb
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.save(dest, format="JPEG")
        existing_jpg_stems.add(stem)
        print(f"  Created {dest}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ensure PNG+JPG pairs for all images and sort into folders."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory containing image files (default: current directory)",
    )
    args = parser.parse_args()

    root = Path(args.directory).resolve()
    if not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")

    # Prepare output subdirectories (they live inside the working directory)
    jpg_dir = root / "jpg"
    png_dir = root / "png"
    jpg_dir.mkdir(exist_ok=True)
    png_dir.mkdir(exist_ok=True)

    # ---- Step 1: inventory ------------------------------------------------
    cats = image_files(root)
    jpg_files  = cats['jpg']
    png_files  = cats['png']
    bmp_files  = cats['bmp']
    webp_files = cats['webp']

    # Fast stem lookups
    png_stems = {p.stem for p in png_files}
    jpg_stems = {p.stem for p in jpg_files}

    print(f"Found: {len(jpg_files)} jpg, {len(png_files)} png, "
          f"{len(bmp_files)} bmp, {len(webp_files)} webp")

    # ---- Step 2: JPG <-> PNG cross-check ----------------------------------
    print("\n--- Ensuring JPG→PNG pairs ---")
    for src in sorted(jpg_files):
        if src.stem not in png_stems:
            ensure_jpg_and_png(
                src.stem, src, jpg_dir, png_dir,
                png_stems, jpg_stems,
            )

    print("\n--- Ensuring PNG→JPG pairs ---")
    for src in sorted(png_files):
        if src.stem not in jpg_stems:
            ensure_jpg_and_png(
                src.stem, src, jpg_dir, png_dir,
                png_stems, jpg_stems,
            )

    # ---- Step 3: BMP & WebP → both JPG + PNG ------------------------------
    for label, file_set in (("BMP", bmp_files), ("WebP", webp_files)):
        print(f"\n--- Processing {label} files ---")
        for src in sorted(file_set):
            ensure_jpg_and_png(
                src.stem, src, jpg_dir, png_dir,
                png_stems, jpg_stems,
            )

    # ---- Step 4: Move JPG/PNG files into their subdirectories -------------
    # Re-scan because some files may have been created in the root
    # (conversions write directly into the subdirectories, but originals
    # are still in root).
    print("\n--- Moving files into subdirectories ---")

    jpg_exts = {'.jpg', '.jpeg'}
    for entry in root.iterdir():
        if not entry.is_file():
            continue
        ext = entry.suffix.lower()
        if ext in jpg_exts:
            dest = jpg_dir / entry.name
            if entry.resolve() != dest.resolve():
                entry.rename(dest)
                print(f"  Moved {entry.name} -> jpg/")
        elif ext == '.png':
            dest = png_dir / entry.name
            if entry.resolve() != dest.resolve():
                entry.rename(dest)
                print(f"  Moved {entry.name} -> png/")

    print("\nDone.")


if __name__ == "__main__":
    main()