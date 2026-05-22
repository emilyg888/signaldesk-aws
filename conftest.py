# conftest.py — shared pytest configuration
import sys
from pathlib import Path

# Ensure project root is always on the path
sys.path.insert(0, str(Path(__file__).parent))
