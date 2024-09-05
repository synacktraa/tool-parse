import typing as t

import pytest

from tool_parse import ToolRegistry


@pytest.fixture
def registry():
    tr = ToolRegistry()

    @tr.register
    def get_flight_times(departure: str, arrival: str) -> str:
        """
        Get flight times.
        :param departure: Departure location code
        :param arrival: Arrival location code
        """
        return "2 hours"

    async def call_api(host: str, port: int):
        """
        Call the API.
        @param host: Target host.
        @param port: Port number to request.
        """
        return {"status": "ok"}

    _ = tr.register(call_api, name="CallApi")

    @tr.register(name="user_info", description="Information of the user.")
    class UserInfo(t.TypedDict):
        """User information"""

        name: str
        role: t.Literal["admin", "tester"] = "tester"

    class HeroInfo(t.TypedDict):
        name: str
        age: t.Optional[int] = None

    class HeroData(t.NamedTuple):
        info: HeroInfo
        powers: t.Optional[list[str]]

    tr["HeroData"] = HeroData

    yield tr


def test_tool_registry(registry):
    assert len(registry) == 4

    assert "get_flight_times" in registry
    assert "CallApi" in registry
    assert "user_info" in registry
    assert "HeroData" in registry

    with pytest.raises(KeyError):
        registry["some_tool"]


def test_registry_marshal_method(registry):
    tools = registry.marshal("base")

    assert tools is not None
    assert not isinstance(tools, str)

    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "get_flight_times"
    assert tools[0]["function"]["description"] == "Get flight times."
    assert tools[0]["function"]["parameters"]["type"] == "object"
    assert tools[0]["function"]["parameters"]["required"] == ["departure", "arrival"]
    assert tools[0]["function"]["parameters"]["properties"]["departure"]["type"] == "string"
    assert (
        tools[0]["function"]["parameters"]["properties"]["departure"]["description"]
        == "Departure location code"
    )
    assert tools[0]["function"]["parameters"]["properties"]["arrival"]["type"] == "string"
    assert (
        tools[0]["function"]["parameters"]["properties"]["arrival"]["description"]
        == "Arrival location code"
    )

    assert tools[1]["type"] == "function"
    assert tools[1]["function"]["name"] == "CallApi"
    assert tools[1]["function"]["description"] == "Call the API."
    assert tools[1]["function"]["parameters"]["type"] == "object"
    assert tools[1]["function"]["parameters"]["required"] == ["host", "port"]
    assert tools[1]["function"]["parameters"]["properties"]["host"]["type"] == "string"
    assert tools[1]["function"]["parameters"]["properties"]["host"]["description"] == "Target host."
    assert tools[1]["function"]["parameters"]["properties"]["port"]["type"] == "integer"
    assert (
        tools[1]["function"]["parameters"]["properties"]["port"]["description"]
        == "Port number to request."
    )

    assert tools[2]["type"] == "function"
    assert tools[2]["function"]["name"] == "user_info"
    assert tools[2]["function"]["description"] == "Information of the user."
    assert tools[2]["function"]["parameters"]["type"] == "object"
    assert tools[2]["function"]["parameters"]["required"] == ["name"]
    assert tools[2]["function"]["parameters"]["properties"]["name"]["type"] == "string"
    assert tools[2]["function"]["parameters"]["properties"]["role"]["type"] == "string"
    assert tools[2]["function"]["parameters"]["properties"]["role"]["enum"] == ["admin", "tester"]

    assert tools[3]["type"] == "function"
    assert tools[3]["function"]["name"] == "HeroData"
    assert tools[3]["function"]["parameters"]["type"] == "object"
    assert tools[3]["function"]["parameters"]["required"] == ["info"]
    assert tools[3]["function"]["parameters"]["properties"]["info"]["type"] == "object"
    assert (
        tools[3]["function"]["parameters"]["properties"]["info"]["properties"]["name"]["type"]
        == "string"
    )
    assert (
        tools[3]["function"]["parameters"]["properties"]["info"]["properties"]["age"]["type"]
        == "integer"
    )
    assert tools[3]["function"]["parameters"]["properties"]["info"]["required"] == ["name"]
    assert tools[3]["function"]["parameters"]["properties"]["powers"]["type"] == "array"
    assert tools[3]["function"]["parameters"]["properties"]["powers"]["items"]["type"] == "string"


def test_registry_compile_method(registry):
    get_flight_times_output = registry.compile(
        name="get_flight_times", arguments={"departure": "NYC", "arrival": "JFK"}
    )
    assert get_flight_times_output == "2 hours"

    call_api_output = registry.compile(
        name="CallApi", arguments={"host": "localhost", "port": 8080}
    )
    assert call_api_output.get("status") == "ok"

    UserInfo_1_output = registry.compile(
        name="user_info", arguments={"name": "Andrej", "role": "admin"}
    )
    assert UserInfo_1_output["name"] == "Andrej"
    assert UserInfo_1_output["role"] == "admin"

    UserInfo_2_output = registry.compile("user_info(name='Synacktra')")
    assert UserInfo_2_output["name"] == "Synacktra"
    assert UserInfo_2_output["role"] == "tester"

    HeroData_1_output = registry.compile(
        name="HeroData",
        arguments={
            "info": {"name": "homelander", "age": "1"},
            "powers": ["bullying", "laser beam"],
        },
    )
    assert HeroData_1_output[0]["name"] == "homelander"
    assert HeroData_1_output.info["age"] == 1
    assert HeroData_1_output.powers[0] == "bullying"
    assert HeroData_1_output.powers[1] == "laser beam"

    HeroData_2_output = registry.compile(name="HeroData", arguments={"info": {"name": "Man"}})
    assert HeroData_2_output.info["name"] == "Man"
    assert HeroData_2_output[0]["age"] is None
    assert HeroData_2_output.powers is None
