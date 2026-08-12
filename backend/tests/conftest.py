from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("CINEVOICE_DATA_DIR", str(ROOT / ".test-data"))
os.environ.setdefault("CINEVOICE_FRONTEND_DIR", "")
