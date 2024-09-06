import ast
import asyncio
import inspect
import json
import typing as t
from enum import Enum
from pathlib import Path

from ._types import (
    _SUPPORTED_TYPE_MAP,
    _SUPPORTED_TYPES_REPR,
    NamedTuple,
    PydanticModel,
    TypedDict,
    get_signature,
    is_async,
    is_namedtuple,
    is_pydantic_model,
    is_typeddict,
    resolve_annotation,
)

__all__ = ("compile_value", "compile_object", "CompileError")


class CompileError(Exception): ...


P = t.ParamSpec("P")
R = t.TypeVar("R")


def run_async(coro: t.Awaitable[R]) -> R:
    """
    Gets an existing event loop to run the coroutine.
    If there is no existing event loop, creates a new one.
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


def parse_expression(__expression: str) -> tuple[str, dict[str, t.Any]]:
    """Parse a call expression as metadata."""

    def eval_ast_node(node: ast.AST):
        if isinstance(node, ast.Call):
            args, kwargs = [], {}
            for arg in node.args:
                args.append(eval_ast_node(arg))
            for kw in node.keywords:
                kwargs[kw.arg] = eval_ast_node(kw.value)
            return node.func.id, {"*args": args, **kwargs}  # type: ignore[attr-defined]
        try:
            return ast.literal_eval(ast.unparse(node))
        except NameError as err:
            raise CompileError(f"Invalid input detected in signature: {__expression!r}") from err

    try:
        call_node = ast.parse(__expression).body[0].value  # type: ignore[attr-defined]
    except SyntaxError as err:
        raise CompileError(f"Invalid syntax detected in call expression: {__expression!r}") from err
    if not isinstance(call_node, ast.Call):
        raise CompileError(f"{__expression!r} is not a valid call signature")
    return eval_ast_node(call_node)


def compile_function_object(
    __fn: t.Callable[P, R] | t.Callable[P, t.Awaitable[R]], arguments: dict[str, t.Any]
) -> R:
    args, kwargs = [], {}
    pos_args = arguments.pop("*args", [])
    p_args_len = len(pos_args)
    for idx, (key, param) in enumerate(get_signature(__fn).parameters.items()):
        is_default_none = param.default is None
        default = None if param.default is inspect._empty else param.default
        raw_value = pos_args[idx] if idx + 1 <= p_args_len else arguments.get(key)

        value, is_optional = compile_value(param.annotation, raw_value)
        if value is None:
            value = default

        if not is_optional and value is None and not is_default_none:
            raise CompileError(f"{key!r} parameter is required for function {__fn.__name__!r}.")

        if param.kind is inspect._ParameterKind.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[key] = value

    return run_async(__fn(*args, **kwargs)) if is_async(__fn) else __fn(*args, **kwargs)  # type: ignore[return-value]


def compile_pydantic_object(__model: t.Type[PydanticModel], arguments: dict[str, t.Any]):
    name, fields = __model.__name__, {}
    for key, field in __model.model_fields.items():
        is_default_none = field.default is None
        value, is_optional = compile_value(field.annotation, arguments.get(key))
        if value is None:
            value = field.default

        if not is_optional and value is None and not is_default_none:
            raise CompileError(f"{name!r} model required field {key!r} missing.")

        fields[key] = value
    return __model(**fields)


def compile_typeddict_object(__td: t.Type[TypedDict], arguments: dict[str, t.Any]):
    name, fields = __td.__name__, {}
    for key, annotation in t.get_type_hints(__td).items():
        value, is_optional = compile_value(annotation, arguments.get(key))

        if not is_optional and value is None and not hasattr(__td, key):
            raise CompileError(f"{name!r} TypedDict required field {key!r} missing.")

        fields[key] = getattr(__td, key, None) if value is None else value
    return __td(**fields)


def compile_namedtuple_object(__nt: t.Type[NamedTuple], arguments: dict[str, t.Any]):
    name, fields = __nt.__name__, {}
    for key, annotation in t.get_type_hints(__nt).items():
        value, is_optional = compile_value(annotation, arguments.get(key))

        if not is_optional and value is None and key not in __nt._field_defaults:
            raise CompileError(f"{name!r} NamedTuple required field {key!r} missing.")

        fields[key] = __nt._field_defaults.get(key) if value is None else value
    return __nt(**fields)


def compile_value(  # noqa: C901
    __annotation: type | t.ForwardRef, raw_value: t.Optional[t.Any]
) -> tuple[t.Optional[t.Any], bool]:
    """
    Compile the raw value as instance of the given annotation.
    """
    rest_err = f"but received value of type {type(raw_value)!r} instead."

    annot, args, is_optional = resolve_annotation(__annotation)

    if raw_value is None:
        return None, is_optional

    if args:
        if annot is t.Literal:
            arg_types = list({type(e) for e in args})
            if len(arg_types) != 1:
                CompileError("Literal args must be of same type.")

            arg_type = arg_types[0]
            if not isinstance(raw_value, arg_type):
                try:
                    raw_value = arg_type(raw_value)
                except ValueError as err:
                    raise CompileError(
                        f"Expected {getattr(arg_type, '__name__', arg_type)!r} value for Literal parameter, {rest_err}"
                    ) from err
            if raw_value not in args:
                raise CompileError(
                    f"{raw_value!r} is not a valid literal. Valid literals: {args!r}"
                )
            return raw_value, is_optional

        if annot in (list, set, t.List, t.Set):
            if not isinstance(raw_value, list):
                raise CompileError(f"Expected list value, {rest_err}")
            return annot(compile_value(args[0], e)[0] for e in raw_value), is_optional

    if issubclass(annot, Path):
        if not isinstance(raw_value, str):
            raise CompileError(f"Expected string value for `pathlib.Path` type, {rest_err}")
        return Path(raw_value), is_optional

    if issubclass(annot, Enum):
        if not isinstance(raw_value, str):
            raise CompileError(
                f"Expected string value for {getattr(annot, '__name__', annot)!r}, {rest_err}"
            )
        if (enum := annot._member_map_.get(raw_value)) is None:
            raise CompileError(
                f"{raw_value!r} is not a valid {getattr(annot, '__name__', annot)!r} member. "
                f"Valid members: {annot._member_names_!r}"
            )
        return enum, is_optional

    if annot in _SUPPORTED_TYPE_MAP:
        if not isinstance(raw_value, annot):
            try:
                raw_value = annot(raw_value)  # type: ignore[call-arg]
            except ValueError as err:
                raise CompileError(
                    f"Expected value of type {getattr(annot, '__name__', annot)!r}, {rest_err}"
                ) from err
        return raw_value, is_optional

    compile_fn = None
    if is_pydantic_model(annot):
        compile_fn = compile_pydantic_object
    elif is_typeddict(annot):
        compile_fn = compile_typeddict_object
    elif is_namedtuple(annot):
        compile_fn = compile_namedtuple_object

    if compile_fn is not None:
        if not isinstance(raw_value, dict):
            raise CompileError(
                f"Expected dictionary value for {getattr(annot, '__name__', annot)!r}, {rest_err}"
            )
        return compile_fn(annot, raw_value), is_optional

    raise CompileError(
        f"{getattr(annot, '__name__', annot)!r} type is not supported.\nSupported types: {_SUPPORTED_TYPES_REPR}"
    )


def compile_object(__obj: t.Any, *, arguments: t.Optional[str | dict[str, t.Any]]):
    if isinstance(arguments, str):
        try:
            arguments: dict[str, t.Any] = json.loads(arguments)  # type: ignore[no-redef]
        except json.JSONDecodeError as err:
            raise ValueError("arguments is not a valid JSON object") from err

    if is_pydantic_model(__obj):
        compile_fn = compile_pydantic_object
    elif is_typeddict(__obj):
        compile_fn = compile_typeddict_object
    elif is_namedtuple(__obj):
        compile_fn = compile_namedtuple_object
    elif inspect.isfunction(__obj):
        compile_fn = compile_function_object
    else:
        CompileError("Tool invocation failed, given object is not supported")

    return compile_fn(__obj, arguments=arguments)
