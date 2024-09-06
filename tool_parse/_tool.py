import typing as t

from . import _types as ts
from . import compile, marshal

P = t.ParamSpec("P")
R = t.TypeVar("R")


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

    @t.overload
    def __init__(self, __obj: type[ts.TypedDict]) -> None: ...
    @t.overload
    def __init__(self, __obj: type[ts.NamedTuple]) -> None: ...
    @t.overload
    def __init__(self, __obj: type[ts.PydanticModel]) -> None: ...
    @t.overload
    def __init__(self, __obj: t.Callable[P, t.Awaitable[R]]) -> None: ...
    @t.overload
    def __init__(self, __obj: t.Callable[P, R]) -> None: ...

    def __init__(self, __obj: type):
        self.__obj = __obj
        self.name = __obj.__name__

    def __call__(self, *args: t.Any, **kwargs: t.Any) -> t.Any:
        return self.__obj(*args, **kwargs)

    def marshal(self, __spec: t.Literal["base", "claude"]) -> ts.ToolSchema:
        return marshal.marshal_object(self.__obj, spec=__spec)

    def compile(
        self,
        __expression: t.Optional[str] = None,
        *,
        arguments: t.Optional[str | dict[str, t.Any]] = None,
    ):
        if __expression:
            name, arguments = compile.parse_expression(__expression)
            if name != self.name:
                raise ValueError(f"Expected call expression for tool {self.name!r}")

        if arguments is None:
            raise ValueError("Either tool call expression or arguments required.")

        return compile.compile_object(self.__obj, arguments=arguments or {})
