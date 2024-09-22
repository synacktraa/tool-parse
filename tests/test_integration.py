import sys

import pytest

if sys.version_info >= (3, 9):
    import asyncio
    from typing import Literal, NamedTuple

    from langchain_core.tools.structured import StructuredTool

    from tool_parse.integrations.langchain import ExtendedStructuredTool

    @pytest.fixture
    def langchain_tools():
        async def search_web(query: str, safe_search: bool = True):
            """
            Search the web.
            :param query: Query to search for.
            :param safe_search: If True, enable safe search.
            """
            return "not found"

        class UserInfo(NamedTuple):
            """User information"""

            name: str
            age: int
            role: Literal["admin", "tester"] = "tester"

        return [
            StructuredTool.from_function(func=search_web),
            ExtendedStructuredTool(func=UserInfo, name="user_info", schema_spec="claude"),
        ]

    def test_langchain_integration(langchain_tools):
        async def __asyncio__():
            assert len(langchain_tools) == 2

            assert langchain_tools[0].name == "search_web"
            assert (await langchain_tools[0].invoke(input={"query": "langchain"})) == "not found"

            assert langchain_tools[1].name == "user_info"
            assert "input_schema" in langchain_tools[1].json_schema["function"]
            info = langchain_tools[1].invoke(input={"name": "synacktra", "age": "21"})
            assert info.name == "synacktra"
            assert info.age == 21
            assert info.role == "tester"

        asyncio.run(__asyncio__())
