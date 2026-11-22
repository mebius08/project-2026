import pytest

from text_utils import format_text


@pytest.mark.parametrize(
    ("text", "max_length", "expected"),
    [
        ("Hello", 10, "Hello"),
        ("Hello", 5, "Hello"),
        ("", 5, ""),
        ("", 0, ""),
    ],
)
def test_short_text_is_unchanged(text, max_length, expected):
    assert format_text(text, max_length) == expected


@pytest.mark.parametrize(
    ("text", "max_length", "expected"),
    [
        ("Hello world", 5, "Hello..."),
        ("Hello world", 6, "Hello..."),
        ("abcdef", 3, "abc..."),
        ("abc", 0, "..."),
    ],
)
def test_long_text_is_trimmed_and_gets_dots(text, max_length, expected):
    assert format_text(text, max_length) == expected


@pytest.mark.parametrize(
    ("text", "max_length", "expected"),
    [
        ("  Hello  ", 10, "Hello"),
        ("\tHello\n", 5, "Hello"),
        ("  Hello world  ", 5, "Hello..."),
        ("   ", 3, ""),
    ],
)
def test_spaces_at_the_ends_are_removed(text, max_length, expected):
    assert format_text(text, max_length) == expected


@pytest.mark.parametrize("text", [None, 123, ["Hello"], b"Hello"])
def test_non_string_text_raises_value_error(text):
    with pytest.raises(ValueError):
        format_text(text, 10)


@pytest.mark.parametrize("max_length", [-1, 2.5, "5", None])
def test_invalid_max_length_raises_value_error(max_length):
    with pytest.raises(ValueError):
        format_text("Hello", max_length)
