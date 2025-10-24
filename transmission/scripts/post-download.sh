#!/bin/bash

# Post-download script for Transmission
# This script is called when a download completes
# Arguments passed by Transmission:
# $1 = Torrent ID
# $2 = Torrent Name
# $3 = Torrent Path

TR_TORRENT_DIR="$TR_TORRENT_DIR"
TR_TORRENT_NAME="$TR_TORRENT_NAME"
TR_TORRENT_LABEL="${TR_TORRENT_LABEL:-}"

# Log the download completion
echo "$(date): Download completed - $TR_TORRENT_NAME" >> /config/post-download.log
echo "  Path: $TR_TORRENT_DIR" >> /config/post-download.log
echo "  Label: $TR_TORRENT_LABEL" >> /config/post-download.log

# Check if this is an audiobook by checking the path or label
# Method 1: Check if label is 'audiobooks' (if set by download client)
# Method 2: Check if download path contains 'audiobooks' subdirectory
if [[ "$TR_TORRENT_LABEL" == "audiobooks" ]] || [[ "$TR_TORRENT_DIR" == *"/audiobooks"* ]]; then
    echo "  Copying to /library/audiobooks..." >> /config/post-download.log
    
    # Create audiobooks directory if it doesn't exist
    mkdir -p "/library/audiobooks"
    
    # Try hard links first to save space (files on same filesystem)
    # If that fails, fall back to regular copy
    if cp -lr "$TR_TORRENT_DIR/$TR_TORRENT_NAME" "/library/audiobooks/" 2>/dev/null; then
        echo "  ✓ Successfully copied with hard links to /library/audiobooks/$TR_TORRENT_NAME" >> /config/post-download.log
    else
        # Hard links failed, use regular copy
        cp -r "$TR_TORRENT_DIR/$TR_TORRENT_NAME" "/library/audiobooks/" 2>&1 | tee -a /config/post-download.log
        if [ $? -eq 0 ]; then
            echo "  ✓ Successfully copied to /library/audiobooks/$TR_TORRENT_NAME" >> /config/post-download.log
        else
            echo "  ✗ Failed to copy files" >> /config/post-download.log
        fi
    fi
else
    echo "  Skipping copy (not an audiobook - path: $TR_TORRENT_DIR, label: $TR_TORRENT_LABEL)" >> /config/post-download.log
fi

echo "" >> /config/post-download.log
