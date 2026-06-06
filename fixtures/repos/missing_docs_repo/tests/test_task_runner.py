from src.task_runner import next_task


def test_next_task_returns_first_task():
    assert next_task(["observe", "diagnose"]) == "observe"
