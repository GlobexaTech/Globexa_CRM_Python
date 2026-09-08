"""Validate and export the frontend contract without running provider calls."""

import json
from pathlib import Path
from openapi_spec_validator import validate_spec
from app.main import app


def validate():
    specification = app.openapi()
    validate_spec(specification)
    required = [
        "/api/v1/operations/conversations",
        "/api/v1/operations/ai/requests",
        "/api/v1/operations/workflows",
        "/api/v1/operations/analytics/{view}",
        "/api/v1/operations/search",
        "/api/v1/operations/customers/{kind}/{entity_id}",
    ]
    assert all(path in specification["paths"] for path in required)
    Path("evidence").mkdir(exist_ok=True)
    Path("evidence/openapi.json").write_text(
        json.dumps(specification, indent=2), encoding="utf-8"
    )
    print(f"OPENAPI_VALID: {len(specification['paths'])} paths")


if __name__ == "__main__":
    validate()
