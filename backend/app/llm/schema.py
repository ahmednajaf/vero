"""Provider-independent closed JSON schema used for structured output and caching."""

import json
from typing import Any

from pydantic import BaseModel

from app.llm.contracts import ExtractionError, T


def output_schema(schema: type[T]) -> dict[str, Any]:
    if not isinstance(schema, type) or not issubclass(schema, BaseModel):
        raise ExtractionError("invalid_schema")
    result = schema.model_json_schema()

    def close(node: Any) -> None:
        if isinstance(node, dict):
            if "$ref" in node and not str(node["$ref"]).startswith("#/$defs/"):
                raise ExtractionError("invalid_schema")
            if node.get("type") == "object":
                if node.get("additionalProperties") not in (None, False):
                    raise ExtractionError("open_object_schema")
                node["additionalProperties"] = False
            for child in node.values():
                close(child)
        elif isinstance(node, list):
            for child in node:
                close(child)

    close(result)
    if (
        result.get("type") != "object"
        or len(
            json.dumps(
                result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        )
        > 32000
    ):
        raise ExtractionError("invalid_schema")
    return result
