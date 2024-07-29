import inspect
import typing as t
from enum import Enum
from pathlib import Path
from docstring_parser import parse_from_object, Docstring


from ._types import (
    TypedDict,
    NamedTuple, 
    PydanticModel,
    is_typeddict, 
    is_namedtuple,
    is_pydantic_model,
    normalize_type,
    _SUPPORTED_TYPE_MAP,
    _SUPPORTED_TYPES_REPR
)

__all__ = ('marshal_annotation', 'marshal_object', 'MarshalError')

class MarshalError(Exception):
    ...

class ParamMetadata(t.NamedTuple):
    label: str
    schema: t.Dict[str, t.Any]
    required: bool

def marshal_parameters(__params: t.Iterable[ParamMetadata]) -> t.Dict[str, t.Any]:
    properties, required_props = {}, []
    for (label, schema, required) in __params:
        properties[label] = schema
        if required:
            required_props.append(label)
    
    if not properties:
        return {}
    
    return {
        "type": "object", "properties": properties, "required": required_props
    }

def map_param_to_description(docstring: Docstring) -> t.Dict[str, str]:
    description_map = {}
    for param in docstring.params:
        if param.description:
            description_map[param.arg_name] = param.description
    return description_map

def generate_function_metadata(
    __fn: t.Callable[..., t.Any], description_map: t.Dict[str, str]
):
    for label, param in inspect.signature(__fn).parameters.items():
        schema = marshal_annotation(param.annotation)
        if label in description_map:
            schema['description'] = description_map[label]

        yield ParamMetadata(
            label=label,
            schema=schema,
            required=True if param.default is inspect._empty else False
        )

def generate_pydantic_metadata(
    __model: t.Type[PydanticModel], description_map: t.Dict[str, str]
):
    for label, field in __model.model_fields.items():
        if field.annotation is __model:
            raise MarshalError(
                f"{label!r} field cannot have the same type as the Pydantic model {__model.__name__!r}."
            )
        schema = marshal_annotation(field.annotation)
        if description := field.description or description_map.get(label):
            schema['description'] = description

        yield ParamMetadata(
            label=label,
            schema=schema,
            required=True if field.is_required() else False
        )

def generate_typeddict_metadata(
    __td: t.Type[TypedDict], description_map: t.Dict[str, str]
):
    for label, annotation in t.get_type_hints(__td).items():
        if is_typeddict(annotation) and annotation.__name__ == __td.__name__:
            raise MarshalError(
                f"{label!r} field cannot have the same type as the TypeDict class {__td.__name__!r}."
            )
        schema = marshal_annotation(annotation)
        if label in description_map:
            schema['description'] = description_map[label]

        yield ParamMetadata(
            label=label, 
            schema=schema, 
            required=False if label in __td.__dict__ else True
        )

def generate_namedtuple_metadata(
    __nt: t.Type[NamedTuple], description_map: t.Dict[str, str]
):
    for label, annotation in t.get_type_hints(__nt).items():
        if is_namedtuple(annotation) and annotation.__name__ == __nt.__name__:
            raise MarshalError(
                f"{label!r} field cannot have the same type as the NamedTuple class {__nt.__name__!r}."
            )
        schema = marshal_annotation(annotation)
        if label in description_map:
            schema['description'] = description_map[label]

        yield ParamMetadata(
            label=label, 
            schema=schema, 
            required=False if label in __nt._field_defaults else True
        )

def marshal_annotation(__annotation: t.Type | t.ForwardRef) -> t.Dict[str, t.Any]:
    """
    Marshal the annotation to tool-calling specific property map
    """

    annot, args = normalize_type(__annotation)
    if args:
        if annot in (list, t.List):
            return {'type': 'array', 'items': marshal_annotation(args[0])}
        if annot is t.Literal:
            types = {type(e) for e in args}
            if types == {str}:
                return {'enum': args, 'type': 'string'}
            elif types == {int}:
                return {'enum': args, 'type': 'integer'}
            elif types == {float}:
                return {'enum': args, 'type': 'number'}
            elif types == {bool}:
                return {'enum': args, 'type': 'boolean'}
            else:
                MarshalError("Literal args must be of same type.")
        
    if issubclass(annot, Path):
        return {'type': 'string'}
        
    if issubclass(annot, Enum):
        return {'type': 'string', 'enum': annot._member_names_}

    if (p_type := _SUPPORTED_TYPE_MAP.get(annot)) is not None:
        return {'type': p_type}
    
    generate_fn = None
    if is_pydantic_model(annot):
        generate_fn = generate_pydantic_metadata
    elif is_typeddict(annot):
        generate_fn = generate_typeddict_metadata
    elif is_namedtuple(annot):
        generate_fn = generate_namedtuple_metadata
    
    if generate_fn is not None:
        return marshal_parameters(
            generate_fn(
                annot, 
                map_param_to_description(parse_from_object(annot))
            )
        )
    raise MarshalError(f"{annot.__name__!r} type is not supported.\nSupported types: {_SUPPORTED_TYPES_REPR}")

def marshal_object(
    __obj, 
    *, 
    spec: t.Literal['base', 'claude'],
    name: t.Optional[str] = None,
    description: t.Optional[str] = None,
):
    if is_pydantic_model(__obj):
        generate_fn = generate_pydantic_metadata
    elif is_typeddict(__obj):
        generate_fn = generate_typeddict_metadata
    elif is_namedtuple(__obj):
        generate_fn = generate_namedtuple_metadata
    elif inspect.isfunction(__obj):
        generate_fn = generate_function_metadata
    else:
        MarshalError(f"Schema generation failed, given object is not supported")
    
    ds = parse_from_object(__obj)
    parameters = marshal_parameters(
        generate_fn(__obj, map_param_to_description(ds))
    )
    fn_schema = {
        'name': name or __obj.__name__, 
        'input_schema' if spec == 'claude' else 'parameters': parameters
    }
    
    if (desc := description or ds.short_description):
        fn_schema['description'] = desc

    return {'type': 'function', 'function': fn_schema}