import inspect
import types as pytypes
import typing as t
from enum import Enum
from inspect import iscoroutinefunction
from pathlib import Path

try:
    from pydantic import BaseModel  # type: ignore[import-not-found]
except ImportError:
    BaseModel = None


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
"""Supported types mapped property types"""


def get_type_repr(_t: t.Optional[type]) -> str:
    get_type_name = lambda _t: getattr(_t, "__name__", str(_t))
    if _t is None:
        return "`pydantic.BaseModel`"
    if _t.__module__ == "builtins":
        return f"`{get_type_name(_t)}`"
    return f"`{_t.__module__.split('.')[0]}.{get_type_name(_t)}`"


_SUPPORTED_TYPES_REPR = " | ".join(
    _repr for _repr in (get_type_repr(t) for t in _SUPPORTED_TYPE_MAP)
)


def has_orig_bases(__obj: object, __base: str) -> bool:
    if (bases := getattr(__obj, "__orig_bases__", None)) is None:
        return False
    return bool(bases[0].__name__ == __base)


class Annotation(t.NamedTuple):
    type: type
    args: list[t.Any]
    is_optional: bool


def eval_ref(ref: t.ForwardRef) -> type:
    ns = getattr(ref, "__globals__", None)
    return ref._evaluate(ns, ns, recursive_guard=frozenset())  # type: ignore[return-value]


def resolve_annotation(__annot: type | t.ForwardRef) -> Annotation:
    if isinstance(__annot, t.ForwardRef):
        __annot = eval_ref(__annot)

    is_optional = False
    _type, args = t.get_origin(__annot) or __annot, list(t.get_args(__annot))
    if _type in (t.Union, pytypes.UnionType):
        if len(args) != 2 or type(None) not in args:
            raise TypeError(
                "Only `typing.Optional[<type>]`, `typing.Union[<type>, None] and `<type> | None` union types are supported."
            )
        is_optional = True
        _type, args, _ = resolve_annotation(args[1 if args.index(type(None)) == 0 else 0])

    return Annotation(type=_type, args=args, is_optional=is_optional)


def get_signature(__f: t.Any) -> inspect.Signature:
    return inspect.signature(__f, eval_str=True)


def is_async(__fn: t.Callable[..., t.Any]) -> bool:
    """Returns true if the callable is async, accounting for wrapped callables"""
    is_coro = iscoroutinefunction(__fn)
    while hasattr(__fn, "__wrapped__"):
        __fn = __fn.__wrapped__
        is_coro = is_coro or iscoroutinefunction(__fn)
    return is_coro


# Pydantic-related definitions
PydanticModel = t.TypeVar("PydanticModel", bound=BaseModel)
"""
A type variable bound to `BaseModel` for internal use.

This PydanticModel is intended for internal type hinting and should not be used directly.
For actual PydanticModel implementations, please use the BaseModel component from the pydantic library.
"""


def is_pydantic_model(__obj):
    if BaseModel is None:
        return False

    return isinstance(__obj, type) and issubclass(__obj, BaseModel)


# TypedDict-related definitions
class TypedDictInstance(t.Protocol):
    __annotations__: t.Dict[str, type]
    __required_keys__: t.FrozenSet[str]
    __optional_keys__: t.FrozenSet[str]


TypedDict = t.TypeVar("TypedDict", bound=TypedDictInstance)
"""
A type variable bound to `TypedDictInstance` for internal use.

This TypedDict is intended for internal type hinting and should not be used directly.
For actual TypedDict implementations, please use the `TypedDict` component from the typing or typing_extensions library.
"""


def is_typeddict(__obj):
    return has_orig_bases(__obj, "TypedDict")


# NamedTuple-related definitions
NTKeys = t.TypeVar("NTKeys", bound=tuple[str, ...])


class NamedTupleInstance(t.Protocol[NTKeys]):
    _fields: NTKeys
    _field_defaults: t.Dict[str, t.Any]
    __annotations__: t.Dict[str, type]


NamedTuple = t.TypeVar("NamedTuple", bound=NamedTupleInstance)
"""
A type variable bound to `NamedTupleInstance` for internal use.

This NamedTuple is intended for internal type hinting and should not be used directly.
For actual NamedTuple implementations, please use the `NamedTuple` component from the typing or typing_extensions library.
"""


def is_namedtuple(__obj):
    return has_orig_bases(__obj, "NamedTuple")


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
