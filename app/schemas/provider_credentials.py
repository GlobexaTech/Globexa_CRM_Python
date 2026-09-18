"""Bounded credential writes; validation errors never echo supplied secrets."""
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime

Secret = Annotated[str, Field(min_length=1, max_length=16000)]


class CredentialWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str | None = Field(None, min_length=1, max_length=255)
    credentials: dict[Annotated[str, Field(min_length=1, max_length=100)], Secret] | None = Field(None, max_length=20)
    access_token: Secret | None = None
    refresh_token: Secret | None = None
    token_expires_at: AwareDatetime | None = None
    token_type: str | None = Field(None, max_length=50)
    scopes: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=50)
    is_active: bool = True


def validate_credential_write(data, *, creating=False):
    from fastapi import HTTPException
    from pydantic import ValidationError
    import json
    try:
        # JSON validation accepts ISO8601 dates while retaining strict scalar types.
        row = CredentialWrite.model_validate_json(json.dumps(data))
        values = row.model_dump(exclude_unset=True)
        if creating and not values.get("name"):
            raise ValueError("name")
        if "credentials" in values and values["credentials"] is None:
            raise ValueError("credentials")
        if len(json.dumps(data)) > 20000:
            raise ValueError("size")
        if values.get("name") is None and "name" in values:
            raise ValueError("name")
        return values
    except (ValidationError, TypeError, ValueError):
        raise HTTPException(422, "Invalid credential fields or expiry; supply bounded strings and a timezone-aware ISO8601 date") from None
