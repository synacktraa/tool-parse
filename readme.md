<div align="center">
  <img src="./assets/main.gif" alt="hypertion">
</div>

---

<p align="center">Effortless function schema creation and efficient invocation based on given function's signature or metadata.</p>


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

#### Use the `takeover` decorator to register a function and utilize the `criteria` static method to define the conditions for parameter evaluation when invoking the function.


```py
import json

from enum import Enum
from pydantic import BaseModel, Field

class Unit(str, Enum):
    celsius = "celsius"
    fahrenheit = "fahrenheit"

class Settings(BaseModel):
    unit: Unit = Field(description="The unit scale to represent temperature")
    forecast: bool = Field(
        default=False, description="If set to True, returns the forecasting."
    )

@hyperfunction.takeover(
    description="Get the current weather for a given location"
)
def get_current_weather(
    location: str = HyperFunction.criteria(
        description="The city and state, e.g. San Francisco, CA"),
    settings: Settings = HyperFunction.criteria(
        description="Settings to use for getting current weather."
    )
):
    info = {
        "location": location,
        "temperature": "72",
        "unit": settings.unit.value,
    }
    if settings.forecast is True:
        info = info | {"forecast": ["sunny", "windy"]}
    
    return info
```

---

<details>

<summary>
OpenFunctions Schema Representation

```py
print(json.dumps(hyperfunction.as_open_functions, indent=4))
```
</summary>

```json
[
    {
        "api_call": "get_current_weather",
        "name": "get_current_weather",
        "description": "Get the current weather for a given location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA"
                },
                "settings": {
                    "type": "object",
                    "description": "Settings to use for getting current weather.",
                    "properties": {
                        "unit": {
                            "type": "string",
                            "description": "The unit scale to represent temperature",
                            "enum": [
                                "celsius",
                                "fahrenheit"
                            ]
                        },
                        "forecast": {
                            "type": "boolean",
                            "description": "If set to True, returns the forecasting."
                        }
                    },
                    "required": [
                        "unit"
                    ]
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
</details>

---

<details>

<summary>
OpenAIFunctions Schema Representation

```py
print(json.dumps(hyperfunction.as_openai_functions, indent=4))
```
</summary>

```json
[
    {
        "api_call": "get_current_weather",
        "name": "get_current_weather",
        "description": "Get the current weather for a given location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA"
                },
                "settings": {
                    "type": "object",
                    "description": "Settings to use for getting current weather.",
                    "properties": {
                        "unit": {
                            "type": "string",
                            "description": "The unit scale to represent temperature",
                            "enum": [
                                "celsius",
                                "fahrenheit"
                            ]
                        },
                        "forecast": {
                            "type": "boolean",
                            "description": "If set to True, returns the forecasting."
                        }
                    },
                    "required": [
                        "unit"
                    ]
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

</details>

---

#### OpenFunctions `Signature` invocation

```py
import openai
from hypertion.types import Signature

def get_openfunctions_response(prompt: str, functions: list[dict]):
    openai.api_key = "EMPTY"
    openai.api_base = "http://luigi.millennium.berkeley.edu:8000/v1"
    """This API endpoint is only for testing purpose. Do not use it for production use."""
    try:
        completion = openai.ChatCompletion.create(
            model="gorilla-openfunctions-v0",
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
            functions=functions,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(e)

signature = Signature(get_openfunctions_response(
    prompt="What is the current weather in Kolkata in fahrenheit scale with forecasting?", 
    functions=hyperfunction.as_open_functions
))

output = hyperfunction.invoke(signature)
print(output)
```
```
{'location': 'Kolkata', 'temperature': '72', 'unit': 'fahrenheit', 'forecast': ['sunny', 'windy']}
```

#### OpenAIFunctions `Metadata` invocation

```py
import json

import openai
from hypertion.types import Metadata

def get_openaifunctions_response(prompt: str, functions: list[dict]):
    openai.api_key = "<OPENAI-API-KEY>"
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4",
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
            functions=functions,
        )
        function_ = completion.choices[0].message.function_call
        return function_.name, json.loads(function_.arguments)

    except Exception as e:
        print(e)

name, arguments = get_openaifunctions_response(
    prompt="What is the current weather in Kolkata in fahrenheit scale with forecasting?", 
    functions=hyperfunction.as_openai_functions
)

output = hyperfunction.invoke(Metadata(name=name, arguments=arguments))
print(output)
```
```
{'location': 'Kolkata', 'temperature': '72', 'unit': 'fahrenheit', 'forecast': ['sunny', 'windy']}
```

> Important: The `hypertion` library lacks the capability to interact directly with LLM-specific APIs, meaning it cannot directly request gorilla-generated Signatures or GPT-generated Metadata from the LLM. This design choice was made to provide more flexibility to developers, allowing them to integrate or adapt different tools and libraries as per their project needs.


#### Attach new `HyperFunction` instance

> Note: A single `HyperFunction` instance can hold multiple functions. Creating a new `HyperFunction` instance is beneficial only if you need a distinct set of functions. This approach is especially effective when deploying Agent(s) to utilize functions designed for particular tasks.

```py
new_hyperfunction = HyperFunction()

@new_hyperfunction.takeover(
    description="<Function's Description>"
)
def new_function(
    param1: str = HyperFunction.criteria(
        description="<Description of the parameter>"),
    param2: int = HyperFunction.criteria(
        100, description="<Description of the parameter>")
):
    ...

```
<details>    
<summary>
Merged Schema

```py
import json

hyperfunction.attach_hyperfunction(new_hyperfunction)
print(json.dumps(hyperfunction.as_open_functions, indent=4))
```
</summary>

```json
[
    {
        "api_call": "get_current_weather",
        "name": "get_current_weather",
        "description": "Get the current weather for a given location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA"
                },
                "settings": {
                    "type": "object",
                    "description": "Settings to use for getting current weather.",
                    "properties": {
                        "unit": {
                            "type": "string",
                            "description": "The unit scale to represent temperature",
                            "enum": [
                                "celsius",
                                "fahrenheit"
                            ]
                        },
                        "forecast": {
                            "type": "boolean",
                            "description": "If set to True, returns the forecasting."
                        }
                    },
                    "required": [
                        "unit"
                    ]
                }
            },
            "required": [
                "location",
                "settings"
            ]
        }
    },
    {
        "api_call": "new_function",
        "name": "new_function",
        "description": "<Function's Description>",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "<Description of the parameter>"
                },
                "param2": {
                    "type": "integer",
                    "description": "<Description of the parameter>"
                }
            },
            "required": [
                "param1"
            ]
        }
    }
]
```
</details>

### Conclusion

The key strength of this approach lies in its ability to automate schema creation, sparing developers the time and complexity of manual setup. By utilizing the `takeover` decorator and `criteria` method, the system efficiently manages multiple functions within a `HyperFunction` instance, a boon for deploying Agents in LLM applications. This automation not only streamlines the development process but also ensures precision and adaptability in handling task-specific functions, making it a highly effective solution for agent-driven scenarios.