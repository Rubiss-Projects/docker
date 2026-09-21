#!/usr/bin/env python3
"""Compatibility launcher for the shared, media-preserving cleanup policy.

Requires Node.js. All arguments and the exit status pass through to the same
implementation used by n8n; there is no separate legacy deletion policy.
"""

import os
from pathlib import Path
import sys


if __name__ == "__main__":
    script = Path(__file__).resolve().parents[1] / "n8n/scripts/cleanup_crossseed_stuck.js"
    os.execvp("node", ["node", str(script), *sys.argv[1:]])
