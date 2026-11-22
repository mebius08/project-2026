def format_text(text: str, max_length: int) -> str:
    if not isinstance(text, str):
        raise ValueError("Text has to be a string")  # noqa: TRY004
    if not isinstance(max_length, int) or max_length < 0:
        raise ValueError("max_length has to be a positive number")
    text = text.strip()
    if len(text) > max_length:
        return text[:max_length].rstrip() + "..."
    return text
