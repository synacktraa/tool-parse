from __future__ import annotations

import sys
import typing as t

from . import _types as ts
from . import compile, marshal

__all__ = ("tool",)


class tool:
    """
    Decorator class for building independent tool.

    ```python
    @tool
    def get_current_weather(location: str) -> str:
        ...

    # Get tool schema
    print(get_current_weather.marshal('base'))

    # Invoke the tool from LLM generated arguments
    print(get_current_weather.compile(arguments={"location": "Kolkata"}))
    ```
    """

    def __init__(
        self,
        __obj: type[ts.TypedDict | ts.NamedTuple | ts.PydanticModel]
        | ts.AsyncFunction
        | ts.Function,
    ):
        self._obj = __obj
        self.name = __obj.__name__

    def __call__(self, *args, **kwargs):
        """Call the tool object. Sorry can't figure out how to add parameter type hints."""
        return self._obj(*args, **kwargs)

    def marshal(self, __spec: t.Literal["base", "claude"]) -> ts.ToolSchema:
        """Get tool schema"""
        return marshal.marshal_object(self._obj, spec=__spec, frame=sys._getframe(1))

    @t.overload
    def compile(self, __expression: str) -> t.Any:
        """
        Compile the tool from call expression

        :param __expression: For example - `'function("arg1", key="value")'`
        """

    @t.overload
    def compile(self, *, arguments: str | t.Dict[str, t.Any]) -> t.Any:
        """
        Compile the tool from raw arguments

        :param arguments: Raw arguments derived from JSON object or JSON object itself.
        """

    def compile(
        self,
        __expression: t.Optional[str] = None,
        *,
        arguments: t.Optional[str | t.Dict[str, t.Any]] = None,
    ):
        if __expression:
            name, arguments = compile.parse_expression(__expression)
            if name != self.name:
                raise ValueError(f"Expected call expression for tool {self.name!r}")

        if arguments is None:
            raise ValueError("Either tool call expression or arguments required.")

        return compile.compile_object(self._obj, arguments=arguments or {}, frame=sys._getframe(1))
