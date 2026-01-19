#!/usr/bin/env python3
"""Quick update checker and applier for Flaxos Spaceship Sim."""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from android_update.pydroid_manager import main

if __name__ == "__main__":
    main()
