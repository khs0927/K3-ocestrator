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


def test_flatten_preserves_assistant_reasoning_and_tool_history() -> None:
    _, dialogue = flatten_openai_messages(
        [
            {"role": "user", "content": "Inspect this"},
            {
                "role": "assistant",
                "content": "I will inspect it",
                "reasoning_content": "First check the manifest",
                "tool_calls": [{"id": "call-1", "name": "read_file"}],
            },
            {
                "role": "tool",
                "content": "file contents",
                "tool_call_id": "call-1",
            },
        ]
    )
    assert "[REASONING_CONTENT]\nFirst check the manifest" in dialogue
    assert "[TOOL_CALLS]\n[{\"id\":\"call-1\",\"name\":\"read_file\"}]" in dialogue
    assert "[TOOL_CALL_ID]\ncall-1" in dialogue
