import inspect
import typing as t
from enum import Enum
from pathlib import Path

from docstring_parser import Docstring, parse_from_object

from ._types import (
    _SUPPORTED_TYPE_MAP,
    _SUPPORTED_TYPES_REPR,
    NamedTuple,
    PydanticModel,
    TypedDict,
    get_signature,
    is_namedtuple,
    is_pydantic_model,
    is_typeddict,
    resolve_annotation,
)

__all__ = ("marshal_annotation", "marshal_object", "MarshalError")


class MarshalError(Exception): ...


class ParamMetadata(t.NamedTuple):
    label: str
    schema: dict[str, t.Any]
    required: bool


def marshal_parameters(__params: t.Iterable[ParamMetadata]) -> dict[str, t.Any]:
    properties, required_props = {}, []
    for label, schema, required in __params:
        properties[label] = schema
        if required:
            required_props.append(label)

    if not properties:
        return {}

    return {"type": "object", "properties": properties, "required": required_props}


def map_param_to_description(docstring: Docstring) -> dict[str, str]:
    description_map = {}
    for param in docstring.params:
        if param.description:
            description_map[param.arg_name] = param.description
    return description_map


def generate_function_metadata(__fn: t.Callable[..., t.Any], description_map: dict[str, str]):
    for label, param in get_signature(__fn).parameters.items():
        schema, is_optional = marshal_annotation(param.annotation)
        if label in description_map:
            schema["description"] = description_map[label]

        yield ParamMetadata(
            label=label,
            schema=schema,
            required=bool(not is_optional and param.default is inspect._empty),
        )


def generate_pydantic_metadata(__model: t.Type[PydanticModel], description_map: dict[str, str]):
    for label, field in __model.model_fields.items():
        if field.annotation is __model:
            raise MarshalError(
                f"{label!r} field cannot have the same type as the Pydantic model {__model.__name__!r}."
            )
        schema, is_optional = marshal_annotation(field.annotation)
        if description := field.description or description_map.get(label):
            schema["description"] = description

        yield ParamMetadata(
            label=label, schema=schema, required=bool(not is_optional and field.is_required())
        )


def generate_typeddict_metadata(__td: t.Type[TypedDict], description_map: dict[str, str]):
    for label, annotation in t.get_type_hints(__td).items():
        if is_typeddict(annotation) and annotation.__name__ == __td.__name__:
            raise MarshalError(
                f"{label!r} field cannot have the same type as the TypeDict class {__td.__name__!r}."
            )
        schema, is_optional = marshal_annotation(annotation)
        if label in description_map:
            schema["description"] = description_map[label]

        yield ParamMetadata(
            label=label, schema=schema, required=not (is_optional or hasattr(__td, label))
        )


def generate_namedtuple_metadata(__nt: t.Type[NamedTuple], description_map: dict[str, str]):
    for label, annotation in t.get_type_hints(__nt).items():
        if is_namedtuple(annotation) and annotation.__name__ == __nt.__name__:
            raise MarshalError(
                f"{label!r} field cannot have the same type as the NamedTuple class {__nt.__name__!r}."
            )
        schema, is_optional = marshal_annotation(annotation)
        if label in description_map:
            schema["description"] = description_map[label]

        yield ParamMetadata(
            label=label, schema=schema, required=not (is_optional or label in __nt._field_defaults)
        )


def marshal_annotation(__annotation: t.Type | t.ForwardRef) -> tuple[dict[str, t.Any], bool]:  # noqa: C901
    """
    Marshal the annotation to tool-calling specific property map
    """

    annot, args, is_optional = resolve_annotation(__annotation)

    if args:
        if annot in (list, t.List):
            return {"type": "array", "items": marshal_annotation(args[0])[0]}, is_optional
        if annot is t.Literal:
            arg_types = list({type(e) for e in args})
            if len(arg_types) != 1:
                raise MarshalError("Literal args must be of same type.")

            arg_type = arg_types[0]
            if arg_type not in (str, int, float, bool):
                raise MarshalError(
                    f"{getattr(arg_type, '__name__', arg_type)!r} type is not supported in typing.Literal."
                )
            return {"enum": args, "type": _SUPPORTED_TYPE_MAP[arg_type]}, is_optional

    if issubclass(annot, Path):
        return {"type": "string"}, is_optional

    if issubclass(annot, Enum):
        return {"type": "string", "enum": annot._member_names_}, is_optional

    if (_type := _SUPPORTED_TYPE_MAP.get(annot)) is not None:
        return {"type": _type}, is_optional

    generate_fn = None
    if is_pydantic_model(annot):
        generate_fn = generate_pydantic_metadata
    elif is_typeddict(annot):
        generate_fn = generate_typeddict_metadata
    elif is_namedtuple(annot):
        generate_fn = generate_namedtuple_metadata

    if generate_fn is not None:
        return marshal_parameters(
            generate_fn(annot, map_param_to_description(parse_from_object(annot)))
        ), is_optional
    raise MarshalError(
        f"{getattr(annot, '__name__', annot)!r} type is not supported.\nSupported types: {_SUPPORTED_TYPES_REPR}"
    )


def marshal_object(
    __obj,
    *,
    spec: t.Literal["base", "claude"],
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
        MarshalError("Schema generation failed, given object is not supported")

    fn_schema = {"name": name or __obj.__name__}
    ds = parse_from_object(__obj)
    if desc := description or ds.description:
        fn_schema["description"] = desc

    parameters = marshal_parameters(generate_fn(__obj, map_param_to_description(ds)))
    fn_schema["input_schema" if spec == "claude" else "parameters"] = parameters

    return {"type": "function", "function": fn_schema}
