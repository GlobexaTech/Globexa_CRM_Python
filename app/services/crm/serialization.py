"""Serialize explicit scalar DTO fields without implicit async relationship queries."""

from sqlalchemy import inspect


def scalar_response(schema, row):
    return schema.model_validate(
        {
            prop.key: getattr(row, prop.key)
            for prop in inspect(type(row)).column_attrs
            if prop.key in schema.model_fields
        }
    )
