"""Fail-closed validator for the JSON Schema subset emitted by this package.

This is not a general Draft 2020-12 implementation. Unknown assertion keywords,
remote references and recursive depth are rejected. Original scientific and
stage semantics remain the responsibility of contracts/validation, not schema.
"""
from datetime import date, datetime
import math
import re
from .contracts import canonical, require

ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "contentMediaType"}
ASSERTIONS = {"$defs", "$ref", "type", "properties", "required", "additionalProperties", "items",
              "minItems", "maxItems", "uniqueItems", "minLength", "pattern", "format", "const", "enum", "anyOf"}


def _check_schema(schema, depth=0):
    require(depth < 64 and isinstance(schema, dict), "SCHEMA_OBJECT_DEPTH_REQUIRED")
    require(set(schema) <= ASSERTIONS | ANNOTATIONS, "UNSUPPORTED_SCHEMA_ASSERTION")
    for key in ("$defs", "properties"):
        if key in schema:
            require(isinstance(schema[key], dict), "SCHEMA_NAMED_OBJECT_REQUIRED")
            for child in schema[key].values():
                _check_schema(child, depth + 1)
    if "items" in schema:
        _check_schema(schema["items"], depth + 1)
    if "anyOf" in schema:
        require(isinstance(schema["anyOf"], list) and schema["anyOf"], "SCHEMA_ANYOF_REQUIRED")
        for child in schema["anyOf"]:
            _check_schema(child, depth + 1)
    if "type" in schema:
        require(schema["type"] in ("object", "array", "string", "number", "integer", "boolean", "null"), "SUPPORTED_SCHEMA_TYPE_REQUIRED")
    if "additionalProperties" in schema:
        require(type(schema["additionalProperties"]) is bool, "SCHEMA_ADDITIONAL_BOOLEAN_REQUIRED")
    if "format" in schema:
        require(schema["format"] in ("date", "date-time"), "SUPPORTED_SCHEMA_FORMAT_REQUIRED")
    if "$ref" in schema:
        require(isinstance(schema["$ref"], str) and schema["$ref"].startswith("#/$defs/"), "LOCAL_SCHEMA_REF_ONLY")


def validate_schema_packet(schema, packet):
    _check_schema(schema)

    def validate(node, value, depth=0):
        require(depth < 64, "SCHEMA_PACKET_DEPTH_REQUIRED")
        if "$ref" in node:
            target = schema
            for token in node["$ref"][2:].split("/"):
                token = token.replace("~1", "/").replace("~0", "~")
                require(isinstance(target, dict) and token in target, "SCHEMA_REF_TARGET_REQUIRED")
                target = target[token]
            validate(target, value, depth + 1)
        if "anyOf" in node:
            accepted = False
            for candidate in node["anyOf"]:
                try:
                    validate(candidate, value, depth + 1)
                    accepted = True
                    break
                except ValueError:
                    pass
            require(accepted, "SCHEMA_ANYOF_FAILED")
        if "const" in node:
            require(canonical(value) == canonical(node["const"]), "SCHEMA_CONST_FAILED")
        if "enum" in node:
            require(any(canonical(value) == canonical(item) for item in node["enum"]), "SCHEMA_ENUM_FAILED")
        expected_type = node.get("type")
        matches = {"object": type(value) is dict, "array": type(value) is list,
                   "string": type(value) is str, "number": type(value) in (int, float) and math.isfinite(value),
                   "integer": type(value) is int, "boolean": type(value) is bool, "null": value is None}
        require(expected_type is None or matches[expected_type], "SCHEMA_TYPE_FAILED")
        if isinstance(value, dict):
            require(set(node.get("required", [])) <= set(value), "SCHEMA_REQUIRED_FAILED")
            properties = node.get("properties", {})
            require(node.get("additionalProperties", True) or set(value) <= set(properties), "SCHEMA_ADDITIONAL_PROPERTY_FAILED")
            for key in set(value) & set(properties):
                validate(properties[key], value[key], depth + 1)
        if isinstance(value, list):
            require(len(value) >= node.get("minItems", 0) and len(value) <= node.get("maxItems", float("inf")), "SCHEMA_ARRAY_LENGTH_FAILED")
            if node.get("uniqueItems"):
                require(len({canonical(item) for item in value}) == len(value), "SCHEMA_UNIQUE_ITEMS_FAILED")
            if "items" in node:
                for item in value:
                    validate(node["items"], item, depth + 1)
        if isinstance(value, str):
            require(len(value) >= node.get("minLength", 0), "SCHEMA_STRING_LENGTH_FAILED")
            if "pattern" in node:
                require(re.search(node["pattern"], value) is not None, "SCHEMA_PATTERN_FAILED")
            if node.get("format") == "date":
                require(date.fromisoformat(value).isoformat() == value, "SCHEMA_DATE_FAILED")
            if node.get("format") == "date-time":
                require(datetime.fromisoformat(value).utcoffset() is not None, "SCHEMA_AWARE_DATETIME_FAILED")

    validate(schema, packet)
    return {"status": "STATIC_CONTRACT_PASS", "validator_scope": "ONLY_EMITTED_SCHEMA_SUBSET",
            "general_draft_2020_12_validator": False, "scientific_certified": False}
