"""Test _extract_clean_reply and _is_doc_heavy_section improvements."""
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import server


class FakeHandler:
    """Minimal handler to call _extract_clean_reply and _is_doc_heavy_section."""
    PLANNER_CHAT_OUTPUT_MARKER = server.TaskBoardHandler.PLANNER_CHAT_OUTPUT_MARKER

    def _is_noise_line(self, line):
        return server.TaskBoardHandler._is_noise_line(self, line)

    def _is_doc_heavy_section(self, section):
        return server.TaskBoardHandler._is_doc_heavy_section(self, section)

    def _extract_clean_reply(self, text):
        return server.TaskBoardHandler._extract_clean_reply(self, text)


FORBIDDEN_CLEAN_REPLY_SNIPPETS = (
    "## Allowed Files",
    "## Hard Boundary",
    "## Task Setup Rules",
    "## Task Fields",
    "## Planning Conflict Rules",
    "curl -s -X POST",
    "Invoke-RestMethod",
    '"TASK-YYYYMMDD-###"',
    "--- Process exit status ---",
    "qwen:",
    "formatter:",
    "return code",
    "...(truncated)...",
)


RAW_DIAGNOSTIC_MARKERS = (
    "Warning:",
    ">> ",
    "[OK]",
    "thinking",
    "result (success)",
    "--- Process exit status ---",
    "qwen:",
    "formatter:",
    "session_id:",
)


def assert_clean_conversational_reply(h, result):
    assert isinstance(result, str), "Clean reply should be a string"
    assert result.strip(), "Clean reply should not be empty"
    assert len(result.split()) >= 5, f"Result missing conversational content: {result[:200]}"
    assert not h._is_doc_heavy_section(result), f"Result is still doc-heavy: {result[:200]}"
    for snippet in FORBIDDEN_CLEAN_REPLY_SNIPPETS:
        assert snippet.lower() not in result.lower(), (
            f"Result contains forbidden snippet {snippet!r}: {result[:200]}"
        )


def test_extract_from_sample_session():
    """Test clean planner replies from fixture data without hiding diagnostics."""
    planner_messages = [
        {
            "role": "planner",
            "result": "Hi Richard! I can help capture requirements and turn them into board tasks.",
            "output": "thinking\nresult (success)\nHi Richard! I can help capture requirements and turn them into board tasks.\n--- Process exit status ---\nqwen:      return code 0\nformatter: return code 0",
        },
        {
            "role": "planner",
            "output": """...(truncated)...
## Task Setup Rules

1. Add new work to columns.todo.
2. Use a stable task ID.

result (success)
I added a focused task for the layout issue and linked the handoff as context.
   [duration: 5000ms]""",
        },
    ]

    h = FakeHandler()
    checked = 0
    used_stored_result = False
    for msg in planner_messages:
        stored_result = msg.get("result", "")
        raw_output = msg.get("output", "")
        if isinstance(stored_result, str) and stored_result.strip():
            source_text = stored_result
            result = h._extract_clean_reply(stored_result)
            used_stored_result = True
        elif isinstance(raw_output, str) and raw_output.strip():
            source_text = raw_output
            result = h._extract_clean_reply(raw_output)
        else:
            continue

        checked += 1
        assert_clean_conversational_reply(h, result)

        # message.output is the diagnostics surface. It may be intentionally
        # truncated and doc-heavy, but it should remain available when it
        # differs from the clean chat bubble result.
        if (
            isinstance(stored_result, str)
            and isinstance(raw_output, str)
            and stored_result.strip()
            and raw_output.strip()
            and raw_output != stored_result
        ):
            assert any(marker in raw_output for marker in RAW_DIAGNOSTIC_MARKERS), (
                f"Raw diagnostics output lost expected markers: {raw_output[:200]}"
            )

        # Long raw logs should shrink substantially; short stored result fields
        # only need to avoid growing while stripping trailing metadata.
        if len(source_text) > 1000:
            assert len(result) < len(source_text) * 0.5, (
                f"Result too long ({len(result)} chars) vs raw ({len(source_text)} chars)"
            )
        else:
            assert len(result) <= len(source_text), (
                f"Result grew unexpectedly ({len(result)} chars) vs raw ({len(source_text)} chars)"
            )

        if isinstance(raw_output, str) and "result (success)" in raw_output:
            extracted_output = h._extract_clean_reply(raw_output)
            assert_clean_conversational_reply(h, extracted_output)

    assert checked, "No planner text found in sample session"
    assert used_stored_result, "Sample session should validate stored message.result before diagnostics output"

    print(f"PASS: test_extract_from_sample_session")
    print(f"  Planner messages checked: {checked}")


def test_doc_heavy_detection():
    """Test that doc-heavy sections are correctly identified."""
    h = FakeHandler()

    # Role documentation should be doc-heavy
    doc_section = """## Allowed Files

Primary file:

- `task-board/board.json`

Reference image folder:

- `reference-images/`

## Task Setup Rules

1. Add new work to `columns.todo`.
2. Use a stable task ID.
3. Make each task small."""
    assert h._is_doc_heavy_section(doc_section), "Role docs should be doc-heavy"

    # Conversational text should NOT be doc-heavy
    convo_section = """Hey Richard! Planner-chat here, registered and ready.

What are we working on? Got new requirements, a handoff to process,
or want to check on the current board state?"""
    assert not h._is_doc_heavy_section(convo_section), "Conversational text should not be doc-heavy"

    # Mixed section with mostly docs should be doc-heavy
    mixed_section = """Here's what I found:

## API Endpoints

```bash
curl -s -X POST "/api/add-task"
```

1. First step
2. Second step

The task was created successfully."""
    assert h._is_doc_heavy_section(mixed_section), "Mixed section with mostly docs should be doc-heavy"

    print("PASS: test_doc_heavy_detection")


def test_result_marker_priority():
    """Test that text after 'result (success)' marker is prioritized."""
    h = FakeHandler()

    text = """...(truncated)...
Some role documentation here
## Section Header

More documentation content
>> tool invocation
tool output here
result (success)
Hey there! This is the actual reply.
How can I help you today?
   [duration: 5000ms]"""

    result = h._extract_clean_reply(text)
    assert "Hey there!" in result, f"Should prioritize text after result marker: {result[:200]}"
    assert "## Section Header" not in result, f"Should not include doc headers: {result[:200]}"
    assert "duration:" not in result, f"Should not include metadata: {result[:200]}"

    print("PASS: test_result_marker_priority")


def test_result_marker_strips_qwen_process_status():
    """Test that Qwen process status after a result marker stays out of the reply."""
    h = FakeHandler()

    text = """Planner chat (qwen) at 2026-06-25T01:00:00-07:00
result (success)
Hi Richard! I'm Ada, your planner. Ready to capture requirements or organize the board.

--- Process exit status ---
qwen:      return code 0
formatter: return code 0"""

    result = h._extract_clean_reply(text)
    assert "Hi Richard!" in result, f"Should keep conversational reply: {result[:200]}"
    assert "--- Process exit status ---" not in result, f"Should strip process marker: {result[:200]}"
    assert "qwen:" not in result.lower(), f"Should strip qwen return code: {result[:200]}"
    assert "formatter:" not in result.lower(), f"Should strip formatter return code: {result[:200]}"
    assert "return code" not in result.lower(), f"Should strip return-code lines: {result[:200]}"

    print("PASS: test_result_marker_strips_qwen_process_status")


def test_empty_and_edge_cases():
    """Test edge cases."""
    h = FakeHandler()

    # Empty input
    assert h._extract_clean_reply("") == "", "Empty input should return empty"

    # Only truncated marker
    assert h._extract_clean_reply("...(truncated)...") == "", "Only truncated marker should return empty"

    # Only metadata after result marker
    text = """result (success)
   [duration: 5000ms]
   cost: $0.01"""
    result = h._extract_clean_reply(text)
    # Should fall back to something reasonable
    assert isinstance(result, str), "Should always return a string"

    print("PASS: test_empty_and_edge_cases")


if __name__ == "__main__":
    test_extract_from_sample_session()
    test_doc_heavy_detection()
    test_result_marker_priority()
    test_result_marker_strips_qwen_process_status()
    test_empty_and_edge_cases()
    print("\nAll tests passed!")
