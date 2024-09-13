import typing as t

import pytest
from pydantic import BaseModel

from tool_parse import _types, exceptions, tool


def test_independent_tool():
    class Metadata(BaseModel):
        """
        Flight metadata.
        :param departure: Departure location code
        :param arrival: Arrival location code
        """

        departure: str
        arrival: str

    assert _types.is_pydantic_model(Metadata) is True

    @tool
    def get_flight_times(metadata: Metadata) -> str:
        """
        Get flight times.
        :param metadata: Flight metadata
        """
        return "2 hours"

    schema = get_flight_times.marshal("claude")

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "get_flight_times"
    assert schema["function"]["description"] == "Get flight times."
    assert schema["function"]["input_schema"]["type"] == "object"
    assert schema["function"]["input_schema"]["required"] == ["metadata"]
    assert schema["function"]["input_schema"]["properties"]["metadata"]["type"] == "object"
    assert (
        schema["function"]["input_schema"]["properties"]["metadata"]["properties"]["departure"][
            "description"
        ]
        == "Departure location code"
    )
    assert (
        schema["function"]["input_schema"]["properties"]["metadata"]["properties"]["arrival"][
            "description"
        ]
        == "Arrival location code"
    )
    # passing dictionary as arguments
    assert (
        get_flight_times.compile(arguments={"metadata": {"departure": "NYC", "arrival": "JFK"}})
        == "2 hours"
    )

    # passing json as arguments
    assert (
        get_flight_times.compile(arguments='{"metadata": {"departure": "NYC", "arrival": "JFK"}}')
        == "2 hours"
    )

    # passing call expression
    assert (
        get_flight_times.compile(
            'get_flight_times(metadata={"departure": "NYC", "arrival": "JFK"})'
        )
        == "2 hours"
    )

    with pytest.raises(ValueError):
        _ = get_flight_times.compile(
            'get_flight_time(metadata={"departure": "NYC", "arrival": "JFK"})'
        )

    with pytest.raises(exceptions.RequiredParameterException):
        _ = get_flight_times.compile('get_flight_times(metadata={"departure": "NYC"})')


def test_recursive_parameter_exception():
    @tool
    class Model(t.NamedTuple):
        """
        Model.
        :param models: set of models
        """

        models: t.Set["Model"]

    with pytest.raises(exceptions.RecursiveParameterException):
        _ = Model.marshal("claude")
