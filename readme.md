<div align="center">
  <img src="./assets/main.gif" alt="hypertion">
</div>

---

<p align="center">Making LLM Function-Calling Simpler.</p>


## 🚀 Installation

```sh
pip install hypertion
```

---

## Usage 🤗

#### Create a `HyperFunction` instance

```py
from hypertion import HyperFunction

hyperfunction = HyperFunction()
```

#### Use the `takeover` method to register the function

> Check [notebooks](./notebooks) directory for complex function usage.

```py
from typing import Literal
from typing_extensions import TypedDict

class Settings(TypedDict):
    """
    Settings
    @param unit: The unit scale to represent temperature.
    @param forecast: If set to True, returns the forecasting.
    """
    unit: Literal['celsius', 'fahrenheit']
    forecast: bool = False

@hyperfunction.takeover
def get_current_weather(location: str, *, settings: Settings):
    """
    Get the current weather.
    @param location: Location to search for.
    @param settings: Settings to use for getting current weather.
    """
    info = {
        "location": location,
        "temperature": "72",
        "unit": settings['unit'],
    }
    if settings['forecast'] is True:
        return info | {"forecast": ["sunny", "windy"]}
    
    return info
```

Supported Types: `str` | `int` | `float` | `bool` | `list` | `dict` | `pathlib.Path` | `typing.List` | `typing.Dict` | `typing.NamedTuple` | `typing_extensions.TypedDict` | `pydantic.BaseModel` | `typing.Literal` | `enum.Enum`

#### List registered functions

```python
hyperfunction.registry()
```
```
============================================================
get_current_weather(
   location: str,
   *,
   settings: Settings
):
"""Get the current weather."""
============================================================
```

#### Register a predefined function

```python
from some_module import some_function

hyperfunction.takeover(
    some_function,
    docstring="<Override docstring for the function>"
)
```

### Use the `format` method to get function schema

> LLM specific formats are available: `functionary`, `gorilla`, `mistral`, `gpt`, `claude`

```python
hyperfunction.format(as_json=True)
# hyperfunction.format('<format>', as_json=True)
```
```json
[
    {
        "name": "get_current_weather",
        "description": "Get the current weather.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Location to search for."
                },
                "settings": {
                    "type": "object",
                    "properties": {
                        "unit": {
                            "type": "string",
                            "enum": [
                                "celsius",
                                "fahrenheit"
                            ],
                            "description": "The unit scale to represent temperature."
                        },
                        "forecast": {
                            "type": "boolean",
                            "description": "If set to True, returns the forecasting."
                        }
                    },
                    "required": [
                        "unit"
                    ],
                    "description": "Settings to use for getting current weather."
                }
            },
            "required": [
                "location",
                "settings"
            ]
        }
    }
]
```
---

### Compose function `signature` as function-call object

> Try [Gorilla+Hypertion Colab](https://colab.research.google.com/drive/1DKkXHdebEgj7AfXqw6Ro17KQ1RUBMgco?usp=sharing) for live example.

```python
signature =  """
get_current_weather(
    location='Kolkata', settings={'unit': 'fahrenheit'}
)
"""
function_call = hyperfunction.compose(signature)
function_call
```
```
get_current_weather(
   location='Kolkata',
   settings={'unit': 'fahrenheit', 'forecast': False}
)
```

Invoke the `function-call` object

```python
function_call()
```
```
{'location': 'Kolkata', 'temperature': '72', 'unit': 'fahrenheit'}
```

### Compose function `metadata` as function-call object

> Try [Mistral+Hypertion Colab](https://colab.research.google.com/drive/1y0hf-8leMnk0fnTPY9FWnCgu3ePJqx0G?usp=sharing) for live example.

> Try [Functionary+Hypertion Colab](https://colab.research.google.com/drive/1azzJiAcYRFItlzwEfRPk6UzDUPVAZkUl?usp=sharing) for live example.

```python
name = 'get_current_weather'
arguments = '{"location": "Kolkata", "settings": {"unit": "fahrenheit", "forecast": true}}'
function_call = hyperfunction.compose(name=name, arguments=arguments) # Accepts both JsON and dictionary object
function_call
```
```
get_current_weather(
   location='Kolkata',
   settings={'unit': 'fahrenheit', 'forecast': True}
)
```

Invoke the `function-call` object

```python
function_call()
```
```
{'location': 'Kolkata', 'temperature': '72', 'unit': 'fahrenheit', 'forecast': ['sunny', 'windy']}
```

> Important: The `hypertion` library lacks the capability to interact directly with LLM-specific APIs, meaning it cannot directly make request to any LLM. Its functionality is to generate schema and invoke signature/metadata generated from LLM(s). This design choice was made to provide more flexibility to developers, allowing them to integrate or adapt different tools and libraries as per their project needs.


#### Combining two `HyperFunction` instance

> Note: A single `HyperFunction` instance can hold multiple functions. Creating a new `HyperFunction` instance is beneficial only if you need a distinct set of functions. This approach is especially effective when deploying Agent(s) to utilize functions designed for particular tasks.

```py
new_hyperfunction = HyperFunction()

@new_hyperfunction.takeover
def new_function(
    param1: str,
    param2: int = 100
):
    """Description for the new function"""
    ...

combined_hyperfunction = hyperfunction + new_hyperfunction
combined_hyperfunction.registry()
```
```
============================================================
get_current_weather(
   location: str,
   *,
   settings: Settings
):
"""Get the current weather."""
============================================================
new_function(
   param1: str,
   param2: int = 100
):
"""Description for the new function"""
============================================================
```

### Conclusion

The key strength of this approach lies in its ability to automate schema creation, sparing developers the time and complexity of manual setup. By utilizing the `takeover` method, the system efficiently manages multiple functions within a `HyperFunction` instance, a boon for deploying Agents in LLM applications. This automation not only streamlines the development process but also ensures precision and adaptability in handling task-specific functions, making it a highly effective solution for agent-driven scenarios.