#!/usr/bin/env python3
"""
Replace duplicate media files with hardlinks.

For files that exist in both downloads/ and tv/ or movies/ (copies made by 
Sonarr/Radarr before hardlink support was properly configured), this script 
replaces the library copy with a hardlink to the download copy.

Algorithm:
1. Index all files in downloads/ by size
2. Walk tv/ and movies/ 
3. For each library file with link count == 1, check if a download file 
   has the exact same size
4. Verify match with partial hash (first + last 64KB)
5. If confirmed identical, replace library file with hardlink to download file

Safety:
- Only processes files with link count == 1 (single copies)
- DRY RUN by default (pass --execute to actually modify files)
- Verifies partial content hash before linking
- Only processes common media extensions

WSL Compatibility:
- Files owned by UID 911 (Docker containers) cannot be modified via standard
  Python os.remove()/os.link() on WSL DrvFs mounts with access=client.
- Falls back to cmd.exe /c del and cmd.exe /c mklink /H using Windows paths
  to bypass WSL UID-based permission enforcement.
"""

import os
import sys
import hashlib
import shutil
import subprocess
from collections import defaultdict

MEDIA_DIR = "/mnt/e/Media"
DOWNLOAD_DIRS = [
    os.path.join(MEDIA_DIR, "downloads", "sonarr"),
    os.path.join(MEDIA_DIR, "downloads", "radarr"),
]
LIBRARY_DIRS = [
    os.path.join(MEDIA_DIR, "tv"),
    os.path.join(MEDIA_DIR, "movies"),
]
MEDIA_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.m4v', '.wmv', '.flv', '.mov', '.ts'}
HASH_CHUNK_SIZE = 65536  # 64KB

DRY_RUN = "--execute" not in sys.argv


def wsl_to_windows_path(wsl_path):
    """Convert a WSL path like /mnt/e/Media/... to E:\\Media\\..."""
    if wsl_path.startswith('/mnt/'):
        parts = wsl_path.split('/')
        drive = parts[2].upper()
        rest = '\\'.join(parts[3:])
        return f"{drive}:\\{rest}"
    return wsl_path


def escape_for_cmd(path):
    """Escape special cmd.exe metacharacters in paths."""
    return path.replace('&', '^&')


def win_delete(filepath):
    """Delete a file using cmd.exe /c del (bypasses WSL UID checks).
    Escapes cmd.exe metacharacters and passes args separately."""
    win_path = escape_for_cmd(wsl_to_windows_path(filepath))
    try:
        result = subprocess.run(
            ['cmd.exe', '/c', 'del', win_path],
            capture_output=True, timeout=30
        )
        return result.returncode == 0
    except Exception:
        return False


def win_hardlink(link_path, target_path):
    """Create a hardlink using cmd.exe /c mklink /H (bypasses WSL UID checks).
    Escapes cmd.exe metacharacters and passes args separately."""
    win_link = escape_for_cmd(wsl_to_windows_path(link_path))
    win_target = escape_for_cmd(wsl_to_windows_path(target_path))
    try:
        result = subprocess.run(
            ['cmd.exe', '/c', 'mklink', '/H', win_link, win_target],
            capture_output=True, timeout=30
        )
        return result.returncode == 0
    except Exception:
        return False


def safe_remove(filepath):
    """Remove a file, falling back to Windows cmd.exe if WSL permissions block it."""
    try:
        os.remove(filepath)
        return True
    except PermissionError:
        return win_delete(filepath)


def safe_link(source, link_name):
    """Create a hardlink, falling back to Windows cmd.exe if WSL permissions block it."""
    try:
        os.link(source, link_name)
        return True
    except OSError:
        return win_hardlink(link_name, source)


def partial_hash(filepath):
    """Hash first and last 64KB of a file for fast comparison."""
    h = hashlib.md5()
    size = os.path.getsize(filepath)
    with open(filepath, 'rb') as f:
        h.update(f.read(HASH_CHUNK_SIZE))
        if size > HASH_CHUNK_SIZE * 2:
            f.seek(-HASH_CHUNK_SIZE, 2)
            h.update(f.read(HASH_CHUNK_SIZE))
    return h.hexdigest()


def index_downloads():
    """Build a dict of size -> [filepath] for all media files in downloads."""
    size_map = defaultdict(list)
    for dl_dir in DOWNLOAD_DIRS:
        if not os.path.isdir(dl_dir):
            print(f"  Skipping {dl_dir} (not found)")
            continue
        for root, dirs, files in os.walk(dl_dir):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in MEDIA_EXTENSIONS:
                    continue
                fpath = os.path.join(root, fname)
                try:
                    size = os.path.getsize(fpath)
                    if size > 1_000_000:  # Only files > 1MB
                        size_map[size].append(fpath)
                except OSError:
                    pass
    return size_map


def find_and_link_duplicates(size_map):
    """Walk library dirs, find duplicates, and replace with hardlinks."""
    linked = 0
    skipped = 0
    no_match = 0
    already_linked = 0
    errors = 0
    space_saved = 0
    win_fallback_count = 0

    for lib_dir in LIBRARY_DIRS:
        if not os.path.isdir(lib_dir):
            print(f"  Skipping {lib_dir} (not found)")
            continue
        
        lib_name = os.path.basename(lib_dir)
        print(f"\nProcessing {lib_dir}...")
        
        for root, dirs, files in os.walk(lib_dir):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in MEDIA_EXTENSIONS:
                    continue
                
                lib_path = os.path.join(root, fname)
                try:
                    stat = os.stat(lib_path)
                except OSError:
                    continue
                
                # Skip if already hardlinked (link count > 1)
                if stat.st_nlink > 1:
                    already_linked += 1
                    continue
                
                size = stat.st_size
                if size not in size_map:
                    no_match += 1
                    continue
                
                # Find matching download file by size
                candidates = size_map[size]
                matched_dl = None
                
                lib_hash = None
                for dl_path in candidates:
                    if not os.path.exists(dl_path):
                        continue
                    # Verify with partial hash
                    if lib_hash is None:
                        lib_hash = partial_hash(lib_path)
                    dl_hash = partial_hash(dl_path)
                    if lib_hash == dl_hash:
                        matched_dl = dl_path
                        break
                
                if not matched_dl:
                    no_match += 1
                    continue
                
                # Replace library copy with hardlink to download
                size_gb = size / (1024**3)
                rel_lib = os.path.relpath(lib_path, MEDIA_DIR)
                rel_dl = os.path.relpath(matched_dl, MEDIA_DIR)
                
                if DRY_RUN:
                    print(f"  [DRY RUN] Would link: {rel_lib} ({size_gb:.2f} GB)")
                    print(f"            -> {rel_dl}")
                    linked += 1
                    space_saved += size
                else:
                    try:
                        if not safe_remove(lib_path):
                            raise OSError(f"Failed to remove {lib_path} (both Python and cmd.exe failed)")
                        if not safe_link(matched_dl, lib_path):
                            # Hardlink creation failed after file was deleted - try to copy as recovery
                            print(f"  WARNING: Hardlink failed for {rel_lib}, recovering with copy...")
                            try:
                                shutil.copy2(matched_dl, lib_path)
                                print(f"  RECOVERED: {rel_lib} (copied, not hardlinked)")
                                errors += 1
                                continue
                            except Exception as copy_err:
                                raise OSError(f"Failed to create hardlink AND copy for {lib_path}: {copy_err}")
                        # Verify the link was created
                        new_stat = os.stat(lib_path)
                        if new_stat.st_nlink < 2:
                            print(f"  WARNING: {rel_lib} link count is {new_stat.st_nlink}, expected >= 2")
                        linked += 1
                        space_saved += size
                        if linked % 25 == 0:
                            print(f"  Progress: {linked} files linked, {space_saved / (1024**3):.1f} GB saved")
                    except OSError as e:
                        print(f"  ERROR linking {rel_lib}: {e}")
                        errors += 1

    return linked, skipped, no_match, already_linked, errors, space_saved


def main():
    mode = "DRY RUN" if DRY_RUN else "EXECUTE"
    print(f"=== Hardlink Deduplication ({mode}) ===")
    if DRY_RUN:
        print("Pass --execute to actually replace copies with hardlinks\n")
    
    print("Indexing download files...")
    size_map = index_downloads()
    total_dl_files = sum(len(v) for v in size_map.values())
    print(f"  Indexed {total_dl_files} media files across {len(size_map)} unique sizes")
    
    linked, skipped, no_match, already_linked, errors, space_saved = find_and_link_duplicates(size_map)
    
    print(f"\n=== Results ===")
    print(f"  {'Would link' if DRY_RUN else 'Linked'}: {linked}")
    print(f"  Already hardlinked: {already_linked}")
    print(f"  No download match: {no_match}")
    print(f"  Errors: {errors}")
    print(f"  Space {'saveable' if DRY_RUN else 'saved'}: {space_saved / (1024**3):.2f} GB")


if __name__ == "__main__":
    main()
