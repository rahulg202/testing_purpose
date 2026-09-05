"""JSON Schema export utility.

Generates JSON Schema files from Pydantic models for use by the
TypeScript frontend (type generation) and external integrators.
"""

import json
from pathlib import Path

from pydantic import BaseModel

from .audit import AuditEvent
from .canonical_case import CanonicalCase
from .source_record import SourceRecord

MODELS: dict[str, type[BaseModel]] = {
    "CanonicalCase": CanonicalCase,
    "SourceRecord": SourceRecord,
    "AuditEvent": AuditEvent,
}


def export_schemas(output_dir: str | Path) -> None:
    """Export JSON Schema for all contract models."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for name, model in MODELS.items():
        schema = model.model_json_schema()
        schema_file = output_path / f"{name}.schema.json"
        schema_file.write_text(json.dumps(schema, indent=2))
        print(f"  Exported {name} → {schema_file}")


def export_typescript_types(output_dir: str | Path) -> None:
    """Export TypeScript type definitions from JSON Schema.

    Note: In production this would use json-schema-to-typescript or similar.
    For MVP we export the JSON schemas and use them with a TS code generator.
    """
    export_schemas(output_dir)
    print("  Use `npx json-schema-to-typescript` on the exported schemas for TS types.")


if __name__ == "__main__":
    export_schemas("./schemas")
