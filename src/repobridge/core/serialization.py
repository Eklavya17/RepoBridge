"""Strict JSON encoding/decoding and JSON Schema export for the data contracts.

Decoding is driven by the dataclass type hints: unknown fields, missing fields, wrong types and
invalid enum values all raise ``ContractError`` with the path of the offending value.
"""

import dataclasses
import enum
import json
import types
import typing
from typing import Any, get_args, get_origin, get_type_hints

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


class ContractError(ValueError):
    """A record does not satisfy its data contract."""


class Record:
    """Base for every contract dataclass: normalises sequences and runs validation."""

    def __post_init__(self) -> None:
        for f in dataclasses.fields(self):  # type: ignore[arg-type]
            value = getattr(self, f.name)
            if isinstance(value, list):
                object.__setattr__(self, f.name, tuple(value))
        try:
            self._validate()
        except ContractError:
            raise
        except ValueError as exc:
            raise ContractError(f"{type(self).__name__}: {exc}") from exc

    def _validate(self) -> None:
        """Override to check field-level rules. Raise ValueError/ContractError on violation."""


class Contract(Record):
    """A top-level record that travels on its own and carries a versioned ``schema`` tag."""

    SCHEMA = ""  # overridden, e.g. "repobridge.evidence/v1"

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.SCHEMA, **encode(self)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, data: Any) -> "Contract":
        if not isinstance(data, dict):
            raise ContractError(f"{cls.__name__}: expected an object, got {type(data).__name__}")
        if data.get("schema") != cls.SCHEMA:
            raise ContractError(
                f"{cls.__name__}: schema must be {cls.SCHEMA!r}, got {data.get('schema')!r}"
            )
        return decode(cls, data, cls.__name__)

    @classmethod
    def from_json(cls, text: str) -> "Contract":
        return cls.from_dict(json.loads(text))


# --------------------------------------------------------------------------- encoding


def encode(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, list | tuple):
        return [encode(v) for v in value]
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    return value


# --------------------------------------------------------------------------- decoding

_PRIMITIVES = (str, int, float, bool)


def decode(tp: Any, value: Any, path: str) -> Any:
    origin = get_origin(tp)
    if tp is Any:
        return value
    if origin in (typing.Union, types.UnionType):
        args = get_args(tp)
        if value is None and type(None) in args:
            return None
        options = [a for a in args if a is not type(None)]
        if len(options) != 1:
            raise ContractError(f"{path}: unions of several types are not supported")
        return decode(options[0], value, path)
    if origin is tuple:
        if not isinstance(value, list | tuple):
            raise ContractError(f"{path}: expected a list, got {type(value).__name__}")
        (item_tp, _ellipsis) = get_args(tp)
        return tuple(decode(item_tp, v, f"{path}[{i}]") for i, v in enumerate(value))
    if origin is dict:
        if not isinstance(value, dict):
            raise ContractError(f"{path}: expected an object, got {type(value).__name__}")
        _key_tp, val_tp = get_args(tp)
        return {str(k): decode(val_tp, v, f"{path}.{k}") for k, v in value.items()}
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        try:
            return tp(value)
        except ValueError:
            allowed = [m.value for m in tp]
            raise ContractError(f"{path}: {value!r} is not one of {allowed}") from None
    if dataclasses.is_dataclass(tp):
        return _decode_dataclass(tp, value, path)
    if tp in _PRIMITIVES:
        if tp is float and type(value) is int:
            return float(value)
        if type(value) is not tp:
            raise ContractError(f"{path}: expected {tp.__name__}, got {type(value).__name__}")
        return value
    raise ContractError(f"{path}: unsupported type {tp!r}")


def _decode_dataclass(cls: type, data: Any, path: str) -> Any:
    if not isinstance(data, dict):
        raise ContractError(f"{path}: expected an object, got {type(data).__name__}")
    hints = get_type_hints(cls)
    fields = {f.name: f for f in dataclasses.fields(cls) if f.init}
    allowed = set(fields) | ({"schema"} if issubclass(cls, Contract) else set())
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ContractError(f"{path}: unknown field(s) {unknown}")
    kwargs = {}
    for name, f in fields.items():
        if name in data:
            kwargs[name] = decode(hints[name], data[name], f"{path}.{name}")
        elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            raise ContractError(f"{path}: missing required field {name!r}")
    try:
        return cls(**kwargs)
    except ContractError as exc:
        raise ContractError(f"{path}: {exc}") from exc


# --------------------------------------------------------------------------- JSON Schema


def json_schema(tp: Any) -> dict[str, Any]:
    """JSON Schema (draft 2020-12) for a contract or nested value type."""
    origin = get_origin(tp)
    if tp is Any:
        return {}
    if origin in (typing.Union, types.UnionType):
        options = [a for a in get_args(tp) if a is not type(None)]
        return {"anyOf": [json_schema(options[0]), {"type": "null"}]}
    if origin is tuple:
        return {"type": "array", "items": json_schema(get_args(tp)[0])}
    if origin is dict:
        return {"type": "object", "additionalProperties": json_schema(get_args(tp)[1])}
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        return {"enum": [m.value for m in tp]}
    if tp is str:
        return {"type": "string"}
    if tp is bool:
        return {"type": "boolean"}
    if tp is int:
        return {"type": "integer"}
    if tp is float:
        return {"type": "number"}
    if dataclasses.is_dataclass(tp):
        hints = get_type_hints(tp)
        props: dict[str, Any] = {}
        required: list[str] = []
        if issubclass(tp, Contract):
            props["schema"] = {"const": tp.SCHEMA}
            required.append("schema")
        for f in dataclasses.fields(tp):
            props[f.name] = json_schema(hints[f.name])
            if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
                required.append(f.name)
        out: dict[str, Any] = {"type": "object", "properties": props, "required": required}
        out["additionalProperties"] = False
        if tp.__doc__:
            out["description"] = " ".join(tp.__doc__.split())
        return out
    raise TypeError(f"no JSON Schema mapping for {tp!r}")


def contract_json_schema(cls: type[Contract]) -> dict[str, Any]:
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": cls.SCHEMA,
        "title": cls.__name__,
        **json_schema(cls),
    }
