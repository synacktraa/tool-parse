"""
Extended tool support for langchain-based integration.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import typing as t
import uuid
from contextvars import copy_context
from types import MethodType

from langchain_core.callbacks import (
    AsyncCallbackManager,
    AsyncCallbackManagerForToolRun,
    CallbackManager,
    CallbackManagerForToolRun,
    Callbacks,
)
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, ToolCall
from langchain_core.runnables import Runnable
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

from .. import _types as ts
from ..compile import compile_object
from ..marshal import marshal_object


class ExtendedStructuredTool(BaseTool):
    name: t.Optional[str] = None
    """The unique name of the tool that clearly communicates its purpose."""
    description: t.Optional[str] = None
    """Used to tell the model how/when/why to use the tool."""
    func: type[ts.TypedDict | ts.NamedTuple | ts.PydanticModel] | ts.AsyncFunction | ts.Function
    """
    The object to run when the tool is called.
    `func` is used as attribute name because it used widely in other components in langchain.
    """
    schema_spec: t.Literal["base", "claude"] = "base"
    """Schema spec to use. `base` works with most of the LLM."""
    _schema: dict = PrivateAttr

    @model_validator(mode="after")
    def validate_name_and_description(self):
        tool_schema = marshal_object(
            self.func,
            spec=self.schema_spec,
            name=self.name,
            description=self.description,
            frame=sys._getframe(1),
        )
        if not self.name:
            self.name = tool_schema["function"]["name"]

        if not self.description:
            if (fn_desc := tool_schema["function"].get("description")) is None:
                raise ValueError("Function must have a docstring if description not provided.")
            self.description = fn_desc

        self._schema = tool_schema
        return self

    @classmethod
    def from_objects(
        cls,
        *__objs: type[ts.TypedDict | ts.NamedTuple | ts.PydanticModel]
        | ts.AsyncFunction
        | ts.Function,
        schema_spec: t.Literal["base", "claude"] = "base",
        **kwargs: t.Any,
    ):
        """
        Create multiple tool at once.

        :param __objs: The objects to add as tools.
        :param schema_spec: Schema spec to use. `base` works with most of the LLM.
        :returns: list of tools.
        """
        return [cls(func=obj, schema_spec=schema_spec, **kwargs) for obj in __objs]

    # --- Runnable ---

    async def ainvoke(
        self,
        input: t.Union[str, dict, ToolCall],  # noqa: A002
        config: t.Optional[RunnableConfig] = None,
        **kwargs: t.Any,
    ) -> t.Any:
        if not inspect.iscoroutinefunction(self.func):
            # If the tool does not implement async, fall back to default implementation
            return await run_in_executor(config, self.invoke, input, config, **kwargs)

        return await super().ainvoke(input, config, **kwargs)

    # --- Tool ---

    @property
    def json_schema(self) -> ts.ToolSchema:
        return getattr(self, "_schema", None)  # type: ignore[return-value]

    @property
    def args(self) -> t.Dict[str, t.Any]:
        """The tool's input arguments."""
        p_key = "parameters" if self.schema_spec == "base" else "input_schema"
        return self.json_schema["function"][p_key]["properties"]  # type: ignore[literal-required]

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

        return compile_object(self.func, arguments=kwargs, frame=sys._getframe(1))

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

            return compile_object(self.func, arguments=kwargs, frame=sys._getframe(1))

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
                response = await asyncio.create_task(coro, context=context)  # type: ignore[call-arg]
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


ChatModel = t.TypeVar("ChatModel", bound=BaseChatModel)


@t.overload
def patch_chat_model(__model: ChatModel) -> ChatModel:
    """
    Patch a chat model instance to add support for `ExtendedStructuredTool`

    :Example:
    ```
    from langchain_ollama.chat_models import ChatOllama
    model = patch_chat_model(ChatOllama(model="<model-name>"))
    ```

    :param __model: Chat model instance to patch
    :returns: Patched model instance
    """


@t.overload
def patch_chat_model(__model: type[ChatModel]) -> type[ChatModel]:
    """
    Patch a chat model class to add support for `ExtendedStructuredTool`

    :Example:
    ```
    from langchain_ollama.chat_models import ChatOllama
    model = patch_chat_model(ChatOllama)(model="<model-name>")
    ```

    :param __model: Chat model class to patch
    :returns: Patched model class
    """


def patch_chat_model(__model: ChatModel | type[ChatModel]):
    class PatchedModel(BaseChatModel):
        def bind_tools(
            self,
            tools: t.Sequence[t.Any],
            **kwargs: t.Any,
        ) -> Runnable[LanguageModelInput, BaseMessage]:
            schema_list = []
            for tool in tools:
                if isinstance(tool, ExtendedStructuredTool):
                    schema_list.append(tool.json_schema)
                else:
                    schema_list.extend(super().bind_tools(tools=[tool], **kwargs))
            return self.bind(tools=schema_list, **kwargs)

    if isinstance(__model, type):
        # Patch the class
        __model.bind_tools = PatchedModel.bind_tools
    else:
        # Patch the instance (pydantic is weird)
        object.__setattr__(__model, "bind_tools", MethodType(PatchedModel.bind_tools, __model))

    return __model
