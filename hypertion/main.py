import re
import inspect
from enum import EnumMeta
from typing import Callable, Any

from .info import FunctionInfo, CriteriaInfo


class HyperFunction:
    """
    Handles the creation of a schema for LLM function calling, as well as the validation and invocation of functions based on the provided signature or metadata.
    """
    def __init__(self) -> None:
        self._registered_functions: dict[str, FunctionInfo] = {}
        """Registered functions."""
        self._supported_type_mapping = {
            str: 'string', EnumMeta: None, int: 'integer', list: 'list', dict: 'dictionary'
        } # Update EnumMeta value according to its children values
        """Supported types and it's mappings"""
        self._supported_types = tuple(self._supported_type_mapping)
        """Supported types"""

    def takeover(self, description: str | None = None):
        """Register the function by decorating it to generate function schema."""
        def __wrapper__(func: Callable[..., Any]):
            _description = description or func.__doc__
            if _description is None:
                raise RuntimeError(f"No description found for {func.__name__!r}")
        
            _description = '\n'.join(
                line.strip() for line in _description.split('\n')
            )
            self._registered_functions[func.__name__] = FunctionInfo(
                obj=func, description=description
            )
            return func
        return __wrapper__
    
    @staticmethod
    def criteria(
        default: Any | None = None, *, description: str
    ): 
        """Adding criteria to parameters."""
        return CriteriaInfo(description=description, default=default)

    def _construct_mappings(self):
        """Construct schema mappings of registered functions."""
        for f_name, f_info in self._registered_functions.items():
            signature = inspect.signature(f_info.obj)
            params_dict = {"type": "object", "properties": {}, "required": []}

            for name, instance in signature.parameters.items():
                _param = instance.default
                if not isinstance(_param, CriteriaInfo):
                    raise TypeError(
                        f"Parameters of registered functions must be initialized with `criteria` method."
                    )

                choices, param_type = {}, instance.annotation
                if isinstance(param_type, EnumMeta):
                    enum_values = param_type._member_names_
                    if all(isinstance(_, str) for _ in enum_values):
                        _type = 'string'
                    elif all(isinstance(_, int) for _ in enum_values):
                        _type = 'integer'
                    else:
                        raise TypeError(
                            "All members of Enum typer parameter must be either `int` or `str`."
                        )
                    choices = {'enum': enum_values}
                elif param_type not in self._supported_types:
                    raise TypeError(
                        f"Only `str`, `int`, `list`, `dict` and `enum.Enum` types are supported."
                    )
                else:
                    _type = self._supported_type_mapping[param_type]
                
                default = _param.default
                if default and not isinstance(default, param_type):
                    raise TypeError("Default value type must be same as type hint.")
                elif not default:
                    params_dict['required'].append(name)
                
                params_dict["properties"].update({
                    name: {
                        'type': _type, 'description': _param.description, **choices
                    }
                })
                
            yield {'name': f_name, 'description': f_info.description} | {'parameters': params_dict}

    def attach_hyperfunction(self, __obj: "HyperFunction"):
        """Attach new `HyperFunction` instance in the current instance"""
        self._registered_functions.update(__obj._registered_functions)

    @property
    def as_openai_functions(self) -> list[dict[str, Any]]:
        """Return GPT based function schema."""
        return list(self._construct_mappings())
    
    @property
    def as_open_functions(self) -> list[dict[str, Any]]:
        """Return Gorilla based function schema."""
        return [{'api_call': _['name']} | _  for _ in self._construct_mappings()]

    def _marshal_signature(self, signature: str):
        """Marshal a function signature into metadata."""
        api_call, argstr = signature.split('(', 1)
        argstr = argstr.rstrip(')')
        kwargs = {'name': api_call.strip(), 'arguments': {}}

        prev, arguments = 0, []
        for match in re.finditer(r', ?[a-zA-Z_]', argstr):
            _range = match.span()
            arguments.append(argstr[prev:_range[0]])
            prev = _range[1] - 1
        arguments.append(argstr[prev:])

        for argument in arguments:
            key, value = argument.split('=')
            kwargs['arguments'][key] = eval(value)
        return kwargs

    def invoke(self, name: str, arguments: dict[str, Any]):
        """Validate and invoke the function from metadata."""
        func_info = self._registered_functions.get(name)
        if func_info is None:
            raise LookupError(f"{name!r} not found in registered functions.")
        
        signature = inspect.signature(func_info.obj)
        kwargs = {}
        for pname, param in signature.parameters.items():
            criteria = param.default
            if pname not in arguments and criteria.default is None:
                raise KeyError(f"{pname!r} argument missing.")
            
            param_type = param.annotation
            if isinstance(param_type, EnumMeta):
                _enum = param_type._member_map_.get(
                    arguments.get(pname), criteria.default
                )
                if _enum is None:
                    raise ValueError(
                        f"{arguments[pname]!r} is not a valid choice." 
                        f"Valid choices: {param_type._member_names_!r}"
                    )
                kwargs[pname] = _enum
                continue
            
            elif param_type not in self._supported_types:
                raise TypeError(
                    f"Only `str`, `int`, `list`, `dict` and `enum.Enum` types are supported."
                )
            param_value = arguments.get(pname, criteria.default)
            if not isinstance(param_value, param_type):
                raise TypeError(
                    f"Expected parameter type {param_type!r}, but received value of type {type(param_value)!r} instead."
                )
            
            kwargs[pname] = param_value
        
        return func_info.obj(**kwargs)
            
    def invoke_from_signature(self, signature: str):
        """Validate and invoke the function from signature."""
        return self.invoke(**self._marshal_signature(signature=signature))