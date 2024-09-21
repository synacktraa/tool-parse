"""
Extended tool support for langchain-based integration.

To run this file, run the following command: `pip install -U tool-parse langchain-core langchain-ollama duckduckgo-search`
"""

from __future__ import annotations

import asyncio
import inspect
import typing as t
import uuid
from contextvars import copy_context

from langchain_core.callbacks import (
    AsyncCallbackManager,
    AsyncCallbackManagerForToolRun,
    CallbackManager,
    CallbackManagerForToolRun,
)
from langchain_core.callbacks.manager import Callbacks
from langchain_core.runnables.config import (
    RunnableConfig,
    _set_config_context,
    patch_config,
    run_in_executor,
)
from langchain_core.runnables.utils import asyncio_accepts_context
from langchain_core.tools.base import (
    BaseTool,
    ToolException,
    _format_output,
    _get_runnable_config_param,
    _handle_tool_error,
    _handle_validation_error,
)
from pydantic import PrivateAttr, ValidationError, model_validator

from tool_parse import _types as tp_types
from tool_parse.compile import compile_object
from tool_parse.marshal import marshal_object


class ExtendedStructuredTool(BaseTool):
    name: str | None = None
    """The unique name of the tool that clearly communicates its purpose."""
    description: str | None = None
    """Used to tell the model how/when/why to use the tool."""
    func: t.Any
    """The object to run when the tool is called.
    `func` is used as attribute name because it used widely in other components in langchain."""
    _schema: dict = PrivateAttr

    @model_validator(mode="after")
    def validate_name_and_description(self):
        tool_schema = marshal_object(
            self.func, spec="base", name=self.name, description=self.description
        )
        if self.name is None:
            self.name = tool_schema["function"]["name"]

        if self.description is None:
            if (fn_desc := tool_schema["function"].get("description")) is None:
                raise ValueError("Function must have a docstring if description not provided.")
            self.description = fn_desc

        self._schema = tool_schema
        return self

    @classmethod
    def from_objects(cls, *__objs: t.Any, verbose: bool = False):
        return [cls(func=obj, verbose=verbose) for obj in __objs]

    # --- Runnable ---

    async def ainvoke(
        self,
        input: t.Union[str, t.Dict],  # noqa: A002
        config: t.Optional[RunnableConfig] = None,
        **kwargs: t.Any,
    ) -> t.Any:
        if not inspect.iscoroutinefunction(self.func):
            # If the tool does not implement async, fall back to default implementation
            return await run_in_executor(config, self.invoke, input, config, **kwargs)

        return await super().ainvoke(input, config, **kwargs)

    # --- Tool ---

    @property
    def schema(self) -> tp_types.ToolSchema:
        return getattr(self, "_schema", None)

    @property
    def args(self) -> t.Dict[str, t.Any]:
        """The tool's input arguments."""
        return self.schema["function"]["parameters"]["properties"]

    def _run(
        self,
        *args: t.Any,
        config: t.Optional[RunnableConfig] = None,
        run_manager: t.Optional[CallbackManagerForToolRun] = None,
        **kwargs: t.Any,
    ) -> t.Any:
        """Use the tool."""
        if run_manager and self.args.get("callbacks"):
            kwargs["callbacks"] = run_manager.get_child()
        if config_param := _get_runnable_config_param(self.func):
            kwargs[config_param] = config

        return compile_object(self.func, arguments=kwargs)

    async def _arun(
        self,
        *args: t.Any,
        config: t.Optional[RunnableConfig] = None,
        run_manager: t.Optional[AsyncCallbackManagerForToolRun] = None,
        **kwargs: t.Any,
    ) -> t.Any:
        """Use the tool asynchronously."""
        if inspect.iscoroutinefunction(self.func):
            if run_manager and self.args.get("callbacks"):
                kwargs["callbacks"] = run_manager.get_child()
            if config_param := _get_runnable_config_param(self.func):
                kwargs[config_param] = config

            # Need to update tool-parse library so user can use await
            return compile_object(self.func, arguments=kwargs)

        return await run_in_executor(
            None,
            self._run,
            *args,
            run_manager=run_manager.get_sync() if run_manager else None,
            **kwargs,
        )

    def run(  # noqa: C901
        self,
        tool_input: t.Union[str, t.Dict[str, t.Any]],
        verbose: t.Optional[bool] = None,
        start_color: t.Optional[str] = "green",
        color: t.Optional[str] = "green",
        callbacks: Callbacks = None,
        *,
        tags: t.Optional[t.List[str]] = None,
        metadata: t.Optional[t.Dict[str, t.Any]] = None,
        run_name: t.Optional[str] = None,
        run_id: t.Optional[uuid.UUID] = None,
        config: t.Optional[RunnableConfig] = None,
        tool_call_id: t.Optional[str] = None,
        **kwargs: t.Any,
    ) -> t.Any:
        """Run the tool."""
        if isinstance(tool_input, str):
            raise ValueError("Tool parse expects dictionary objects as input.")

        callback_manager = CallbackManager.configure(
            callbacks,
            self.callbacks,
            self.verbose or bool(verbose),
            tags,
            self.tags,
            metadata,
            self.metadata,
        )

        # TODO: maybe also pass through run_manager is _run supports kwargs
        run_manager = callback_manager.on_tool_start(
            {"name": self.name, "description": self.description},
            str(tool_input),
            color=start_color,
            name=run_name,
            run_id=run_id,
            inputs=tool_input,
            **kwargs,
        )
        content = None
        artifact = None
        error_to_raise: t.Union[Exception, KeyboardInterrupt, None] = None
        try:
            child_config = patch_config(
                config,
                callbacks=run_manager.get_child(),
            )
            context = copy_context()
            context.run(_set_config_context, child_config)
            if inspect.signature(self._run).parameters.get("run_manager"):
                tool_input["run_manager"] = run_manager
            response = context.run(self._run, **tool_input)
            if self.response_format == "content_and_artifact":
                if not isinstance(response, tuple) or len(response) != 2:
                    raise ValueError(
                        "Since response_format='content_and_artifact' "
                        "a two-tuple of the message content and raw tool output is "
                        f"expected. Instead generated response of type: "
                        f"{type(response)}."
                    )
                content, artifact = response
            else:
                content = response
            status = "success"
        except ValidationError as e:
            if not self.handle_validation_error:
                error_to_raise = e
            else:
                content = _handle_validation_error(e, flag=self.handle_validation_error)
            status = "error"
        except ToolException as e:
            if not self.handle_tool_error:
                error_to_raise = e
            else:
                content = _handle_tool_error(e, flag=self.handle_tool_error)
            status = "error"
        except (Exception, KeyboardInterrupt) as e:
            error_to_raise = e
            status = "error"

        if error_to_raise:
            run_manager.on_tool_error(error_to_raise)
            raise error_to_raise
        output = _format_output(content, artifact, tool_call_id, self.name, status)
        run_manager.on_tool_end(output, color=color, name=self.name, **kwargs)
        return output

    async def arun(  # noqa: C901
        self,
        tool_input: t.Union[str, t.Dict],
        verbose: t.Optional[bool] = None,
        start_color: t.Optional[str] = "green",
        color: t.Optional[str] = "green",
        callbacks: Callbacks = None,
        *,
        tags: t.Optional[t.List[str]] = None,
        metadata: t.Optional[t.Dict[str, t.Any]] = None,
        run_name: t.Optional[str] = None,
        run_id: t.Optional[uuid.UUID] = None,
        config: t.Optional[RunnableConfig] = None,
        tool_call_id: t.Optional[str] = None,
        **kwargs: t.Any,
    ) -> t.Any:
        """Run the tool asynchronously."""
        if isinstance(tool_input, str):
            raise ValueError("Tool parse expects dictionary objects as input.")

        callback_manager = AsyncCallbackManager.configure(
            callbacks,
            self.callbacks,
            self.verbose or bool(verbose),
            tags,
            self.tags,
            metadata,
            self.metadata,
        )

        run_manager = await callback_manager.on_tool_start(
            {"name": self.name, "description": self.description},
            tool_input if isinstance(tool_input, str) else str(tool_input),
            color=start_color,
            name=run_name,
            inputs=tool_input,
            run_id=run_id,
            **kwargs,
        )
        try:
            child_config = patch_config(config, callbacks=run_manager.get_child())
            context = copy_context()
            context.run(_set_config_context, child_config)
            func_to_check = self._run if self.__class__._arun is BaseTool._arun else self._arun
            if inspect.signature(func_to_check).parameters.get("run_manager"):
                tool_input["run_manager"] = run_manager
            if config_param := _get_runnable_config_param(func_to_check):
                tool_input[config_param] = config
            coro = context.run(self._arun, **tool_input)
            if asyncio_accepts_context():
                response = await asyncio.create_task(coro, context=context)
            else:
                response = await coro
            if self.response_format == "content_and_artifact":
                if not isinstance(response, tuple) or len(response) != 2:
                    raise ValueError(
                        "Since response_format='content_and_artifact' "
                        "a two-tuple of the message content and raw tool output is "
                        f"expected. Instead generated response of type: "
                        f"{type(response)}."
                    )
                content, artifact = response
            else:
                content = response
            status = "success"
        except ValidationError as e:
            if not self.handle_validation_error:
                error_to_raise = e
            else:
                content = _handle_validation_error(e, flag=self.handle_validation_error)
            status = "error"
        except ToolException as e:
            if not self.handle_tool_error:
                error_to_raise = e
            else:
                content = _handle_tool_error(e, flag=self.handle_tool_error)
            status = "error"
        except (Exception, KeyboardInterrupt) as e:
            error_to_raise = e
            status = "error"

        if error_to_raise:
            await run_manager.on_tool_error(error_to_raise)
            raise error_to_raise

        output = _format_output(content, artifact, tool_call_id, self.name, status)
        await run_manager.on_tool_end(output, color=color, name=self.name, **kwargs)
        return output


if __name__ == "__main__":
    from duckduckgo_search import DDGS
    from langchain_core.messages import HumanMessage
    from langchain_ollama.chat_models import ChatOllama

    async def search_text(
        text: str,
        *,
        safe_search: bool = True,
        backend: t.Literal["api", "html", "lite"] = "api",
        max_results: int = 1,
    ):
        """
        Search for text in the web.
        :param text: Text to search for.
        :param safe_search: If True, enable safe search.
        :param backend: Backend to use for retrieving results.
        :param max_results: Max results to return.
        """
        return DDGS().text(
            keywords=text,
            safesearch="on" if safe_search else "off",
            backend=backend,
            max_results=max_results,
        )

    class ProductInfo(t.NamedTuple):  # Can be t.TypedDict or pydantic.BaseModel
        """
        Information about the product.
        :param name: Name of the product.
        :param price: Price of the product.
        :param in_stock: If the product is in stock.
        """

        name: str
        price: float
        in_stock: bool = False

    search_tool = ExtendedStructuredTool(func=search_text, description="Search the web.")
    parse_product_tool = ExtendedStructuredTool(func=ProductInfo, name="product_info")
    tools = [search_tool, parse_product_tool]

    # OR tools = ExtendedStructuredTool.from_objects(search_text, ProductInfo)

    model = ChatOllama(model="llama3-groq-tool-use").bind(tools=[tool.schema for tool in tools])

    def call_model(__query: str):
        ai_message = model.invoke(input=[HumanMessage(content=__query)])
        if ai_message.tool_calls:
            metadata = ai_message.tool_calls[0]
            print(f"name={metadata['name']!r}")
            print(f"arguments={metadata['args']}")
            if metadata["name"] == "search_text":
                print(f"output={search_tool.invoke(input=metadata).content}")
            elif metadata["name"] == "product_info":
                print(f"output={parse_product_tool.invoke(input=metadata).content}")
            else:
                print("Tool not registered.")
        else:
            print(ai_message.content)
        print("---" * 20)

    call_model("Search 5 sources for langgraph docs using lite backend")
    call_model("Parse: Product RTX 4900, priced at $3.5k, is in stock.")
    """
    name='search_text'
    arguments={'backend': 'lite', 'max_results': 5, 'text': 'langgraph docs'}
    output=[{"title": "LangGraph - LangChain", "href": "https://www.langchain.com/langgraph", "body": "\n      While in beta, all LangSmith users on Plus and Enterprise plans can access LangGraph Cloud. Check out the docs. How are LangGraph and LangGraph Cloud different? LangGraph is a stateful, orchestration framework that brings added control to agent workflows. LangGraph Cloud is a service for deploying and scaling LangGraph applications, with a ...\n    "}, {"title": "️LangGraph - GitHub Pages", "href": "https://langchain-ai.github.io/langgraph/", "body": "\n      LangGraph is a framework for creating stateful, multi-actor applications with LLMs, using cycles, controllability, and persistence. Learn how to use LangGraph with examples, features, and integration with LangChain and LangSmith.\n    "}, {"title": "Introduction to LangGraph", "href": "https://academy.langchain.com/courses/intro-to-langgraph", "body": "\n      No. LangGraph is an orchestration framework for complex agentic systems and is more low-level and controllable than LangChain agents. On the other hand, LangChain provides a standard interface to interact with models and other components, useful for straight-forward chains and retrieval flows. How is LangGraph different from other agent frameworks?\n    "}, {"title": "Tutorials - GitHub Pages", "href": "https://langchain-ai.github.io/langgraph/tutorials/", "body": "\n      Learn how to use LangGraph, a framework for building language agents as graphs, through various examples and scenarios. Explore chatbots, code assistants, multi-agent systems, planning agents, reflection agents, and more.\n    "}, {"title": "Graphs - GitHub Pages", "href": "https://langchain-ai.github.io/langgraph/reference/graphs/", "body": "\n      Learn how to create and run graph workflows with LangGraph, a core abstraction of LangChain AI. See examples of StateGraph, ConditionalEdges, EntryPoint, FinishPoint, and Node methods.\n    "}]
    ------------------------------------------------------------
    name='product_info'
    arguments={'in_stock': True, 'name': 'Product RTX 4900', 'price': 3500}
    output=["Product RTX 4900", 3500.0, true] # Don't know why tuple is casted to list :>
    ------------------------------------------------------------
    """
