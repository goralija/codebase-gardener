from normal_service import greeting_for


def test_greeting_for_name():
    assert greeting_for("Ada") == "Hello, Ada."
