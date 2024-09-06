import typing as t
from enum import Enum
from pathlib import Path

import pytest

from tool_parse import ToolRegistry
from tool_parse.compile import CompileError
from tool_parse.marshal import MarshalError


# Basic registry fixture
@pytest.fixture
def basic_registry():
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

    return tr


# Complex registry fixture
@pytest.fixture
def complex_registry():
    tr = ToolRegistry()

    @tr.register
    def process_data(
        text: str,
        count: int,
        ratio: float,
        is_valid: bool,
        tags: set[str],
        items: list[str],
        metadata: dict[str, t.Any],
        file_path: Path,
        optional_param: t.Optional[int] = None,
    ) -> dict:
        """
        Process various types of data.
        :param text: A string input
        :param count: An integer count
        :param ratio: A float ratio
        :param is_valid: A boolean flag
        :param tags: A set of string tags
        :param items: A list of string items
        :param metadata: A dictionary of metadata
        :param file_path: A file path
        :param optional_param: An optional integer parameter
        """
        return {
            "text_length": len(text),
            "count_squared": count**2,
            "ratio_rounded": round(ratio, 2),
            "is_valid": is_valid,
            "unique_tags": len(tags),
            "items_count": len(items),
            "metadata_keys": list(metadata.keys()),
            "file_name": file_path.name,
            "optional_param": optional_param,
        }

    class ColorEnum(Enum):
        RED = "red"
        GREEN = "green"
        BLUE = "blue"

    @tr.register
    def color_brightness(color: ColorEnum, brightness: t.Literal["light", "dark"]) -> str:
        """
        Get color brightness description.
        :param color: The color enum
        :param brightness: The brightness level
        """
        return f"{brightness} {color.value}"

    class UserProfile(t.TypedDict):
        name: str
        age: int
        hobbies: t.List[str]

    @tr.register
    def create_user_profile(profile: UserProfile) -> str:
        """
        Create a user profile.
        :param profile: The user profile data
        """
        return f"{profile['name']} ({profile['age']}) likes {', '.join(profile['hobbies'])}"

    class BookInfo(t.NamedTuple):
        title: str
        author: str
        year: int

    @tr.register
    def format_book_info(book: BookInfo) -> str:
        """
        Format book information.
        :param book: The book information
        """
        return f"{book.title} by {book.author} ({book.year})"

    return tr


# Tests for basic registry
def test_basic_registry_content(basic_registry):
    assert len(basic_registry) == 4
    assert all(
        tool in basic_registry for tool in ["get_flight_times", "CallApi", "user_info", "HeroData"]
    )

    with pytest.raises(KeyError):
        basic_registry["non_existent_tool"]


def test_basic_registry_marshal(basic_registry):
    tools = basic_registry.marshal("base")
    assert len(tools) == 4

    flight_tool = next(tool for tool in tools if tool["function"]["name"] == "get_flight_times")
    assert flight_tool["function"]["parameters"]["required"] == ["departure", "arrival"]

    user_info_tool = next(tool for tool in tools if tool["function"]["name"] == "user_info")
    assert user_info_tool["function"]["parameters"]["properties"]["role"]["enum"] == [
        "admin",
        "tester",
    ]


def test_basic_registry_compile(basic_registry):
    assert (
        basic_registry.compile(
            name="get_flight_times", arguments={"departure": "NYC", "arrival": "JFK"}
        )
        == "2 hours"
    )

    user_info = basic_registry.compile(name="user_info", arguments={"name": "Alice"})
    assert user_info == {"name": "Alice", "role": "tester"}


# Tests for complex registry
def test_complex_registry_process_data(complex_registry):
    result = complex_registry.compile(
        name="process_data",
        arguments={
            "text": "Hello, World!",
            "count": 5,
            "ratio": 3.14159,
            "is_valid": True,
            "tags": ["python", "testing", "testing"],
            "items": ["item1", "item2", "item3"],
            "metadata": {"key1": "value1", "key2": "value2"},
            "file_path": "../test.txt",
            "optional_param": 42,
        },
    )
    assert result["text_length"] == 13
    assert result["count_squared"] == 25
    assert result["ratio_rounded"] == 3.14
    assert result["unique_tags"] == 2
    assert result["file_name"] == "test.txt"


def test_complex_registry_enum_and_literal(complex_registry):
    result = complex_registry.compile(
        name="color_brightness", arguments={"color": "RED", "brightness": "light"}
    )
    assert result == "light red"

    with pytest.raises(CompileError):
        complex_registry.compile(
            name="color_brightness", arguments={"color": "YELLOW", "brightness": "light"}
        )

    with pytest.raises(CompileError):
        complex_registry.compile(
            name="color_brightness", arguments={"color": "RED", "brightness": "medium"}
        )


def test_complex_registry_typed_dict(complex_registry):
    result = complex_registry.compile(
        name="create_user_profile",
        arguments={
            "profile": {"name": "Alice", "age": 30, "hobbies": ["reading", "hiking", "photography"]}
        },
    )
    assert result == "Alice (30) likes reading, hiking, photography"

    with pytest.raises(CompileError):
        complex_registry.compile(
            name="create_user_profile",
            arguments={"profile": {"name": "Bob", "hobbies": ["coding"]}},
        )


def test_complex_registry_named_tuple(complex_registry):
    result = complex_registry.compile(
        name="format_book_info",
        arguments={"book": {"title": "1984", "author": "George Orwell", "year": 1949}},
    )
    assert result == "1984 by George Orwell (1949)"


# Tests for MarshalError
def test_marshal_error_unsupported_type():
    tr = ToolRegistry()

    @tr.register
    def process_bytes(data: bytes) -> str:
        """Process byte data"""
        return data.decode()

    with pytest.raises(MarshalError):
        _ = tr.marshal("base")


def test_marshal_error_complex_unsupported_type():
    tr = ToolRegistry()

    @tr.register
    def process_complex_data(data: t.List[bytes]) -> str:
        """Process complex data with unsupported type"""
        return str(len(data))

    with pytest.raises(MarshalError):
        _ = tr.marshal("base")


# Additional tests for edge cases
def test_empty_registry():
    tr = ToolRegistry()
    assert len(tr) == 0
    assert tr.marshal("base") is None


def test_registry_addition():
    tr1 = ToolRegistry()
    tr2 = ToolRegistry()

    @tr1.register
    def func1():
        pass

    @tr2.register
    def func2():
        pass

    combined = tr1 + tr2
    assert len(combined) == 2
    assert "func1" in combined and "func2" in combined


def test_marshal_as_json(complex_registry):
    json_output = complex_registry.marshal(as_json=True)
    assert isinstance(json_output, str)
    assert "process_data" in json_output
    assert "color_brightness" in json_output
