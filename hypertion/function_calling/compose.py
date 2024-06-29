import re
import ast
from enum import Enum
from pathlib import Path
from typing import (
    Any, 
    Type, 
    List, 
    Dict, 
    TypeVar,
    Literal, 
    ForwardRef,
    get_args, 
    get_origin, 
    get_type_hints 
)
from typing_extensions import is_typeddict
from pydantic import BaseModel, Json

from .utils import (
    _SUPPORTED_TYPE_MAP, 
    _SUPPORTED_TYPES_REPR,
    is_namedtuple, 
)

PydanticT = TypeVar("PydanticT", bound=BaseModel)

class ComposeError(Exception):
    ...

class JsonArguments(BaseModel):
    value: Json[Dict[str, Any]]

SIGNATURE_REGEX = re.compile(r"^\w+\(\s*(?:(?:.|\s)*)\s*\)$")

def extract_arguments(__signature: str) -> tuple[str, Dict[str, Any]]:
    if SIGNATURE_REGEX.fullmatch(__signature.strip()) is None:
        raise ValueError(f"{__signature!r} is not a valid function-call signature.")
    
    call_node = ast.parse(__signature).body[0].value
    parameters, pos_args = {}, []

    for arg in call_node.args:
        pos_args.append(eval(ast.unparse(arg)))

    if pos_args:
        parameters["*args"] = pos_args
    for kw in call_node.keywords:
        parameters[kw.arg] = eval(ast.unparse(kw.value))

    return call_node.func.id, parameters

def create_pydantic_object(
    __model: Type[PydanticT], field_map: Dict[str, Any]
) -> PydanticT:
    fields = {}
    for key, field in __model.model_fields.items():
        if key not in field_map and field.is_required():
            raise ComposeError(
                f"{__model.__name__!r} model required field {key!r} missing."
            )
        fields[key] = parse_value(field.annotation, field_map.get(key, field.default))
    return __model(**fields)

def create_typeddict_object(__typeddict, field_map: Dict[str, Any]):
    fields = {}
    for key, annotation in get_type_hints(__typeddict).items():
        if key not in field_map and key not in __typeddict.__dict__:
            raise ComposeError(
                f"{__typeddict.__name__!r} TypedDict required field {key!r} missing."
            )
        fields[key] = parse_value(annotation, field_map.get(key, __typeddict.__dict__.get(key)))
    return fields

def create_namedtuple_object(__namedtuple, field_map: Dict[str, Any]):
    fields = {}
    for key, annotation in get_type_hints(__namedtuple).items():
        if key not in field_map:
            raise ComposeError(
                f"{__namedtuple.__name__!r} NamedTuple required field {key!r} missing."
            )
        fields[key] = parse_value(annotation, field_map.get(key))
    return tuple(fields.values())

def parse_value(__annotation: Type | ForwardRef, raw_value: Any):
    rest_err = lambda v: f"but received value of type {type(v)!r} instead."
    if isinstance(__annotation, ForwardRef):
        __annotation = __annotation._evaluate({}, {}, frozenset())
    
    origin: Type = get_origin(__annotation) or __annotation
    args = get_args(__annotation)
    if args:
        if origin is Literal:
            if not isinstance(raw_value, str):
                raise ComposeError(
                    f"Expected string value for Literal parameter, {rest_err(raw_value)}" 
                )
            if raw_value not in args:
                raise ComposeError(
                    f"{raw_value!r} is not a valid literal. Valid literals: {args!r}"
                )
            return raw_value
            
        if origin in (list, List):
            if not isinstance(raw_value, list):
                raise ComposeError(f"Expected list value, {rest_err(raw_value)}")
            return [parse_value(args[0], e) for e in raw_value]
                
    if issubclass(origin, Path):
        if not isinstance(raw_value, str):
            raise ComposeError(
                f"Expected string value for `pathlib.Path` type, {rest_err(raw_value)}"
            )
        return Path(raw_value)
    
    if issubclass(origin, Enum):
        if not isinstance(raw_value, str):
            raise ComposeError(
                f"Expected string value for {origin.__name__}, {rest_err(raw_value)}"
            )
        if (enum := origin._member_map_.get(raw_value)) is None:
            raise ComposeError(
                f"{raw_value!r} is not a valid {origin.__name__!r} member." 
                f"Valid members: {origin._member_names_!r}"
            )
        return enum
    
    if origin in _SUPPORTED_TYPE_MAP:
        if not isinstance(raw_value, origin):
            raise ComposeError(
                f"Expected parameter type {origin.__name__!r}, {rest_err(raw_value)}" 
            )
        return raw_value
    
    create_fn = None
    if issubclass(origin, BaseModel):
        create_fn = create_pydantic_object            
    elif is_typeddict(origin):
        create_fn = create_typeddict_object
    elif is_namedtuple(origin):
        create_fn = create_namedtuple_object

    if create_fn is not None:  
        if not isinstance(raw_value, dict):
            raise ComposeError(
                f"Expected dictionary value for {origin.__name__}, {rest_err(raw_value)}"
            )
        return create_fn(origin, raw_value)
    
    raise ComposeError(
        f"{origin.__name__!r} type is not supported.\nSupported types: {_SUPPORTED_TYPES_REPR}"
    )