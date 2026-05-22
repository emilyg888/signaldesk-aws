from __future__ import annotations

import json

from api.handlers.common import response


def test_response_shape():
    result = response(202, {"run_id": "abc", "status": "STARTED"})
    assert result["statusCode"] == 202
    assert json.loads(result["body"])["status"] == "STARTED"
