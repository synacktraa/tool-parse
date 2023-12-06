import re
from typing import Any

from pydantic import BaseModel


class Metadata(BaseModel):
    name: str
    arguments: dict[str, Any]


class Signature:
    def __init__(self, __signature: str) -> None:
        self.__signature = __signature
    
    def __repr__(self) -> str:
        return self.__signature

    def as_metadata(self) -> "Metadata":
        """Marshal a function signature into metadata."""
        api_call, argstr = self.__signature.split('(', 1)
        arguments, argstr = {}, argstr.rstrip(')')

        prev, pairs = 0, []
        for match in re.finditer(r', ?[a-zA-Z_]', argstr):
            _range = match.span()
            pairs.append(argstr[prev:_range[0]])
            prev = _range[1] - 1
        pairs.append(argstr[prev:])

        for pair in pairs:
            key, value = pair.split('=')
            arguments[key] = eval(value)

        return Metadata(name=api_call.strip(), arguments=arguments)