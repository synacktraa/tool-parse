import re
import inspect
from docstring_parser import parse
from typing import (
    Callable, ParamSpec, TypeVar, Generic, Dict, Literal, Any, Optional
)

from .utils import map_param_to_description
from .schema import construct_object_schema, generate_callable_metadata
from .compose import parse_value, ComposeError

P = ParamSpec("P")
R = TypeVar("R")


class DescriptionNotFoundError(Exception):
    ...

class FunctionComponent:
    def __init__(
        self, __function: Callable[..., Any], docstring: Optional[str] = None
    ) -> None:
        self.name = __function.__name__
        self._function = __function
        self._docstring = parse(docstring or __function.__doc__)
        self._signature = inspect.signature(__function) 
        description = self._docstring.short_description
        if not description:
            raise DescriptionNotFoundError("Description is required for function-calling.")
        self.description = description

    def __repr__(self) -> str:
        splitted = re.sub(r'\b\w+\.', '', str(self._signature)).strip('(').split(")")
        fn_str = f"{self.name}(\n   " + ',\n   '.join(splitted[0].split(', ')) + "\n)"
        if len(splitted) == 2:
            fn_str += splitted[1]
        return f'{fn_str}:\n"""{self.description}"""'
    
    def schema(
        self, 
        __format: Literal['functionary', 'gorilla', 'mistral', 'gpt', 'claude']
    ) -> Dict[str, Any]:
        params_key = "input_schema" if __format == 'claude' else 'parameters'
        base_schema = {
            'name': self.name,
            'description': self.description,
            params_key: construct_object_schema(
                generate_callable_metadata(
                    self._function, map_param_to_description(self._docstring)
                ))
        }
        if __format in ('functionary', 'mistral', 'gpt'):
            return {"type": "function", "function": base_schema}
        if __format == 'gorilla':
            return {"api_call": self.name} | base_schema
        return base_schema
    
    def compose_arguments(self, raw_args: list | tuple, raw_kwargs: dict[str, Any]):
        args, kwargs = [], {} 
        p_args_len = len(raw_args)
        for idx, (key, param) in enumerate(self._signature.parameters.items()):
            default, raw_value = param.default, None
            if idx+1 <= p_args_len:
                raw_value = raw_args[idx]
            else:
                raw_value = raw_kwargs.get(key)
            if raw_value is None and default is inspect._empty:
                raise ComposeError(f"{key!r} parameter is required.")
            
            value = parse_value(param.annotation, raw_value if raw_value is not None else default)
            if param.kind is inspect._ParameterKind.POSITIONAL_ONLY:
                args.append(value)
            else:
                kwargs[key] = value

        return args, kwargs


class FunctionCall(Generic[P, R]):
    def __init__(
        self, __function: Callable[P, R], *args: P.args, **kwargs: P.kwargs
    ):
        self.name = __function.__name__
        self._function = __function
        self._args = args
        self._kwargs = kwargs

    def __repr__(self) -> str:
        args_kwargs_repr = ",\n   ".join([
            *(repr(arg) for arg in self._args),
            *(f"{key}={value!r}" for key, value in self._kwargs.items()),
        ])
        return f"{self.name}(\n   {args_kwargs_repr}\n)"
    
    @property
    def function(self):
        return self._function

    @property
    def arguments(self) -> dict[str, Any]:
        signature = inspect.signature(self._function)
        return signature.bind(*self._args, **self._kwargs).arguments.copy()

    def __call__(self) -> R:
        return self._function(*self._args, **self._kwargs)