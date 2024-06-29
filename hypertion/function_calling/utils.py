from enum import Enum
from pathlib import Path
from typing import (
    List, Dict, Literal, NamedTuple 
)
from docstring_parser import Docstring
from typing_extensions import TypedDict
from pydantic import BaseModel

_SUPPORTED_TYPE_MAP = {
    # Builtins
    str: 'string', 
    int: 'integer', 
    float: 'integer',
    bool: 'boolean', 
    list: 'array',
    dict: 'object',
     
    Path: 'string', 
    List: 'array',
    Dict: 'object',

    # object with properties
    NamedTuple: 'object',
    TypedDict: 'object',
    BaseModel: 'object',

    # enums
    Literal: 'string',
    Enum: 'string', 
}
"""Supported types mapped schema types"""

_SUPPORTED_TYPES_REPR = " | ".join(
    f"{t.__module__.split('.')[0]}.{t.__name__}" 
    if t.__module__ != 'builtins' else t.__name__ for t in _SUPPORTED_TYPE_MAP
)
"""Supported types representation"""

def is_namedtuple(__obj) -> bool:
    if (
        '__orig_bases__' in __obj.__dict__ and \
        __obj.__orig_bases__[0].__name__ == 'NamedTuple'
    ):
        return True
    return False

def map_param_to_description(docstring: Docstring) -> Dict[str, str]:
    description_map = {}
    for param in docstring.params:
        if param.description:
            description_map[param.arg_name] = param.description
    return description_map