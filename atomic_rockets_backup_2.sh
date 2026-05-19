#!/bin/bash
set -euo pipefail

# This is a script intended for mirroring the Atomic Rockets site "(www.projectrho.com)"
# the archive will be placed under ./ar_mirror, and wget.log file is available for monitoring the progress
# each time you execute the script, a tar.gz archive marked with date will be created
# and the ./ar_mirror/www.projectrho.com directory will be updated.
# This script runs at foreground, it is recommended to use nohup command as the mirroring process is quite long
# Please make sure that you are running this script on a linux system and have all the required programs installed, 
# including but not limited to wget2, tar, find, rename, missing any of these will result in unintended behaviour.
# last updated: 2026-05-19
# Rewritten by DSv4, correctness not guaranteed

# --- Help flag (must be before auto-background) ---
for arg in "$@"; do
    case "$arg" in
        -h|--help)
            USAGE=1
            ;;
    esac
done
if [[ -n "${USAGE:-}" ]]; then
    cat <<'EOF'
Usage: atomic_rockets_backup_2.sh [mirror_dir] [target_url]

  Mirror the Atomic Rockets site (www.projectrho.com) for offline browsing.

Arguments:
  mirror_dir   Directory to store the mirror archive and wget.log.
               Default: ./ar_mirror
  target_url   The starting URL to mirror.
               Default: http://www.projectrho.com/public_html/rocket/index.php

Flags:
  -h, --help   Show this help message and exit.

Behavior:
  • The script auto-backgrounds itself via nohup for long-running mirroring.
  • A tar.gz archive named atomic_rockets_YYYY-MM-DD.tar.gz is created.
  • Downloaded .php files are renamed to .html, and internal links updated.
  • Requires: wget2, tar, find, sed, rename, date, cp, mv, rm, mkdir.

Example:
  ./atomic_rockets_backup_2.sh ./my_mirror http://www.projectrho.com/public_html/rocket/index.php
EOF
    exit 0
fi

# auto background
if [[ -z "$SCRIPT_BG" ]]; then
    export SCRIPT_BG=1
    nohup "$0" "$@" >/dev/null 2>&1 &
    disown
    exit 0
fi
unset SCRIPT_BG

# --- Configuration ---
ar_dir="${1:-./ar_mirror}"
target_url="${2:-http://www.projectrho.com/public_html/rocket/index.php}"

# --- Resolve ar_dir to absolute path (portable, no realpath needed) ---
mkdir -p "$ar_dir"
cd "$ar_dir" || exit 1
ar_dir="$(pwd)"

# --- Temp paths (absolute, for trap safety) ---
temp_dir="$ar_dir/ar_backup_temp"
log_file="$ar_dir/wget.log"

# --- Dependency check (must be before any real work) ---
check_deps() {
    local missing=""
    for cmd in wget2 tar find sed date cp mv rm mkdir; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing="$missing $cmd"
        fi
    done

    if [ -n "$missing" ]; then
        echo "Error: Required commands not found:$missing" >&2
        exit 1
    fi
}
check_deps

# --- Cleanup trap (absolute paths only) ---
_cleanup_done=false
cleanup() {
    local _exit=$?                        # MUST be first
    if $_cleanup_done; then return; fi
    _cleanup_done=true
    echo "Cleaning up (exit code: $_exit)..." >&2
    rm -rf "$temp_dir"
    exit $_exit
}
trap cleanup EXIT INT TERM

# --- Main script ---
echo "Mirroring $target_url to $ar_dir"
if ! wget2 -k -m --max-threads 8 -o "$log_file" "$target_url"; then
    echo "Error: Wget2 Download Fail, Terminating." >&2
    exit 1
fi

if [ ! -d "www.projectrho.com" ]; then
    echo "Error: Downloaded directory 'www.projectrho.com' not found." >&2
    exit 1
fi

mkdir -p "$temp_dir"
cp -r www.projectrho.com/ "$temp_dir"
cd "$temp_dir"

find . -name '*.php' \
  -exec rename -f 's/\.css\.php$/.css/' {} \; \
  -exec rename -f 's/\.js\.php$/.js/' {} \; \
  -exec rename -f 's/\.php$/.html/' {} \;

find . -name '*.html' -exec sed -i \
  -e 's/\("\)\([^"]*\)\.js\.php\(["#'"'"'?]\)/\1\2.js\3/g' \
  -e "s/\('\)\([^']*\)\.js\.php\(['\"#?]\)/\1\2.js\3/g" \
  -e 's/\("\)\([^"]*\)\.css\.php\(["#'"'"'?]\)/\1\2.css\3/g' \
  -e "s/\('\)\([^']*\)\.css\.php\(['\"#?]\)/\1\2.css\3/g" \
  -e 's/\("\)\([^"]*\)\.php\(["#'"'"'?]\)/\1\2.html\3/g' \
  -e "s/\('\)\([^']*\)\.php\(['\"#?]\)/\1\2.html\3/g" \
  {} \;

today=$(date '+%Y-%m-%d')
archive_name="atomic_rockets_${today}.tar.gz"

tar czf "$archive_name" www.projectrho.com
mv "$archive_name" "$ar_dir/"
cd "$ar_dir"

# Clean up temp directory (trap will also handle this on exit)
rm -rf "$temp_dir"

echo "Script execution completed. Archive: $ar_dir/$archive_name"