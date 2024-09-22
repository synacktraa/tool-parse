from __future__ import annotations

import inspect
import sys
import typing as t
from enum import Enum
from pathlib import Path
from types import FrameType

try:
    from pydantic import BaseModel  # type: ignore[import-not-found]
    from pydantic.fields import PydanticUndefined  # type: ignore[import-not-found]
except ImportError:
    BaseModel, PydanticUndefined = None, None

from . import exceptions

NoneType = type(None)

"""
A mapping of supported types to their corresponding property types.
"""
_SUPPORTED_TYPE_MAP = {
    # Builtins
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    set: "array",
    list: "array",
    dict: "object",
    Path: "string",
    t.Set: "array",
    t.List: "array",
    t.Dict: "object",
    # object with properties
    t.NamedTuple: "object",
    t.TypedDict: "object",
    BaseModel: "object",
    # enums
    t.Literal: "string",
    Enum: "string",
}


def get_type_repr(__type: type) -> str:
    """
    Get a string representation of a type.

    :param __type: The type to represent.
    """
    get_name = lambda _t: getattr(_t, "__name__", repr(_t))

    module = getattr(__type, "__module__", "builtins")
    if module == "builtins":
        return get_name(__type)
    return f"{module}.{get_name(__type).split('.')[-1]}"


_SUPPORTED_TYPES_REPR = " | ".join(
    _repr for _repr in (get_type_repr(t) for t in _SUPPORTED_TYPE_MAP if t)
) + (" | pydantic.BaseModel" if BaseModel is None else "")


def check_subclass(__obj: t.Any, cls: t.Any):
    """
    Check if an object is a subclass of a given class.

    :param __obj: The object to check.
    :param cls: The class to check against.
    """
    return isinstance(__obj, type) and isinstance(cls, type) and issubclass(__obj, cls)


def fake_subclass_hook(cls, subcls):
    """Fake subclass check to pass pydantic's validation error"""
    return inspect.isclass(cls)


class NameSpace(t.NamedTuple):
    globals: t.Dict[str, t.Any] | None
    locals: t.Dict[str, t.Any] | None


def extract_namespace(frame: FrameType | None):
    """
    Extract global and local namespace from frame.
    """
    if frame is None:
        return NameSpace(globals=None, locals=None)

    globalns, localns = frame.f_globals, {}  # type: ignore[var-annotated]
    while frame and (_locals := frame.f_locals) is not globalns:
        localns = {**_locals, **localns}
        frame = frame.f_back

    return NameSpace(globals=globalns, locals=localns or globalns)


if sys.version_info >= (3, 9):

    def evaluate_ref(__ref: t.ForwardRef, *, namespace: NameSpace) -> type:
        """
        Evaluate a ForwardRef typehint.

        :param __ref: The ForwardRef typehint to evaluate.
        :param namespace: Associated namespace.
        """
        return __ref._evaluate(namespace[0], namespace[1], recursive_guard=frozenset())  # type: ignore[return-value]
else:

    def evaluate_ref(__ref: t.ForwardRef, *, namespace: NameSpace) -> type:
        """
        Evaluate a ForwardRef typehint.

        :param __ref: The ForwardRef typehint to evaluate.
        :param namespace: Associated namespace.
        """
        return __ref._evaluate(namespace[0], namespace[1])  # type: ignore[return-value]


def resolve_annotation(__annotation: str | type | t.ForwardRef, *, namespace: NameSpace) -> type:
    """
    Resolve an annotaion.

    :param __annotation: Annotation to resolve.
    :param namespace: Global and local nampespace for evaluating annotation.
    """
    if isinstance(__annotation, str):
        __annotation = t.ForwardRef(arg=__annotation)

    if isinstance(__annotation, t.ForwardRef):
        resolved = evaluate_ref(__annotation, namespace=namespace)
    else:
        resolved = __annotation

    from ._tool import tool

    return resolved._obj if isinstance(resolved, tool) else resolved  # type: ignore[return-value]


if sys.version_info >= (3, 10):
    from types import UnionType

    def is_union_type(__annotation: type) -> bool:
        """
        Check if the given annotation is a Union type.

        :param __annotation: The type annotation to check.
        """
        return __annotation in (t.Union, UnionType)
else:

    def is_union_type(__annotation: type) -> bool:
        """
        Check if the given annotation is a Union type.

        :param __annotation: The type annotation to check.
        """
        return __annotation is t.Union


class AnnotationInfo(t.NamedTuple):
    base_type: type
    args: list[t.Any]
    is_optional: bool


def extract_annotation_info(
    __annotation: type | t.ForwardRef, *, namespace: NameSpace
) -> AnnotationInfo:
    """
    Extract info from annotation.

    :param __annotation: The annotation to extract info from.
    :param namespace: Global and local nampespace for evaluating annotation.
    :raises exceptions.UnsupportedTypeException: If the type is not supported.
    """
    resolved = resolve_annotation(__annotation, namespace=namespace)

    is_optional = False
    base_type = t.get_origin(resolved) or resolved
    args = list(t.get_args(resolved))

    if is_union_type(base_type):  # extract base type and set is_optional to True
        if len(args) != 2 or NoneType not in args:
            raise exceptions.UnsupportedTypeException(
                type_hint_repr=repr(resolved),
                parent_type_repr="Union",
                supported_repr="'typing.Optional[<type>]', 'typing.Union[<type>, None]', '<type> | None'",
            )
        is_optional = True
        base_type, args, _ = extract_annotation_info(
            args[1 if args.index(NoneType) == 0 else 0], namespace=namespace
        )

    if base_type is t.Literal:  # validate literal type
        arg_types = list({type(e) for e in args})
        if len(arg_types) != 1:
            raise exceptions.UnsupportedTypeException(
                type_hint_repr=repr(resolved),
                parent_type_repr="Literal",
                supported_repr="args must be of same type",
            )
        if (arg_type := arg_types[0]) not in (str, int, float, bool):
            raise exceptions.UnsupportedTypeException(
                type_hint_repr=get_type_repr(arg_type),
                parent_type_repr="Literal",
                supported_repr="'str', 'int', 'float', 'bool'",
            )
    else:
        args = [resolve_annotation(arg, namespace=namespace) for arg in args]

    return AnnotationInfo(base_type=base_type, args=args, is_optional=is_optional)


# Function-related definitions
Function = t.TypeVar("Function", bound=t.Callable[..., t.Any])
AsyncFunction = t.TypeVar("AsyncFunction", bound=t.Callable[..., t.Coroutine[t.Any, t.Any, t.Any]])

if sys.version_info >= (3, 10):

    def get_signature(__f: Function | AsyncFunction, *, namespace: NameSpace):
        """
        Get the signature of a function.

        :param __f: The function to get the signature for.
        :param namespace: Global and local nampespace for evaluating annotation.
        """
        return inspect.signature(
            __f, globals=namespace.globals, locals=namespace.locals, eval_str=True
        )
else:

    def get_signature(__f: Function | AsyncFunction, *, namespace: NameSpace):
        """
        Get the signature of a function.

        :param __f: The function to get the signature for.
        :param namespace: Global and local nampespace for evaluating annotation.
        """
        return inspect.signature(__f)


def is_async(__fn) -> bool:
    """
    Check if a callable is asynchronous, accounting for wrapped callables.

    :param __fn: The callable to check.
    """
    is_coro = inspect.iscoroutinefunction(__fn)
    while hasattr(__fn, "__wrapped__"):
        __fn = __fn.__wrapped__
        is_coro = is_coro or inspect.iscoroutinefunction(__fn)
    return is_coro


# Pydantic-related definitions
PydanticModel = t.TypeVar("PydanticModel", bound=BaseModel)
"""
A type variable bound to `BaseModel` for internal use.

This PydanticModel is intended for internal type hinting and should not be used directly.
For actual PydanticModel implementations, please use the BaseModel component from the pydantic library.
"""


def is_pydantic_model(__obj):
    """
    Check if an object is a Pydantic model.

    :param __obj: The object to check.
    """
    return check_subclass(__obj, BaseModel)


# TypedDict-related definitions
class TypedDictProtocol(t.Protocol):
    __annotations__: t.Dict[str, type]
    __total__: t.ClassVar[bool]
    if sys.version_info >= (3, 9):
        __required_keys__: t.ClassVar[t.FrozenSet[str]]
        __optional_keys__: t.ClassVar[t.FrozenSet[str]]

    __subclasshook__ = classmethod(fake_subclass_hook)


TypedDict = t.TypeVar("TypedDict", bound=TypedDictProtocol)
"""
A type variable bound to `TypedDictProtocol` for internal use.

This TypedDict is intended for internal type hinting and should not be used directly.
For actual TypedDict implementations, please use the `TypedDict` component from the typing or typing_extensions library.
"""


def is_typeddict(__obj):
    """
    Check if an object is a `TypedDict`.

    :param __obj: The object to check.
    """
    return (
        isinstance(__obj, type)
        and issubclass(__obj, dict)
        and isinstance(getattr(__obj, "__total__", None), bool)
        and isinstance(getattr(__obj, "__annotations__", None), dict)
    )


# NamedTuple-related definitions
NTKeys = t.TypeVar("NTKeys", bound=t.Tuple[str, ...])


class NamedTupleProtocol(t.Protocol[NTKeys]):
    _fields: t.ClassVar[NTKeys]
    _field_defaults: t.ClassVar[t.Dict[str, t.Any]]
    __annotations__: t.Dict[str, type]

    __subclasshook__ = classmethod(fake_subclass_hook)


NamedTuple = t.TypeVar("NamedTuple", bound=NamedTupleProtocol)
"""
A type variable bound to `NamedTupleProtocol` for internal use.

This NamedTuple is intended for internal type hinting and should not be used directly.
For actual NamedTuple implementations, please use the `NamedTuple` component from the typing or typing_extensions library.
"""


def is_namedtuple(__obj):
    """
    Check if an object is a `NamedTuple`.

    :param __obj: The object to check.
    """
    return (
        isinstance(__obj, type)
        and issubclass(__obj, tuple)
        and isinstance(getattr(__obj, "_fields", None), tuple)
        and isinstance(getattr(__obj, "_field_defaults", None), dict)
        and isinstance(getattr(__obj, "__annotations__", None), dict)
        and all(isinstance(f, str) for f in __obj._fields)
    )


class Entry(t.TypedDict):
    name: t.Optional[str]
    description: t.Optional[str]
    obj: t.Any


class Property(t.TypedDict):
    type: str
    description: t.Optional[str]
    enum: t.Optional[t.Sequence[str]]  # `enum` is optional and can be a list of strings


class Parameters(t.TypedDict):
    type: str
    required: t.Sequence[str]
    properties: t.Mapping[str, Property]


class ToolMetadata(t.TypedDict):
    name: str
    description: t.Optional[str]


class ToolFunction(ToolMetadata):
    parameters: Parameters


class ClaudeToolFunction(ToolMetadata):
    input_schema: Parameters


class ToolSchema(t.TypedDict):
    type: str
    function: ToolFunction | ClaudeToolFunction
