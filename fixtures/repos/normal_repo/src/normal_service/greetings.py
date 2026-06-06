def greeting_for(name: str) -> str:
    cleaned_name = name.strip() or "friend"
    return f"Hello, {cleaned_name}."
