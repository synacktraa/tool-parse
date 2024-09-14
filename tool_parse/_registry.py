from __future__ import annotations

import json
import sys
import typing as t
from pathlib import Path

from . import _types as ts
from . import compile, exceptions, marshal

__all__ = ("ToolRegistry",)


class ToolRegistry:
    """
    A versatile registry designed to manage a variety of tools, including
    function(both synchronous/asynchronous), `pydantic.BaseModel`, `typing.TypedDict`, and `typing.NamedTuple`.

    It provides the capability to generate schemas for these tools, which are essential for LLM tool-calling.
    Additionally, it allows for the invocation of tools using their metadata -- name & raw arguments.
    """

    def __init__(self, *, override: bool = False) -> None:
        """
        Create a new tool registry.
        :param override: When set to True, allows the new tool to replace a previously registered tool with the same name.
        """
        self._override = override
        self.spec: t.Literal["base", "claude"] = "base"
        self.__entries: dict[str, ts.Entry] = {}

    def __repr__(self) -> str:
        return f"ToolRegistry(num_tools={len(self)})"

    def __len__(self) -> int:
        return len(self.__entries)

    def __contains__(self, value: str):
        return value in self.__entries

    def __register(
        self, obj: type, name: t.Optional[str] = None, description: t.Optional[str] = None
    ):
        key = name or obj.__name__
        entry = self.__entries.get(key)
        if (entry and entry["obj"] is not obj) and not self._override:
            raise exceptions.RegistryException(name=key, registered=True)

        self.__entries[key] = ts.Entry(name=key, description=description, obj=obj)

    def __setitem__(self, key: str, value: type) -> None:
        self.__register(obj=value, name=key)

    def __getitem__(self, key: str) -> ts.ToolSchema:
        entry = self.__entries[key]
        return marshal.marshal_object(
            entry["obj"],
            spec=self.spec,
            name=entry["name"],
            description=entry["description"],
            frame=sys._getframe(1),
        )

    def __add__(self, other: "ToolRegistry"):
        """Combine and create a new `ToolRegistry` instance."""
        new_registry = ToolRegistry()
        new_registry.__entries = {**self.__entries, **other.__entries}
        return new_registry

    @t.overload
    def register(
        self,
        __obj: t.Optional[type[ts.TypedDict]] = None,
        *,
        name: t.Optional[str] = None,
        description: t.Optional[str] = None,
    ) -> type[ts.TypedDict]:
        """Register a `TypedDict` class"""

    @t.overload
    def register(
        self,
        __obj: t.Optional[type[ts.NamedTuple]] = None,
        *,
        name: t.Optional[str] = None,
        description: t.Optional[str] = None,
    ) -> type[ts.NamedTuple]:
        """Register a `NamedTuple` class"""

    @t.overload
    def register(
        self,
        __obj: t.Optional[type[ts.PydanticModel]] = None,
        *,
        name: t.Optional[str] = None,
        description: t.Optional[str] = None,
    ) -> type[ts.PydanticModel]:
        """Register a `Pydantic` model"""

    @t.overload
    def register(
        self,
        __obj: t.Optional[ts.AsyncFunction] = None,
        *,
        name: t.Optional[str] = None,
        description: t.Optional[str] = None,
    ) -> ts.AsyncFunction:
        """Register an async function."""

    @t.overload
    def register(
        self,
        __obj: t.Optional[ts.Function] = None,
        *,
        name: t.Optional[str] = None,
        description: t.Optional[str] = None,
    ) -> ts.Function:
        """Register a function."""

    def register(
        self,
        __obj: t.Optional[t.Any] = None,
        *,
        name: t.Optional[str] = None,
        description: t.Optional[str] = None,
    ):
        def decorator(obj: t.Any):
            self.__register(obj=obj, name=name, description=description)
            return obj

        return decorator if __obj is None else decorator(__obj)

    def register_multiple(
        self,
        *__objs: type[ts.TypedDict | ts.NamedTuple | ts.PydanticModel]
        | ts.AsyncFunction
        | ts.Function,
    ):
        """
        Register multiple objects at once. Overriding name and description is not available when using this method.

        :param __objs: Objects to register.

        Example:
        >>> from typing import TypedDict
        >>> def reverse_string(string: str):
        ...     '''Reverse the given string'''
        ...     return string[::-1]
        >>>
        >>> class User(TypedDict):
        ...     '''User Information'''
        ...     name: str
        ...     role: Literal['admin', 'developer', 'tester']
        >>>
        >>> tool_registry.register_multiple(reverse_string, User)
        """
        for obj in __objs:
            self.__register(obj)

    def marshal(
        self,
        __spec: t.Literal["base", "claude"] = "base",
        *,
        as_json: bool = False,
        persist_at: t.Optional[str | Path] = None,
    ) -> t.Optional[list[ts.ToolSchema] | str]:
        """
        Transform registered tools to schema format.

        :param __spec: Schema spec to use. `base` works with most of the LLM.
        :param as_json: If `True`, schema is returned as JSON object.
        :param persist_at: Path to `.json` file to persist schema.
        """
        if not self.__entries:
            return None

        schema = []
        for entry in self.__entries.values():
            schema.append(
                marshal.marshal_object(
                    entry["obj"],
                    spec=__spec,
                    name=entry["name"],
                    description=entry["description"],
                    frame=sys._getframe(1),
                )
            )

        if persist_at is not None:
            Path(persist_at).write_text(json.dumps(schema, ensure_ascii=False, indent=4))

        return json.dumps(schema, ensure_ascii=False) if as_json else schema

    @t.overload
    def compile(self, __expression: str) -> t.Any:
        """
        Compile a tool from call expression

        :param __expression: For example - `'function("arg1", key="value")'`
        """

    @t.overload
    def compile(self, *, name: str, arguments: str | dict[str, t.Any]) -> t.Any:
        """
        Compile a tool from call metadata

        :param name: Name of the tool
        :param arguments: Raw arguments derived from JSON object or JSON object itself.
        """

    def compile(
        self,
        __expression: t.Optional[str] = None,
        *,
        name: t.Optional[str] = None,
        arguments: t.Optional[str | dict[str, t.Any]] = None,
    ):
        if __expression:
            name, arguments = compile.parse_expression(__expression)

        if name is None and arguments is None:
            raise ValueError("Either tool expression or name & arguments required.")

        if (entry := self.__entries.get(name)) is None:
            raise exceptions.RegistryException(name=name, registered=False)

        return compile.compile_object(
            entry["obj"], arguments=arguments or {}, frame=sys._getframe(1)
        )
