import json
from functools import wraps
from typing import (
    Dict,
    Any,
    overload, 
    Callable, 
    Literal, 
    ParamSpec, 
    TypeVar, 
    Optional
)

from .function_calling import FunctionComponent, FunctionCall
from .function_calling.compose import extract_arguments, JsonArguments

P = ParamSpec("P")
R = TypeVar("R")

class HyperFunction:
    """
    Handles the creation of a schema for LLM function calling, as well as the validation and invocation of functions based on the provided signature or metadata.
    """
    def __init__(self) -> None:
        self._entries: Dict[str, FunctionComponent] = {}
        """Registered functions."""

    @overload
    def takeover(self) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """Register the target function by decorating it."""
    @overload
    def takeover(self, __fn: Callable[P, R]) -> Callable[P, R]:
        """
        Register the target function by passing it.
        @param __fn: The function to register.
        """
    @overload
    def takeover(self, __fn: Callable[P, R], *, docstring: str) -> Callable[P, R]:
        """
        Register the target function by passing it.
        @param __fn: The function to register.
        @param docstring: Custom docstring for the function being registered.
        """

    def takeover(
        self, 
        __fn: Optional[Callable[P, R]] = None,
        *,
        docstring: Optional[str] = None,
    ):
        def decorator(fn: Callable[P, R]):
            self._entries[fn.__name__] = FunctionComponent(fn, docstring=docstring)
            @wraps(fn)
            def __wrapper__(*args: P.args, **kwargs: P.kwargs):
                return fn(*args, **kwargs)
            return __wrapper__

        if __fn is None:
            return decorator
        else:
            return decorator(__fn)

    def __add__(self, other: "HyperFunction"):
        """Combine and create a new `HyperFunction` instance."""
        new_instance = HyperFunction()
        new_instance._entries = self._entries | other._entries
        return new_instance

    def registry(self):
        """Display registered functions."""
        print('===' * 20)
        for component in self._entries.values():
            print(component)
            print('===' * 20)

    def format(
        self, 
        __format: Optional[Literal['functionary', 'gorilla', 'mistral', 'gpt', 'claude']] = None,
        *,
        as_json: bool = False
    ):
        """
        Get registered functions in schema format
        @param __format: Formatting style to use.
        @param as_json: If True, return schema as JsON object.
        """
        formatted = [comp.schema(__format) for comp in self._entries.values()]
        return json.dumps(formatted, indent=4) if as_json else formatted
    
    @overload
    def compose(self, __signature: str) -> FunctionCall[P, R]:
        """
        Compose function-call from signature
        @param __signature: String representation of the raw function-call

        For example:
            `function_name("value", obj={"key": "value"})`
        """
    @overload
    def compose(self, *, name: str, arguments: str | Dict[str, Any]) -> FunctionCall[P, R]:
        """
        Compose function-call from function's name and raw arguments
        @param name: Name of the function.
        @param arguments: Arguments for the function in JsON or dictionary format.
        """

    def compose(
        self, 
        __signature: Optional[str] = None,
        *,
        name: Optional[str] = None,
        arguments: Optional[str | Dict[str, Any]] = None
    ) -> FunctionCall[P, R]:
        if __signature:
            fname, parsed_kwargs = extract_arguments(__signature)
        elif name and arguments:
            fname = name
            if isinstance(arguments, str):
                parsed_kwargs = JsonArguments(value=arguments).value
            else:
                parsed_kwargs = arguments
        else:
            raise ValueError("signature or (name & arguments) required to compose function-call.")
        
        if (component := self._entries.get(fname)) is None:
            raise LookupError(f"function {fname!r} not found in registry.")
        
        parsed_args: list = parsed_kwargs.pop("*args", [])
        args, kwargs = component.compose_arguments(parsed_args, parsed_kwargs) 
        return FunctionCall(component._function, *args, **kwargs)