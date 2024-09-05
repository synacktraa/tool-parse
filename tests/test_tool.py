import pytest

from tool_parse import tool


def test_independent_tool():
    @tool
    def get_flight_times(departure: str, arrival: str) -> str:
        """
        Get flight times.
        :param departure: Departure location code
        :param arrival: Arrival location code
        """
        return "2 hours"

    schema = get_flight_times.marshal("claude")

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "get_flight_times"
    assert schema["function"]["description"] == "Get flight times."
    assert schema["function"]["input_schema"]["type"] == "object"
    assert schema["function"]["input_schema"]["required"] == ["departure", "arrival"]
    assert schema["function"]["input_schema"]["properties"]["departure"]["type"] == "string"
    assert (
        schema["function"]["input_schema"]["properties"]["departure"]["description"]
        == "Departure location code"
    )
    assert schema["function"]["input_schema"]["properties"]["arrival"]["type"] == "string"
    assert (
        schema["function"]["input_schema"]["properties"]["arrival"]["description"]
        == "Arrival location code"
    )

    assert get_flight_times.compile(arguments={"departure": "NYC", "arrival": "JFK"}) == "2 hours"

    assert get_flight_times.compile(arguments='{"departure": "NYC", "arrival": "JFK"}') == "2 hours"

    assert get_flight_times.compile("get_flight_times(departure='NYC', arrival='JFK')") == "2 hours"

    with pytest.raises(ValueError):
        _ = get_flight_times.compile("get_flight_time(departure='NYC', arrival='JFK')")
