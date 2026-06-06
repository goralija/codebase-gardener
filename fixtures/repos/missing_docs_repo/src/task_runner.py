def next_task(tasks: list[str]) -> str | None:
    if not tasks:
        return None
    return tasks[0]
