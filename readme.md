<div align="center">
  <img src="./assets/main.gif" alt="hypertion">
</div>

---

<p align="center">Effortless schema creation and smooth invocation based on given function's signature or metadata.</p>


## 🚀 Installation

```sh
pip install hypertion
```

---

## Usage 🤗

#### Create schema for function calling

```py
from enum import Enum
from hypertion import HyperFunction

hyperfunction = HyperFunction()

class Unit(str, Enum):
    celsius = "celsius"
    fahrenheit = "fahrenheit"

@hyperfunction.takeover(
    description="Get the current weather in a given location"
)
def get_current_weather(
    location: str = HyperFunction.criteria(
        description="The city and state, e.g. San Francisco, CA"), 
    unit: Unit = HyperFunction.criteria(
        default=Unit.fahrenheit, description="The temperature unit scale"
    )
):
    return {
        "location": location,
        "temperature": "72",
        "unit": unit.value,
        "forecast": ["sunny", "windy"],
    }

functions = hyperfunction.as_open_functions
```

#### Pass the functions to LLM to generate signature or metadata

```py
import openai

def get_function_signature(prompt: str, functions: list[dict]):
    openai.api_key = "EMPTY"
    openai.api_base = "http://luigi.millennium.berkeley.edu:8000/v1"
    try:
        completion = openai.ChatCompletion.create(
            model="gorilla-openfunctions-v1",
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
            functions=functions,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(e)

signature = get_function_signature(
    prompt="What's the weather like in Boston?", functions=functions
)
```

#### Invoke the generated signature

```py
print(hyperfunction.invoke_from_signature(signature=signature))
```
```
{'location': 'Boston', 'temperature': '72', 'unit': 'celsius', 'forecast': ['sunny', 'windy']}
```

---

## Deep Dive 🤗

#### Create a `HyperFunction` instance

```py
from hypertion import HyperFunction

hyperfunction = HyperFunction()
```

#### Use the `takeover` decorator to register a function and utilize the `criteria` static method to define the conditions for parameter evaluation when invoking the function.

```py
import json
from enum import Enum

class Choice(Enum):
    choice1 = '1'
    choice2 = '2'

@hyperfunction.takeover(
    description="<Function's Description>"
)
def function(
    string_param: str = HyperFunction.criteria(
        description="<Description of the parameter>"),
    enum_param: Choice = HyperFunction.criteria(
        default=Choice.choice1, description="<Description of the parameter>"),
    int_param: int = HyperFunction.criteria(
        10, description="<Description of the parameter>")
):
    ...
```

> Only `str`, `int`, `list`, `dict` and `enum.Enum` types are supported.

#### Retrieve the schema specific to the LLM function.

- `OpenAI` function schema
    ```py
    openai_functions = hyperfunction.as_openai_functions
    print(json.dumps(openai_functions, indent=4))
    ```

    ```
    [
        {
            "name": "function",
            "description": "<Function's Description>",
            "parameters": {
                "type": "object",
                "properties": {
                    "string_param": {
                        "type": "string",
                        "description": "<Description of the parameter>"
                    },
                    "enum_param": {
                        "type": "string",
                        "description": "<Description of the parameter>",
                        "enum": [
                            "choice1",
                            "choice2"
                        ]
                    },
                    "int_param": {
                        "type": "integer",
                        "description": "<Description of the parameter>"
                    }
                },
                "required": [
                    "string_param"
                ]
            }
        }
    ]
    ```

- `Gorilla` function schema

    ```py
    open_functions = hyperfunction.as_open_functions
    print(json.dumps(open_functions, indent=4))
    ```

    ```
    [
        {
            "api_call": "function",
            "name": "function",
            "description": "<Function's Description>",
            "parameters": {
                "type": "object",
                "properties": {
                    "string_param": {
                        "type": "string",
                        "description": "<Description of the parameter>"
                    },
                    "enum_param": {
                        "type": "string",
                        "description": "<Description of the parameter>",
                        "enum": [
                            "choice1",
                            "choice2"
                        ]
                    },
                    "int_param": {
                        "type": "integer",
                        "description": "<Description of the parameter>"
                    }
                },
                "required": [
                    "string_param"
                ]
            }
        }
    ]
    ```

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

hyperfunction.attach_hyperfunction(new_hyperfunction)
open_functions = hyperfunction.as_open_functions

print(json.dumps(open_functions, indent=4))
```

```
[
    {
        "api_call": "function",
        "name": "function",
        "description": "<Function's Description>",
        "parameters": {
            "type": "object",
            "properties": {
                "string_param": {
                    "type": "string",
                    "description": "<Description of the parameter>"
                },
                "enum_param": {
                    "type": "string",
                    "description": "<Description of the parameter>",
                    "enum": [
                        "choice1",
                        "choice2"
                    ]
                },
                "int_param": {
                    "type": "integer",
                    "description": "<Description of the parameter>"
                }
            },
            "required": [
                "string_param"
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

#### Invoking the function using LLM generated `Signature` or `Metadata`

> Note: The `hypertion` module does not have access to any LLM-specific API, meaning it cannot directly invoke LLM to obtain gorilla-generated Signatures or GPT-generated Metadata. Implementing this functionality seems unnecessary, as various libraries produce outputs in different schemas.

- From Gorilla's OpenFunction Signature

    ```py
    import openai

    def get_function_signature(prompt: str, functions: list[dict]):
        openai.api_key = "EMPTY"
        openai.api_base = "http://luigi.millennium.berkeley.edu:8000/v1"
        try:
            completion = openai.ChatCompletion.create(
                model="gorilla-openfunctions-v1",
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
                functions=functions,
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(e)

    signature = get_function_signature(
        prompt="<Your Prompt>", functions=hyperfunction.as_open_functions
    )

    output = hyperfunction.invoke_from_signature(signature=signature)
    ```

- From OpenAI's Function Metadata

    ```py
    import json
    import openai

    def get_function_metadata(prompt: str, functions: list[dict]):
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

    name, arguments = get_function_metadata(
        prompt="<Your Prompt>", functions=hyperfunction.as_openai_functions
    )

    output = hyperfunction.invoke(name=name, arguments=arguments)
    ```

---

### Conclusion

The key strength of this approach lies in its ability to automate schema creation, sparing developers the time and complexity of manual setup. By utilizing the `takeover` decorator and `criteria` method, the system efficiently manages multiple functions within a `HyperFunction` instance, a boon for deploying Agents in LLM applications. This automation not only streamlines the development process but also ensures precision and adaptability in handling task-specific functions, making it a highly effective solution for agent-driven scenarios.