<p align="center">Making LLM Tool-Calling Simpler.</p>


## 🚀 Installation

```sh
pip install tool-parse
```

---

## Usage 🤗

### Create a new registry

```py
from tool_parse import ToolRegistry

tr = ToolRegistry()
```

### Defining tools and registering them

`tool-parse` supports functions(both synchronous/asynchronous), `pydantic.BaseModel`, `typing.TypedDict` and `typing.NamedTuple` (I might add dataclass support in future). 

> Note: pydantic module is not pre-installed with tool-parse, you will have to install it explicitly using `pip install pydantic`

There are multiple ways of registering tools:

> Adding a docstring is optional, but it's a good practice to include description for parameters. I personally like sphinx format, but you can use any format supported by `docstring_parser` library.

- Decorating the object:

  ```python
  @tr.register
  class Td(TypedDict):
    """
    A useless typeddict
    :param var: A useless parameter
    """
    var: int
  ```

  Overriding tool name and description
  ```python
  @tr.register(name="search_tool", description="Searches for web")
  def fn(var: int):
    """
    A useless function
    :param var: A useless parameter
    """
    ...
  ```

- Passing the object directly

  ```python
  class Nt(NamedTuple):
    """
    A useless namedtuple
    :param var: A useless parameter
    """
    var: int

  tr.register(Nt)
  ```

  Overriding tool name and description
  ```python
  async def fn(var: int):
    """
    A useless function
    :param var: A useless parameter
    """
    ...

  tr.register(fn, name="search_tool", description="Searches for web")
  ```

- Using key-value pair

  > This method doesn't allow overriding description

  ```python
  class Model(BaseModel):
    """
    A useless pydantic model
    :param var: A useless parameter
    """
    var: int

  tr['p_model'] = Model
  ```

Supported parameter types: `str` | `int` | `float` | `bool` | `set` | `list` | `dict` | `pathlib.Path` | `typing.Set` | `typing.List` | `typing.Dict` | `typing.NamedTuple` | `typing.TypedDict` | `pydantic.BaseModel` | `typing.Literal` | `enum.Enum`

### Check if a name has already been registered

```python
'tool_name' in tr
```

### Get registered tools as schema

> `base` and `claude` formats are available, default - `base` format works with almost all the providers.

- as dictionary object
  ```python
  tools = tr.marshal('base') # list[dict]
  ```

- as JsON object
  ```python
  tools = tr.marshal(as_json=True) # str
  ```

- saving JsON object to a file
  ```python
  tools = tr.marshal('claude', persist_at='/path/to/file.json') # str
  ```

- get single tool schema
  ```python
  tool = tr['tool_name'] # dict
  ```

---

### Invoking a tool


- From call expression

  ```python
  output = tr.compile('function("arg1", key="value")')
  ```

- From call metadata

  ```python
  output = tr.compile(name='function', arguments={'key': 'value'})
  ```

> Important: The `tool-parse` library lacks the capability to interact directly with LLM-specific APIs, meaning it cannot directly make request to any LLM. Its functionality is to generate schema and invoke expression/metadata generated from LLM(s). This design choice was made to provide more flexibility to developers, allowing them to integrate or adapt different tools and libraries as per their project needs.

### Combining two registries

> Note: A single `ToolRegistry` instance can hold as many tools you want. Creating a new `ToolRegistry` instance is beneficial only if you need a distinct set of tools. This approach is especially effective when deploying Agent(s) to utilize tools designed for particular tasks.

```py
new_registry = ToolRegistry()

@new_registry.register
def new_function(
    param1: str,
    param2: int = 100
):
    """Description for the new function"""
    ...

combined_registry = tr + new_registry
```