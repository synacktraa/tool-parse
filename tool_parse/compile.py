from __future__ import annotations

import ast
import asyncio
import inspect
import json
import typing as t
from enum import Enum
from pathlib import Path
from types import FrameType

from . import _types as ts
from . import exceptions

__all__ = "compile_value", "compile_object"


def run_async(coro: t.Coroutine[t.Any, t.Any, t.Any]):
    """
    Gets an existing event loop to run the coroutine.
    If there is no existing event loop, creates a new one.

    :param coro: The coroutine to run.

    :raises RuntimeError: If the event loop is already running and cannot be used
    """
    try:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro)
    except RuntimeError:
        try:
            return asyncio.run(coro)
        except RuntimeError as exc:
            if "cannot be called from a running event loop" in str(exc):
                raise RuntimeError(
                    "The event loop is already running. "
                    "Add `import nest_asyncio; nest_asyncio.apply()` to your code to fix this issue."
                ) from exc
            raise exc


def parse_expression(__expression: str) -> t.Tuple[str, t.Dict[str, t.Any]]:
    """
    Parse a call expression as metadata.

    :param __expression: The expression to parse.

    :raises ValueError: If the input is invalid or not a valid call signature
    """

    def eval_ast_node(node: ast.AST):
        if isinstance(node, ast.Call):
            args, kwargs = [], {}
            for arg in node.args:
                args.append(eval_ast_node(arg))
            for kw in node.keywords:
                kwargs[kw.arg] = eval_ast_node(kw.value)
            return node.func.id, {"*args": args, **kwargs}  # type: ignore[attr-defined]
        try:
            return ast.literal_eval(node)
        except NameError as err:
            raise ValueError(f"Invalid input detected in signature: {__expression!r}") from err

    try:
        call_node = ast.parse(__expression).body[0].value  # type: ignore[attr-defined]
    except SyntaxError as err:
        raise ValueError(f"Invalid syntax detected in call expression: {__expression!r}") from err
    if not isinstance(call_node, ast.Call):
        raise ValueError(f"{__expression!r} is not a valid call signature")
    return eval_ast_node(call_node)


def compile_function_object(
    __fn: ts.Function | ts.AsyncFunction, arguments: t.Dict[str, t.Any], namespace: ts.NameSpace
):
    """
    Compile a function object with the given arguments.

    :param __fn: The function to compile.
    :param arguments: The arguments to pass to the function.
    :param namespace: Global and local nampespace for evaluating annotation.

    :raises exceptions.RecursiveParameterException: If a required parameter is missing
    """
    args, kwargs = [], {}
    pos_args = arguments.pop("*args", [])
    p_args_len = len(pos_args)
    for idx, (key, param) in enumerate(ts.get_signature(__fn).parameters.items()):
        is_default_none = param.default is None
        default = None if param.default is inspect._empty else param.default
        raw_value = pos_args[idx] if idx + 1 <= p_args_len else arguments.get(key)

        annot_info = ts.extract_annotation_info(param.annotation, namespace=namespace)
        value, is_optional = compile_value(annot_info, namespace, raw_value)
        if value is None:
            value = default

        if not is_optional and value is None and not is_default_none:
            raise exceptions.RecursiveParameterException(
                label=key, type_base="function", type_name=__fn.__name__
            )

        if param.kind is inspect._ParameterKind.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[key] = value

    return run_async(__fn(*args, **kwargs)) if ts.is_async(__fn) else __fn(*args, **kwargs)


def compile_pydantic_object(
    __model: type[ts.PydanticModel], arguments: t.Dict[str, t.Any], namespace: ts.NameSpace
):
    """
    Compile a Pydantic model object with the given arguments.

    :param __model: The Pydantic model to compile.
    :param arguments: The arguments to pass to the model.
    :param namespace: Global and local nampespace for evaluating annotation.

    :raises exceptions.RequiredParameterException: If a required field is missing
    """
    name, fields = __model.__name__, {}
    for label, field in __model.model_fields.items():
        annot_info = ts.extract_annotation_info(field.annotation, namespace=namespace)
        if annot_info[0] is __model or __model in annot_info[1]:
            raise exceptions.RecursiveParameterException(
                label=label, type_base="pydantic model", type_name=__model.__name__
            )
        value, is_optional = compile_value(annot_info, namespace, arguments.get(label))
        if value is None and field.default not in (None, ts.PydanticUndefined):
            value = field.default

        if not is_optional and value is None and field.is_required():
            raise exceptions.RequiredParameterException(
                label=label, type_base="pydantic model", type_name=name
            )
        fields[label] = value

    return __model(**fields)


def _compile_typed_object(
    __typed_obj: type,
    arguments: t.Dict[str, t.Any],
    namespace: ts.NameSpace,
    has_default: t.Callable[[str], bool],
    get_default: t.Callable[[str], t.Any],
    type_base: str,
):
    """
    Compile a typed object with the given arguments.

    :param __typed_obj: The typed object to compile.
    :param arguments: The arguments to pass to the object.
    :param namespace: Global and local nampespace for evaluating annotation.
    :param has_default: Function to check if a field has a default value.
    :param get_default: Function to get the default value of a field.
    :param type_base: The base type of the object.

        :raises exceptions.RequiredParameterException: If a required field is missing
    """
    name, fields = __typed_obj.__name__, {}
    for label, annotation in __typed_obj.__annotations__.items():
        annot_info = ts.extract_annotation_info(annotation, namespace=namespace)
        if annot_info[0] is __typed_obj or __typed_obj in annot_info[1]:
            raise exceptions.RecursiveParameterException(
                label=label, type_base=type_base, type_name=name
            )

        value, is_optional = compile_value(annot_info, namespace, arguments.get(label))
        if not is_optional and value is None and not has_default(label):
            raise exceptions.RequiredParameterException(
                label=label, type_base=type_base, type_name=name
            )

        fields[label] = get_default(label) if value is None else value

    return __typed_obj(**fields)


def compile_typeddict_object(
    __td: type[ts.TypedDict], arguments: t.Dict[str, t.Any], namespace: ts.NameSpace
):
    """
    Compile a TypedDict object with the given arguments.

    :param __td: The TypedDict to compile.
    :param arguments: The arguments to pass to the TypedDict.
    :param namespace: Global and local nampespace for evaluating annotation.
    """
    return _compile_typed_object(
        __td,
        arguments=arguments,
        namespace=namespace,
        has_default=lambda key: hasattr(__td, key),
        get_default=lambda key: getattr(__td, key, None),
        type_base="TypedDict",
    )


def compile_namedtuple_object(
    __nt: type[ts.NamedTuple], arguments: t.Dict[str, t.Any], namespace: ts.NameSpace
):
    """
    Compile a NamedTuple object with the given arguments.

    :param __nt: The NamedTuple to compile.
    :param arguments: The arguments to pass to the NamedTuple.
    :param namespace: Global and local nampespace for evaluating annotation.
    """
    return _compile_typed_object(
        __nt,
        arguments=arguments,
        namespace=namespace,
        has_default=lambda key: key in __nt._field_defaults,
        get_default=lambda key: __nt._field_defaults.get(key),
        type_base="NamedTuple",
    )


def compile_value(  # noqa: C901
    __info: ts.AnnotationInfo, namespace: ts.NameSpace, raw_value: t.Optional[t.Any]
) -> t.Tuple[t.Optional[t.Any], bool]:
    """
    Compile the raw value based on the given annotation info.

    :param __info: The annotation info to use for compiling.
    :param namespace: Global and local nampespace for evaluating annotation.
    :param raw_value: The raw value to compile.

    :raises exceptions.TypeMismatchException: If the raw value doesn't match the expected type
    :raises exceptions.InvalidArgumentException: If the argument is invalid for Literal or Enum types
    :raises exceptions.UnsupportedTypeException: If the type is not supported
    """
    _type, args, is_optional = __info

    if raw_value is None:
        return None, is_optional

    type_repr = ts.get_type_repr(_type)
    raw_value_type = ts.get_type_repr(type(raw_value))

    def validate(e_type: type, t_type_repr: str | None = type_repr):
        nonlocal raw_value
        exc = exceptions.TypeMismatchException(
            expected_type_repr=ts.get_type_repr(e_type),
            target_type_repr=t_type_repr,
            received_type_repr=raw_value_type,
        )
        if isinstance(raw_value, e_type):
            return
        if e_type not in (str, float, int):
            raise exc
        try:
            raw_value = e_type(raw_value)
        except ValueError as err:
            raise exc from err

    if args:
        if _type is t.Literal:
            validate(type(args[0]))
            if raw_value not in args:
                raise exceptions.InvalidArgumentException(
                    arg=raw_value, type_base="Literal", valid_args=args
                )
            return raw_value, is_optional

        if _type in (list, set, t.List, t.Set):
            validate(list)
            cast = list if _type in (list, t.List) else set
            arg_info = ts.extract_annotation_info(args[0], namespace=namespace)
            return cast(compile_value(arg_info, namespace, v)[0] for v in raw_value), is_optional

    if ts.check_subclass(_type, Path):
        validate(str)
        return _type(raw_value), is_optional

    if ts.check_subclass(_type, Enum):
        validate(str)
        if (enum := _type._member_map_.get(raw_value)) is None:
            raise exceptions.InvalidArgumentException(
                arg=raw_value, type_base=f"{_type.__name__} Enum", valid_args=_type._member_names_
            )
        return enum, is_optional

    if _type in ts._SUPPORTED_TYPE_MAP:
        validate(_type, t_type_repr=None)
        return raw_value, is_optional

    if ts.is_pydantic_model(_type):
        compile_fn = compile_pydantic_object
    elif ts.is_typeddict(_type):
        compile_fn = compile_typeddict_object
    elif ts.is_namedtuple(_type):
        compile_fn = compile_namedtuple_object
    else:
        compile_fn = None

    if compile_fn is not None:
        validate(dict)
        return compile_fn(_type, raw_value, namespace), is_optional

    raise exceptions.UnsupportedTypeException(
        type_hint_repr=type_repr, supported_repr=ts._SUPPORTED_TYPES_REPR
    )


def compile_object(
    __obj: t.Any, *, arguments: t.Optional[str | t.Dict[str, t.Any]], frame: FrameType | None = None
):
    """
    Compile an object with the given arguments.

    :param __obj: The object to compile.
    :param arguments: The arguments to pass to the object.
    :param frame: The frame to extract global and local namespaces from.

    :raises ValueError: If the arguments are not a valid JSON object or if the object type is not supported
    """
    if isinstance(arguments, str):
        try:
            arguments: t.Dict[str, t.Any] = json.loads(arguments)  # type: ignore[no-redef]
        except json.JSONDecodeError as err:
            raise ValueError("arguments is not a valid JSON object") from err

    if ts.is_pydantic_model(__obj):
        compile_fn = compile_pydantic_object
    elif ts.is_typeddict(__obj):
        compile_fn = compile_typeddict_object
    elif ts.is_namedtuple(__obj):
        compile_fn = compile_namedtuple_object
    elif inspect.isfunction(__obj):
        compile_fn = compile_function_object
    else:
        raise ValueError("Tool invocation failed, given object is not supported")

    return compile_fn(__obj, arguments, ts.extract_namespace(frame))
