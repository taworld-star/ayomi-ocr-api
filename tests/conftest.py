import os
import sys
from pathlib import Path

os.environ.setdefault("API_TOKEN", "test-token-" + "x" * 32)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
