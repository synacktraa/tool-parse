import ast
import inspect
import asyncio
import typing as t
from enum import Enum
from pathlib import Path

from ._types import (
    TypedDict,
    NamedTuple, 
    PydanticModel,
    is_async,
    is_typeddict, 
    is_namedtuple,
    is_pydantic_model,
    normalize_type,
    _SUPPORTED_TYPE_MAP,
    _SUPPORTED_TYPES_REPR
)

__all__ = ('compile_value', 'compile_object', 'CompileError')

class CompileError(Exception):...

P = t.ParamSpec("P")
R = t.TypeVar("R")

def run_async(coro: t.Awaitable[R]) -> R:
    """
    Gets an existing event loop to run the coroutine. 
    If there is no existing event loop, creates a new one.
    """
    try:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro)
    except RuntimeError:
        try:
            return asyncio.run(coro)
        except RuntimeError as exc:
            if "cannot be called from a running event loop" in str(exc):
                raise RuntimeError(
                    "The event loop is already running. "
                    "Add `import nest_asyncio; nest_asyncio.apply()` to your code to fix this issue."
                )
            raise exc
        
def parse_expression(__expression: str) -> t.Tuple[str, t.Dict[str, t.Any]]:
    """Parse a call expression as metadata."""
    def eval_ast_node(node: ast.AST):
        if isinstance(node, ast.Call):
            args, kwargs = [], {}
            for arg in node.args:
                args.append(eval_ast_node(arg))
            for kw in node.keywords:
                kwargs[kw.arg] = eval_ast_node(kw.value)
            return node.func.id, {'*args': args, **kwargs}
        try:
            return eval(ast.unparse(node))
        except NameError:
            raise CompileError(f"Invalid input detected in signature: {__expression!r}")
    try:
        call_node = ast.parse(__expression).body[0].value
    except SyntaxError:
        raise CompileError(f"Invalid syntax detected in call expression: {__expression!r}")
    if not isinstance(call_node, ast.Call):
        raise CompileError(f"{__expression!r} is not a valid call signature")
    return eval_ast_node(call_node)

def compile_function_object(
    __fn: t.Callable[P, R] | t.Callable[P, t.Awaitable[R]], 
    arguments: t.Dict[str, t.Any]
) -> R:
    args, kwargs = [], {}
    pos_args = arguments.pop("*args", [])
    p_args_len = len(pos_args)
    for idx, (key, param) in enumerate(inspect.signature(__fn).parameters.items()):
        default, raw_value = param.default, None
        if idx+1 <= p_args_len:
            raw_value = pos_args[idx]
        else:
            raw_value = arguments.get(key)
        if raw_value is None and default is inspect._empty:
            raise CompileError(f"{key!r} parameter is required for function {__fn.__name__!r}.")
        
        value = compile_value(param.annotation, default if raw_value is None else raw_value)
        if param.kind is inspect._ParameterKind.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[key] = value

    return run_async(__fn(*args, **kwargs)) if is_async(__fn) else  __fn(*args, **kwargs)
        
def compile_pydantic_object(
    __model: t.Type[PydanticModel], arguments: t.Dict[str, t.Any]
):
    name, fields = __model.__name__, {}
    for key, field in __model.model_fields.items():
        if key not in arguments and field.is_required():
            raise CompileError(
                f"{name!r} model required field {key!r} missing."
            )
        fields[key] = compile_value(field.annotation, arguments.get(key, field.default))
    return __model(**fields)

def compile_typeddict_object(
    __td: t.Type[TypedDict], arguments: t.Dict[str, t.Any]
):
    name, fields = __td.__name__, {}
    for key, annotation in t.get_type_hints(__td).items():
        if key not in arguments and key not in __td.__dict__:
            raise CompileError(
                f"{name!r} TypedDict required field {key!r} missing."
            )
        fields[key] = compile_value(annotation, arguments.get(key, __td.__dict__.get(key)))
    return __td(**fields)

def compile_namedtuple_object(
    __nt: t.Type[NamedTuple], arguments: t.Dict[str, t.Any]
):
    name, fields = __nt.__name__, {}
    for key, annotation in t.get_type_hints(__nt).items():
        if key not in arguments:
            raise CompileError(
                f"{name!r} NamedTuple required field {key!r} missing."
            )
        fields[key] = compile_value(annotation, arguments.get(key))
    return __nt(**fields)

def compile_value(__annotation: t.Type | t.ForwardRef, raw_value: t.Any):
    """
    Compile the raw value as instance of the given annotation.
    """
    rest_err = f"but received value of type {type(raw_value)!r} instead."
    
    annot, args = normalize_type(__annotation)
    if args:
        if annot is t.Literal:
            arg_type = type(args[0])
            if not isinstance(raw_value, arg_type):
                try:
                    raw_value = arg_type(raw_value)
                except ValueError:
                    raise CompileError(
                        f"Expected {arg_type.__name__} value for Literal parameter, {rest_err}" 
                    )
            if raw_value not in args:
                raise CompileError(
                    f"{raw_value!r} is not a valid literal. Valid literals: {args!r}"
                )
            return raw_value
            
        if annot in (list, t.List):
            if not isinstance(raw_value, list):
                raise CompileError(f"Expected list value, {rest_err}")
            return [compile_value(args[0], e) for e in raw_value]
                
    if issubclass(annot, Path):
        if not isinstance(raw_value, str):
            raise CompileError(
                f"Expected string value for `pathlib.Path` type, {rest_err}"
            )
        return Path(raw_value)
    
    if issubclass(annot, Enum):
        if not isinstance(raw_value, str):
            raise CompileError(
                f"Expected string value for {annot.__name__}, {rest_err}"
            )
        if (enum := annot._member_map_.get(raw_value)) is None:
            raise CompileError(
                f"{raw_value!r} is not a valid {annot.__name__!r} member." 
                f"Valid members: {annot._member_names_!r}"
            )
        return enum
    
    if annot in _SUPPORTED_TYPE_MAP:
        if not isinstance(raw_value, annot):
            try:
                return annot(raw_value)
            except ValueError:
                raise CompileError(
                    f"Expected parameter type {annot.__name__!r}, {rest_err}" 
                )
        return raw_value
    
    compile_fn = None
    if is_pydantic_model(annot):
        compile_fn = compile_pydantic_object            
    elif is_typeddict(annot):
        compile_fn = compile_typeddict_object
    elif is_namedtuple(annot):
        compile_fn = compile_namedtuple_object

    if compile_fn is not None:  
        if not isinstance(raw_value, dict):
            raise CompileError(
                f"Expected dictionary value for {annot.__name__}, {rest_err}"
            )
        return compile_fn(annot, raw_value)
    
    raise CompileError(
        f"{annot.__name__!r} type is not supported.\nSupported types: {_SUPPORTED_TYPES_REPR}"
    )

def compile_object(__obj: t.Any, *, arguments: t.Dict[str, t.Any]):
    if is_pydantic_model(__obj):
        compile_fn = compile_pydantic_object            
    elif is_typeddict(__obj):
        compile_fn = compile_typeddict_object
    elif is_namedtuple(__obj):
        compile_fn = compile_namedtuple_object
    elif inspect.isfunction(__obj):
        compile_fn = compile_function_object
    else:
        CompileError(f"Tool invocation failed, given object is not supported")
    
    return compile_fn(__obj, arguments=arguments)