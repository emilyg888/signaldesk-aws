"""
API tests for api/server.py
"""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from api.server import app


client = TestClient(app)


def test_index_disables_cache():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"
