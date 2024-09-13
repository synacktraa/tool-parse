from __future__ import annotations

from typing import Any, List


class RegistryException(Exception):
    """
    Exception raised for errors related to the tool registry.

    This exception is raised when attempting to register a tool that already exists
    or when trying to use a tool that hasn't been registered.
    """

    def __init__(self, *, name: str, registered: bool) -> None:
        """
        :param name: The name of the tool causing the exception.
        :param registered: Whether the tool is already registered or not.
        """
        if registered is True:
            message = f"Tool with name {name!r} is already registered."
        else:
            message = f"Tool with name {name!r} has not been registered."
        super().__init__(message)


class UnsupportedTypeException(Exception):
    """
    Exception raised when an unsupported type is encountered.

    This exception is raised when a type hint is not supported in the current context,
    either as a standalone type or as part of a parent type.

    """

    def __init__(
        self, *, type_hint_repr: str, parent_type_repr: str | None = None, supported_repr: str
    ) -> None:
        """
        :param type_hint_repr: String representation of the unsupported type hint.
        :param parent_type_repr: String representation of the parent type, if applicable.
        :param supported_repr: String representation of the supported types or type hints.
        """
        message = f"{type_hint_repr!r} typehint is not supported"
        if parent_type_repr:
            message += f" as {parent_type_repr!r} type"

        super().__init__(f"{message}. Supported: {supported_repr}")


class TypeMismatchException(Exception):
    """
    Exception raised when there's a mismatch between expected and received types.

    This exception is raised when a value of an unexpected type is provided during
    deserialization or type conversion.

    Examples:
        - For Enum or Path, expected_type_repr is 'str'
        - For list or set, expected_type_repr is 'list'
        - For TypedDict, NamedTuple, or Pydantic model, expected_type_repr is 'dict'
    """

    def __init__(
        self,
        *,
        expected_type_repr: str,
        target_type_repr: str | None = None,
        received_type_repr: str,
    ) -> None:
        """
        :param expected_type_repr: String representation of the expected type for deserialization.
        :param target_type_repr: String representation of the target data structure type (e.g., Enum, Path, list, set, TypedDict).
        :param received_type_repr: String representation of the actually received type.
        """
        message = f"Expected value of type {expected_type_repr!r}"
        if target_type_repr:
            message += f" for {target_type_repr!r} deserialization"
        super().__init__(f"{message}, but received value of type {received_type_repr!r} instead.")


class RecursiveParameterException(Exception):
    """
    Exception raised when a recursive parameter definition is detected.

    This exception is raised when a parameter is defined with the same type as its parent,
    which would lead to infinite recursion.
    """

    def __init__(self, *, label: str, type_base: str, type_name: str) -> None:
        """
        :param label: The label of the parameter causing the recursion.
        :param type_base: The base type (e.g., "TypedDict") of the recursive definition.
        :param type_name: The name of the object causing the recursion.
        """
        super().__init__(
            f"{label!r} parameter cannot have the same type as {type_base} {type_name!r}"
        )


class RequiredParameterException(Exception):
    """
    Exception raised when a required parameter is not provided.

    This exception is raised when a mandatory parameter is missing from a function or method call.
    """

    def __init__(self, *, label: str, type_base: str, type_name: str) -> None:
        """
        :param label: The name of the missing parameter.
        :param type_base: The base type (e.g., "function") that requires the parameter.
        :param type_name: The name of the object that requires the parameter.
        """
        super().__init__(f"{type_name!r} {type_base} required parameter {label!r} missing.")


class InvalidArgumentException(Exception):
    """
    Exception raised when an invalid argument of the correct type is provided.

    This exception is raised when an argument passes type checking but is not a valid value
    for the given context.

    """

    def __init__(self, *, arg: Any, type_base: str, valid_args: List[Any]) -> None:
        """
        :param arg: The invalid argument that was provided.
        :param type_base: The base type or category of the argument (e.g., "enum", "literal").
        :param valid_args: A list of valid arguments for the given context.
        """
        super().__init__(
            f"{arg!r} is not a valid {type_base} member. Valid arguments: {valid_args!r}"
        )
