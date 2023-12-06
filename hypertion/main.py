import inspect
from typing import Callable, Any

from .import types
from ._utils import helpers, info


class HyperFunction:
    """
    Handles the creation of a schema for LLM function calling, as well as the validation and invocation of functions based on the provided signature or metadata.
    """
    def __init__(self) -> None:
        self._registered_functions: dict[str, info.FunctionInfo] = {}
        """Registered functions."""

    def takeover(self, description: str | None = None):
        """Register the function by decorating it to generate function schema."""
        def __wrapper__(func: Callable[..., Any]):
            _description = description or func.__doc__
            if _description is None:
                raise RuntimeError(f"No description found for {func.__name__!r}")
        
            _description = '\n'.join(
                line.strip() for line in _description.split('\n')
            )
            self._registered_functions[func.__name__] = info.FunctionInfo(
                memloc=func, description=description
            )
            return func
        return __wrapper__
    
    @staticmethod
    def criteria(
        default: Any | None = None, *, description: str
    ): 
        """Adding criteria to parameters."""
        return info.CriteriaInfo(description=description, default=default)

    def _construct_mappings(self):
        """Construct schema mappings of registered functions."""
        for f_name, f_info in self._registered_functions.items():
            signature = inspect.signature(f_info.memloc)
            properties, required = {}, []

            for name, instance in signature.parameters.items():
                criteria = instance.default
                if not isinstance(criteria, info.CriteriaInfo):
                    raise TypeError(
                        f"Parameters of registered functions must be initialized with `criteria` method."
                    )

                default, annotation = criteria.default, instance.annotation
                if default and not isinstance(default, annotation):
                    raise TypeError(
                        f"{name!r} parameter is type-hinted as {annotation.__name__!r} but default value is of type {type(default).__name__!r}"
                    )
                elif not default:
                    required.append(name)

                properties[name] = helpers.construct_property_map(
                    annotation=annotation, description=criteria.description
                )

            parameter_map = {}
            if properties:
                parameter_map = {"type": "object", "properties": properties}
            if required:
                parameter_map['required'] = required
                
            yield {'name': f_name, 'description': f_info.description} | {'parameters': parameter_map}

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
        return [{'api_call': _['name']} | _ for _ in self._construct_mappings()]

    def invoke(self, __signature_or_metadata: types.Signature | types.Metadata):
        """Validate and invoke the function from signature or metadata."""
        function = __signature_or_metadata
        if isinstance(function, types.Signature):
            function = function.as_metadata()

        function_info = self._registered_functions.get(function.name)
        if function_info is None:
            raise LookupError(f"{function.name!r} not found in registered functions.")
        
        signature, forged_kwargs = inspect.signature(function_info.memloc), {}
        for param_name, param in signature.parameters.items():
            criteria = param.default
            if param_name not in function.arguments and criteria.default is None:
                raise KeyError(
                    f"{function.name!r} function required parameter {param_name!r} missing."
                )
            
            forged_kwargs[param_name] = helpers.forge_parameter(
                annotation=param.annotation, value=function.arguments.get(param_name, criteria.default)
            )
        
        return function_info.memloc(**forged_kwargs)