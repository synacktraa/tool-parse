from __future__ import annotations

import inspect
import typing as t
from enum import Enum
from pathlib import Path
from types import FrameType

from docstring_parser import Docstring, parse_from_object

from . import _types as ts
from . import exceptions

__all__ = "marshal_annotation", "marshal_object"


def map_param_to_description(docstring: Docstring) -> t.Dict[str, str]:
    """
    Map parameters to their descriptions from a docstring.

    :param docstring: A Docstring object.
    """
    description_map = {}
    for param in docstring.params:
        if param.description:
            description_map[param.arg_name] = param.description
    return description_map


class ParamMetadata(t.NamedTuple):
    label: str
    schema: t.Dict[str, t.Any]
    required: bool


def marshal_parameters(__params: t.Iterable[ParamMetadata]) -> t.Dict[str, t.Any]:
    """
    Marshal parameters into a schema.

    :param __params: An iterable of ParamMetadata objects.
    """
    properties, required_props = {}, []
    for label, schema, required in __params:
        properties[label] = schema
        if required:
            required_props.append(label)

    if not properties:
        return {}

    return {"type": "object", "properties": properties, "required": required_props}


def generate_function_metadata(
    __fn: ts.Function | ts.AsyncFunction, description_map: t.Dict[str, str], namespace: ts.NameSpace
):
    """
    Generate metadata for a function.

    :param __fn: The function to generate metadata for.
    :param description_map: A dictionary mapping parameter names to descriptions.
    :param namespace: Global and local nampespace for evaluating annotation.
    """
    for label, param in ts.get_signature(__fn).parameters.items():
        annot_info = ts.extract_annotation_info(param.annotation, namespace=namespace)
        schema, is_optional = marshal_annotation(annot_info, namespace)
        if label in description_map:
            schema["description"] = description_map[label]

        yield ParamMetadata(
            label=label,
            schema=schema,
            required=bool(not is_optional and param.default is inspect._empty),
        )


def generate_pydantic_metadata(
    __model: type[ts.PydanticModel], description_map: t.Dict[str, str], namespace: ts.NameSpace
):
    """
    Generate metadata for a Pydantic model.

    :param __model: The Pydantic model to generate metadata for.
    :param description_map: A dictionary mapping field names to descriptions.
    :param namespace: Global and local nampespace for evaluating annotation.

    :raises exceptions.RecursiveParameterException: If a recursive field is detected
    """
    name = __model.__name__
    for label, field in __model.model_fields.items():
        annot_info = ts.extract_annotation_info(field.annotation, namespace=namespace)
        if annot_info[0] is __model or __model in annot_info[1]:
            raise exceptions.RecursiveParameterException(
                label=label, type_base="pydantic model", type_name=name
            )
        schema, is_optional = marshal_annotation(annot_info, namespace)
        if description := field.description or description_map.get(label):
            schema["description"] = description

        yield ParamMetadata(
            label=label, schema=schema, required=bool(not is_optional and field.is_required())
        )


def _generate_typed_metadata(
    __typed_obj: type,
    description_map: t.Dict[str, str],
    namespace: ts.NameSpace,
    has_default: t.Callable[[str], bool],
    type_base: str,
):
    """
    Generate metadata for a typed object.

    :param __typed_obj: The typed object to generate metadata from..
    :param description_map: A dictionary mapping field names to descriptions.
    :param namespace: Global and local nampespace for evaluating annotation.
    :param has_default: A function to check if a field has a default value.
    :param type_base: The base type name.

    :raises exceptions.RecursiveParameterException: If a recursive field is detected
    """
    name = __typed_obj.__name__
    for label, annotation in __typed_obj.__annotations__.items():
        annot_info = ts.extract_annotation_info(annotation, namespace=namespace)
        if annot_info[0] is __typed_obj or __typed_obj in annot_info[1]:
            raise exceptions.RecursiveParameterException(
                label=label, type_base=type_base, type_name=name
            )
        schema, is_optional = marshal_annotation(annot_info, namespace)
        if label in description_map:
            schema["description"] = description_map[label]

        yield ParamMetadata(
            label=label, schema=schema, required=not (is_optional or has_default(label))
        )


def generate_typeddict_metadata(
    __td: type[ts.TypedDict], description_map: t.Dict[str, str], namespace: ts.NameSpace
):
    """
    Generate metadata for a TypedDict.

    :param __td: The TypedDict to generate metadata for.
    :param description_map: A dictionary mapping field names to descriptions.
    :param namespace: Global and local nampespace for evaluating annotation.
    """
    return _generate_typed_metadata(
        __td,
        description_map=description_map,
        namespace=namespace,
        has_default=lambda label: hasattr(__td, label),
        type_base="TypeDict",
    )


def generate_namedtuple_metadata(
    __nt: type[ts.NamedTuple], description_map: t.Dict[str, str], namespace: ts.NameSpace
):
    """
    Generate metadata for a NamedTuple.

    :param __nt: The NamedTuple to generate metadata for.
    :param description_map: A dictionary mapping field names to descriptions.
    :param namespace: Global and local nampespace for evaluating annotation.
    """
    return _generate_typed_metadata(
        __nt,
        description_map=description_map,
        namespace=namespace,
        has_default=lambda label: label in __nt._field_defaults,
        type_base="NamedTuple",
    )


def marshal_annotation(  # noqa: C901
    __info: ts.AnnotationInfo, namespace: ts.NameSpace
) -> t.Tuple[t.Dict[str, t.Any], bool]:
    """
    Marshal the annotation info to tool-calling specific property map.

    :param __info: The annotation info to marshal.
    :param namespace: Global and local nampespace for evaluating annotation.

    :raises exceptions.UnsupportedTypeException: If the type is not supported
    """
    _type, args, is_optional = __info

    if args:
        if _type in (list, set, t.List, t.Set):
            arg_info = ts.extract_annotation_info(args[0], namespace=namespace)
            return {
                "type": "array",
                "items": marshal_annotation(arg_info, namespace)[0],
            }, is_optional

        if _type is t.Literal:
            if (arg_type := type(args[0])) is bool:
                _type = arg_type
            else:
                return {"enum": args, "type": ts._SUPPORTED_TYPE_MAP[arg_type]}, is_optional

    if ts.check_subclass(_type, Path):
        return {"type": "string"}, is_optional

    if ts.check_subclass(_type, Enum):
        return {"type": "string", "enum": _type._member_names_}, is_optional

    if (tvalue := ts._SUPPORTED_TYPE_MAP.get(_type)) is not None:
        return {"type": tvalue}, is_optional

    if ts.is_pydantic_model(_type):
        generate_fn = generate_pydantic_metadata
    elif ts.is_typeddict(_type):
        generate_fn = generate_typeddict_metadata
    elif ts.is_namedtuple(_type):
        generate_fn = generate_namedtuple_metadata
    else:
        generate_fn = None

    if generate_fn is not None:
        desc_map = map_param_to_description(parse_from_object(_type))
        return marshal_parameters(generate_fn(_type, desc_map, namespace)), is_optional

    raise exceptions.UnsupportedTypeException(
        type_hint_repr=ts.get_type_repr(_type), supported_repr=ts._SUPPORTED_TYPES_REPR
    )


def marshal_object(
    __obj: t.Any,
    *,
    spec: t.Literal["base", "claude"],
    name: str | None = None,
    description: str | None = None,
    frame: FrameType | None = None,
):
    """
    Marshal an object into a schema.

    :param __obj: The object to marshal.
    :param spec: The specification to use for marshaling.
    :param name: The name to use for the marshaled object.
    :param description: The description to use for the marshaled object.
    :param frame: The frame to extract global and local namespaces from.

    :raises ValueError: If the object type is not supported for schema generation
    """
    if ts.is_pydantic_model(__obj):
        generate_fn = generate_pydantic_metadata
    elif ts.is_typeddict(__obj):
        generate_fn = generate_typeddict_metadata
    elif ts.is_namedtuple(__obj):
        generate_fn = generate_namedtuple_metadata
    elif inspect.isfunction(__obj):
        generate_fn = generate_function_metadata
    else:
        raise ValueError(
            f"Schema generation failed, given object is not supported.\n{getattr(__obj, '__dict__', None)}"
        )

    fn_schema = {"name": name or __obj.__name__}
    ds = parse_from_object(__obj)
    if desc := description or ds.description:
        fn_schema["description"] = desc

    param_key = "input_schema" if spec == "claude" else "parameters"
    fn_schema[param_key] = marshal_parameters(
        generate_fn(__obj, map_param_to_description(ds), ts.extract_namespace(frame))
    )

    return {"type": "function", "function": fn_schema}
