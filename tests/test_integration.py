import sys

import pytest

if sys.version_info >= (3, 9):
    import asyncio
    from typing import Any, Literal, NamedTuple

    from langchain_core.language_models.fake_chat_models import FakeChatModel
    from langchain_core.tools.structured import StructuredTool
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from tool_parse.integrations.langchain import ExtendedStructuredTool, patch_chat_model

    @pytest.fixture
    def tools():
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

    def test_langchain_tools(tools):
        async def __asyncio__():
            assert len(tools) == 2

            assert tools[0].name == "search_web"
            assert (await tools[0].invoke(input={"query": "langchain"})) == "not found"

            assert tools[1].name == "user_info"
            assert "input_schema" in tools[1].json_schema["function"]
            info = tools[1].invoke(input={"name": "synacktra", "age": "21"})
            assert info.name == "synacktra"
            assert info.age == 21
            assert info.role == "tester"

        asyncio.run(__asyncio__())

    def test_langchain_chat_model(tools):
        class ChatMock(FakeChatModel):
            def bind_tools(self, tools: Any, **kwargs: Any):
                formatted_tools = [convert_to_openai_tool(tool) for tool in tools]
                return super().bind(tools=formatted_tools, **kwargs)

        patched_model = patch_chat_model(ChatMock()).bind_tools(tools=tools)
        print(patched_model.kwargs["tools"])
        assert len(patched_model.kwargs["tools"]) == 2

        patched_model = patch_chat_model(ChatMock)().bind_tools(tools=tools)
        assert len(patched_model.kwargs["tools"]) == 2
