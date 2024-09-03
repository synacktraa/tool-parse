<p align="center">Making LLM Tool-Calling Simpler.</p>

---

<p align="center">
    <a href="https://badge.fury.io/py/tool-parse">
        <img src="https://badge.fury.io/py/tool-parse.svg" alt="tool-parse version">
    </a>
</p>

## 🚀 Installation

```sh
pip install tool-parse
```

## 🌟 Key Features

1. **Flexible Tool Registration:**
   - Support for functions (synchronous and asynchronous)
   - Compatible with `pydantic.BaseModel`, `typing.TypedDict`, and `typing.NamedTuple`
   - Multiple registration methods: decorators, direct passing, and key-value pairs
   - Supports any docstring format recognized by the `docstring_parser` library

2. **Extensive Parameter Type Support:**
   - Handles a wide range of parameter types:
    `str`, `int`, `float`, `bool`, `set`, `list`, `dict`, `pathlib.Path`,
    `typing.Set`, `typing.List`, `typing.Dict`, `typing.NamedTuple`,
    `typing.TypedDict`, `pydantic.BaseModel`, `typing.Literal`, `enum.Enum`
   - Supports optional parameters:
    `typing.Optional[<type>]`/`t.Union[<type>, None]`/`<type> | None`

4. **Lightweight and Flexible:**
   - Core package is lightweight
   - Optional dependencies (like `pydantic`) can be installed separately as needed

5. **Schema Generation and Tool Invocation:**
   - Generate schemas in 'base' and 'claude' formats
   - Easy tool invocation from call expressions or metadata

## Cookbooks

- [GorillaLLM Integration](https://colab.research.google.com/drive/1C2WCgIZ7LnkpLt3KARL9ROh4iLwaACa6?usp=sharing)


## Usage 🤗

### Creating independent tools

```python
from tool_parse import tool

@tool
def search_web(query: str, max_results: int = 10):
    """
    Search the web for given query
    :param query: The search query string
    :param max_results: Maximum number of results to return
    """
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

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/synacktraa/tool-parse/issues).

---

Made with ❤️ by [synacktra](https://github.com/synacktraa)