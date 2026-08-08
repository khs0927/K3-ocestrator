from app.models import OrchestrationMode
from app.prompting import build_task_prompt, flatten_openai_messages


def test_prompt_contains_mode_policy() -> None:
    prompt = build_task_prompt("Fix the bug", OrchestrationMode.execute, "Use Python 3.12")
    assert "plan → implement → test → review" in prompt
    assert "Use Python 3.12" in prompt
    assert "Fix the bug" in prompt


def test_flatten_messages() -> None:
    system, dialogue = flatten_openai_messages(
        [
            {"role": "system", "content": "Be careful"},
            {"role": "user", "content": "Inspect this"},
        ]
    )
    assert system == "Be careful"
    assert "[USER]" in dialogue
