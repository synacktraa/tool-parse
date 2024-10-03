<p align="center">Making LLM Tool-Calling Simpler.</p>

---

<p align="center">
    <a href="https://img.shields.io/github/v/release/synacktraa/tool-parse">
        <img src="https://img.shields.io/github/v/release/synacktraa/tool-parse" alt="tool-parse version">
    </a>
    <a href="https://img.shields.io/github/actions/workflow/status/synacktraa/tool-parse/master.yml?branch=master">
        <img src="https://img.shields.io/github/actions/workflow/status/synacktraa/tool-parse/master.yml?branch=master" alt="tool-parse build status">
    </a>
    <a href="https://codecov.io/gh/synacktraa/tool-parse">
        <img src="https://codecov.io/gh/synacktraa/tool-parse/branch/master/graph/badge.svg" alt="tool-parse codecov">
    </a>
    <a href="https://img.shields.io/github/license/synacktraa/tool-parse">
        <img src="https://img.shields.io/github/license/synacktraa/tool-parse" alt="tool-parse license">
    </a>
</p>

## 🚀 Installation

```sh
pip install tool-parse
```

- with `pydantic` support

  ```sh
  pip install "tool-parse[pydantic]"
  ```

- with `langchain` based integration
  ```sh
  pip install "tool-parse[langchain]"
  ```

## 🌟 Key Features

1. **Versatile Tool Management:**

   - Support for functions (both synchronous and asynchronous)
   - Compatible with `pydantic.BaseModel`, `typing.TypedDict`, and `typing.NamedTuple`
   - Supports any docstring format recognized by the `docstring_parser` library
   - `@tool` decorator for creating independent, standalone tools
   - `ToolRegistry` class for managing multiple tools
     - Multiple registration methods:
       - Decorators (`@tr.register`)
       - Direct passing (`tr.register(func)`)
       - Key-value pairs (`tr[key] = func`)
       - Bulk registration (`register_multiple`)
     - Customizable tool naming and description

2. **Extensive Parameter Type Support:**

   - Handles a wide range of parameter types:
     `str`, `int`, `float`, `bool`, `set`, `list`, `dict`, `pathlib.Path`,
     `typing.Set`, `typing.List`, `typing.Dict`, `typing.NamedTuple`,
     `typing.TypedDict`, `pydantic.BaseModel`, `typing.Literal`, `enum.Enum`
   - Supports optional parameters:
     `typing.Optional[<type>]`, `typing.Union[<type>, None]`, `<type> | None`
   - Handles forward references and complex nested types

3. **Robust Schema Generation:**

   - Generates schemas in both 'base' and 'claude' formats
   - Extracts and includes parameter descriptions from docstrings
   - Handles recursive type definitions gracefully

4. **Flexible Tool Invocation:**

   - Supports tool invocation from call expressions or metadata
   - Handles argument parsing and type conversion
   - Manages both positional and keyword arguments

5. **Error Handling and Validation:**
   - Comprehensive error checking for type mismatches, invalid arguments, and unsupported types
   - Validates enum and literal values against allowed options
   - Handles recursive parameter exceptions

## Cookbooks

- [GorillaLLM Integration](./cookbooks/gorillaLLM-integration.ipynb)
- [Langgraph+Ollama Example](./cookbooks//langgraph-ollama-example.ipynb)

## Usage 🤗

### Creating independent tools

```python
from tool_parse import tool
from typing import Optional

@tool
def search_web(query: str, max_results: Optional[int]):
    """
    Search the web for given query
    :param query: The search query string
    :param max_results: Maximum number of results to return
    """
    print(f"{query=}, {max_results=}")
    ...

# Get tool schema
schema = search_web.marshal('base') # `base` and `claude` schema are available

# Invoke tool from LLM generated arguments
output = search_web.compile(arguments={"query": "Transformers"})
```

### Creating a tool registry

```python
from tool_parse import ToolRegistry

tr = ToolRegistry()
```

#### Defining tools and registering them

There are multiple ways of registering tools:

> Adding a docstring is optional, but it's good practice to include descriptions for parameters. The library supports any format recognized by the `docstring_parser` library, with sphinx format being a personal preference.

1. Decorating the object:

```python
from typing import TypedDict

@tr.register
class UserInfo(TypedDict):
    """
    User information schema
    :param name: The user's full name
    :param age: The user's age in years
    """
    name: str
    age: int

# Override name and description
@tr.register(name="search_web", description="Performs a web search")
def search_function(query: str, max_results: int = 10):
    """
    Search the web for given query
    :param query: The search query string
    :param max_results: Maximum number of results to return
    """
    ...
```

2. Passing the object directly:

```python
from typing import NamedTuple

class ProductInfo(NamedTuple):
    """
    Product information
    :param name: The product name
    :param price: The product price
    :param in_stock: Whether the product is in stock
    """
    name: str
    price: float
    in_stock: bool

tr.register(ProductInfo)

async def fetch_data(url: str, timeout: int = 30):
    """
    Fetch data from a given URL
    :param url: The URL to fetch data from
    :param timeout: Timeout in seconds
    """
    ...

tr.register(fetch_data, name="fetch_api_data", description="Fetches data from an API")
```

3. Using key-value pair:

> Note: This method doesn't allow overriding the description.

```python
from pydantic import BaseModel

class OrderModel(BaseModel):
    """
    Order information
    :param order_id: Unique identifier for the order
    :param items: List of items in the order
    :param total: Total cost of the order
    """
    order_id: str
    items: list[str]
    total: float

tr['create_order'] = OrderModel
```

4. Registering multiple tools at once:

> Note: This method doesn't allow overriding the name and description

```python
tr.register_multiple(UserInfo, search_function, ProductInfo)
```

#### Check if a name has already been registered

```python
'search_web' in tr  # Returns True if 'search_web' is registered, False otherwise
```

#### Get registered tools as schema

> `base` and `claude` formats are available. The default `base` format works with almost all providers.

- As a list of dictionaries:

  ```python
  tools = tr.marshal('base')  # list[dict]
  ```

- As a JSON string:

  ```python
  tools = tr.marshal(as_json=True)  # str
  ```

- Saving as a JSON file:

  ```python
  tools = tr.marshal('claude', persist_at='/path/to/tools_schema.json')  # list[dict]
  ```

- Get a single tool schema:
  ```python
  tool = tr['search_web']  # dict
  ```

#### Invoking a tool

- From a call expression:

  ```python
  result = tr.compile('search_web("Python programming", max_results=5)')
  ```

- From call metadata:

  ```python
  result = tr.compile(name='fetch_api_data', arguments={'url': 'https://api.example.com', 'timeout': 60})
  ```

> Important: The `tool-parse` library does not interact directly with LLM-specific APIs. It cannot make requests to any LLM directly. Its primary functions are generating schemas and invoking expressions or metadata generated from LLMs. This design provides developers with more flexibility to integrate or adapt various tools and libraries according to their project needs.

#### Combining two registries

> Note: A single `ToolRegistry` instance can hold as many tools as you need. Creating a new `ToolRegistry` instance is beneficial only when you require a distinct set of tools. This approach is particularly effective when deploying agents to utilize tools designed for specific tasks.

```python
new_registry = ToolRegistry()

@new_registry.register
def calculate_discount(
    original_price: float,
    discount_percentage: float = 10
):
    """
    Calculate the discounted price of an item
    :param original_price: The original price of the item
    :param discount_percentage: The discount percentage to apply
    """
    ...

combined_registry = tr + new_registry
```

## Third Party Integrations

### Langchain

Define the tools

```python
from tool_parse.integrations.langchain import ExtendedStructuredTool

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
    role: Literal['admin', 'tester'] = 'tester'

tools = [
    ExtendedStructuredTool(func=search_web),
    ExtendedStructuredTool(func=UserInfo, name="user_info", schema_spec='claude'),
]
# OR
tools = ExtendedStructuredTool.from_objects(search_web, UserInfo, schema_spec='base')
```

Patch the chat model

```python
from langchain_ollama.chat_models import ChatOllama

from tool_parse.integrations.langchain import patch_chat_model

model = patch_chat_model(ChatOllama(model="llama3-groq-tool-use")) # Patch the instance
# OR
model = patch_chat_model(ChatOllama)(model="llama3-groq-tool-use") # Patch the class and then instantiate it
```

Bind the tools

```python
model.bind_tools(tools=tools)
```

> For langgraph agent usage, refer [Langgraph+Ollama Example](./cookbooks//langgraph-ollama-example.ipynb) cookbook

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/synacktraa/tool-parse/issues).

---

Made with ❤️ by [synacktra](https://github.com/synacktraa)
