import inspect
from enum import Enum
from pathlib import Path
from typing import (
    Any, 
    Type, 
    List, 
    Dict, 
    Literal, 
    Iterable,
    Callable, 
    NamedTuple, 
    ForwardRef,
    get_args, 
    get_origin, 
    get_type_hints 
)
from typing_extensions import is_typeddict
from docstring_parser import parse_from_object
from pydantic import BaseModel

from .utils import (
    _SUPPORTED_TYPE_MAP, 
    _SUPPORTED_TYPES_REPR,
    is_namedtuple, 
    map_param_to_description
)

class SchemaError(Exception):
    ...

class ParamMetadata(NamedTuple):
    label: str
    schema: Dict[str, Any]
    required: bool


def construct_object_schema(__params: Iterable[ParamMetadata]) -> Dict[str, Any]:
    """Construct object schema with properties."""
    properties, required_props = {}, []
    for (label, schema, required) in __params:
        properties[label] = schema
        if required:
            required_props.append(label)
    
    if not properties:
        return {}
    
    return {
        "type": "object", 
        "properties": properties, 
        **({"required": required_props} if required_props else {}) 
    }

def parse_type(__annotation: Type | ForwardRef) -> Dict[str, Any]:
    """
    Parse the annotation to function-calling specific type map
    """
    if isinstance(__annotation, ForwardRef):
        __annotation = __annotation._evaluate({}, {}, frozenset())

    origin: Type = get_origin(__annotation) or __annotation
    args = get_args(__annotation)
    if args:
        if origin is Literal:
            return {'type': 'string', 'enum': list(args)}
        if origin in (list, List):
            return {'type': 'array', 'items': parse_type(args[0])}
        
    if issubclass(origin, Path):
        return {'type': 'string'}
        
    if issubclass(origin, Enum):
        return {'type': 'string', 'enum': origin._member_names_}

    if (_type := _SUPPORTED_TYPE_MAP.get(origin)) is not None:
        return {'type': _type}
    
    generate_fn = None
    if issubclass(origin, BaseModel):
        generate_fn = generate_pydantic_metadata
    elif is_typeddict(origin):
        generate_fn = generate_typeddict_metadata
    elif is_namedtuple(origin):
        generate_fn = generate_namedtuple_metadata
    
    if generate_fn is not None:
        return construct_object_schema(
            generate_fn(
                origin, description_map=map_param_to_description(
                    parse_from_object(origin))
            )
        )
    raise SchemaError(f"{origin.__name__!r} type is not supported.\nSupported types: {_SUPPORTED_TYPES_REPR}")

def generate_callable_metadata(
    __cb: Callable[..., Any], description_map: Dict[str, str]
):
    for label, param in inspect.signature(__cb).parameters.items():
        schema = parse_type(param.annotation)
        if label in description_map:
            schema['description'] = description_map[label]

        yield ParamMetadata(
            label=label,
            schema=schema,
            required=True if param.default is inspect._empty else False
        )

def generate_pydantic_metadata(
    __model: Type[BaseModel], description_map: Dict[str, str]
):
    for label, field in __model.model_fields.items():
        if field.annotation is __model:
            raise SchemaError(
                f"{label!r} field cannot have the same type as the Pydantic model {__model.__name__!r}."
            )
        schema = parse_type(field.annotation)
        if description := field.description or description_map.get(label):
            schema['description'] = description

        yield ParamMetadata(
            label=label,
            schema=schema,
            required=True if field.is_required() else False
        )

def generate_typeddict_metadata(
    __typeddict, description_map: Dict[str, str]
):
    for label, annotation in get_type_hints(__typeddict).items():
        if is_typeddict(annotation) and annotation.__name__ == __typeddict.__name__:
            raise SchemaError(
                f"{label!r} field cannot have the same type as the TypeDict class {__typeddict.__name__!r}."
            )
        schema = parse_type(annotation)
        if label in description_map:
            schema['description'] = description_map[label]

        yield ParamMetadata(
            label=label, 
            schema=schema, 
            required=False if label in __typeddict.__dict__ else True
        )

def generate_namedtuple_metadata(
    __namedtuple, description_map: Dict[str, str]
):
    for label, annotation in get_type_hints(__namedtuple).items():
        if is_namedtuple(annotation) and annotation.__name__ == __namedtuple.__name__:
            raise SchemaError(
                f"{label!r} field cannot have the same type as the NamedTuple class {__namedtuple.__name__!r}."
            )
        schema = parse_type(annotation)
        if label in description_map:
            schema['description'] = description_map[label]

        yield ParamMetadata(
            label=label, schema=schema, required=True
        )