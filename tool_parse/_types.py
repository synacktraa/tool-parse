import sys
import typing as t
from enum import Enum
from pathlib import Path
from inspect import iscoroutinefunction

try:
    from pydantic import BaseModel # type: ignore[import]
except ImportError:
    BaseModel = None


_SUPPORTED_TYPE_MAP = {
    # Builtins
    str: 'string',
    int: 'integer',
    float: 'number',
    bool: 'boolean',
    set: 'array',
    list: 'array',
    dict: 'object',
     
    Path: 'string',
    t.Set: 'array',
    t.List: 'array',
    t.Dict: 'object',

    # object with properties
    t.NamedTuple: 'object',
    t.TypedDict: 'object',
    BaseModel: 'object',

    # enums
    t.Literal: 'string',
    Enum: 'string', 
}
"""Supported types mapped property types"""

def get_type_repr(t):
    if t is None:
        return "`pydantic.BaseModel`"
    if t.__module__ == 'builtins':
        return f"`{t.__name__}`"
    return f"`{t.__module__.split('.')[0]}.{t.__name__}`"

_SUPPORTED_TYPES_REPR = " | ".join(repr for repr in (get_type_repr(t) for t in _SUPPORTED_TYPE_MAP))


def has_orig_bases(__obj, __base: str):
    if (
        '__orig_bases__' in __obj.__dict__ and \
        __obj.__orig_bases__[0].__name__ == __base
    ):
        return True
    return False

def normalize_type(__annot: t.Type | t.ForwardRef) -> tuple[t.Type, list[t.Any]]:
    if isinstance(__annot, t.ForwardRef):
        ns = getattr(__annot, "__globals__", None)
        __annot = __annot._evaluate(ns, ns, frozenset())
    return t.get_origin(__annot) or __annot, list(t.get_args(__annot))

def is_async(__fn: t.Callable[..., t.Any]) -> bool:
    """Returns true if the callable is async, accounting for wrapped callables"""
    is_coro = iscoroutinefunction(__fn)
    while hasattr(__fn, "__wrapped__"):
        __fn = __fn.__wrapped__  # type: ignore - dynamic
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
    
    is_class = isinstance(__obj, type)
    if sys.version_info < (3, 10):
        if len(typing.get_args(__obj)) == 0:
            return False
        return is_class and issubclass(typing.get_args(__obj)[0], BaseModel)
    return is_class and issubclass(__obj, BaseModel)


# TypedDict-related definitions
class TypedDictInstance(t.Protocol):
    __annotations__: t.Dict[str, t.Type]
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
    __annotations__: t.Dict[str, t.Type]

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