#!/usr/bin/env python3
"""Format qwen stream-json events into human-readable log lines.

Reads JSONL from stdin, writes readable text to stdout.
Each line of input is a JSON event from qwen's --output-format stream-json.
No truncation — all content is logged in full.
"""

import json
import sys


def format_event(ev):
    lines = []
    etype = ev.get("type", "")

    if etype == "system":
        subtype = ev.get("subtype", "")
        if subtype == "init":
            model = ev.get("model", "")
            session = ev.get("session_id", "")
            version = ev.get("qwen_code_version", "")
            perm = ev.get("permission_mode", "")
            lines.append("--------")
            lines.append(f"model: {model}")
            lines.append(f"qwen_code_version: {version}")
            lines.append(f"permission_mode: {perm}")
            lines.append(f"session_id: {session}")
            lines.append("--------")

    elif etype == "assistant":
        msg = ev.get("message", {})
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                btype = block.get("type", "")
                if btype == "thinking":
                    thinking = block.get("thinking", "")
                    if thinking:
                        lines.append(f"\nthinking\n{thinking}")
                elif btype == "tool_use":
                    name = block.get("name", "?")
                    inp = block.get("input", {})
                    inp_summary = format_tool_input(name, inp)
                    lines.append(f"\n>> {name}\n{inp_summary}")
                elif btype == "text":
                    text = block.get("text", "")
                    if text:
                        lines.append(f"\n{text}")

    elif etype == "user":
        msg = ev.get("message", {})
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                btype = block.get("type", "")
                if btype == "tool_result":
                    result = block.get("content", "")
                    is_error = block.get("is_error", False)
                    status = "ERROR" if is_error else "OK"
                    result_text = str(result) if result else "(empty)"
                    lines.append(f"   [{status}] {result_text}")

    elif etype == "result":
        subtype = ev.get("subtype", "")
        result_text = ev.get("result", "")
        if result_text:
            lines.append(f"\nresult ({subtype})\n{result_text}")
        cost = ev.get("cost_usd")
        duration = ev.get("duration_ms")
        tokens_in = ev.get("input_tokens")
        tokens_out = ev.get("output_tokens")
        stats = []
        if cost is not None:
            stats.append(f"cost: ${cost:.4f}")
        if duration is not None:
            stats.append(f"duration: {duration}ms")
        if tokens_in is not None:
            stats.append(f"input_tokens: {tokens_in}")
        if tokens_out is not None:
            stats.append(f"output_tokens: {tokens_out}")
        if stats:
            lines.append(f"   [{', '.join(stats)}]")

    return "\n".join(lines)


def format_tool_input(name, inp):
    if name in ("run_shell_command", "bash"):
        cmd = inp.get("command", "")
        desc = inp.get("description", "")
        directory = inp.get("directory", "")
        parts = []
        if desc:
            parts.append(f"   Description: {desc}")
        if cmd:
            parts.append(f"   Command: {cmd}")
        if directory:
            parts.append(f"   Directory: {directory}")
        return "\n".join(parts) if parts else f"   {json.dumps(inp, ensure_ascii=False)}"
    elif name in ("read_file", "read"):
        path = inp.get("file_path", inp.get("path", ""))
        offset = inp.get("offset", "")
        limit = inp.get("limit", "")
        extra = ""
        if offset:
            extra += f" offset={offset}"
        if limit:
            extra += f" limit={limit}"
        return f"   Path: {path}{extra}"
    elif name in ("write_file", "write"):
        path = inp.get("file_path", inp.get("path", ""))
        content = inp.get("content", "")
        return f"   Path: {path}\n   Content ({len(content)} chars):\n{content}"
    elif name in ("edit",):
        path = inp.get("file_path", "")
        old = inp.get("old_string", "")
        new = inp.get("new_string", "")
        return (
            f"   Path: {path}\n"
            f"   Old:\n{old}\n"
            f"   New:\n{new}"
        )
    elif name in ("grep_search", "grep"):
        pattern = inp.get("pattern", "")
        path = inp.get("path", "")
        return f"   Pattern: {pattern}\n   Path: {path}"
    elif name == "glob":
        pattern = inp.get("pattern", "")
        path = inp.get("path", "")
        return f"   Pattern: {pattern}\n   Path: {path}"
    elif name == "tool_search":
        query = inp.get("query", "")
        return f"   Query: {query}"
    elif name == "web_fetch":
        url = inp.get("url", "")
        prompt = inp.get("prompt", "")
        return f"   URL: {url}\n   Prompt: {prompt}"
    elif name == "list_directory":
        path = inp.get("path", "")
        return f"   Path: {path}"
    elif name == "todo_write":
        todos = inp.get("todos", [])
        if todos:
            items = [f"     [{t.get('status', '')}] {t.get('content', '')}" for t in todos]
            return "   Todos:\n" + "\n".join(items)
        return f"   {json.dumps(inp, ensure_ascii=False)}"
    elif name == "agent":
        desc = inp.get("description", "")
        prompt = inp.get("prompt", "")
        subagent = inp.get("subagent_type", "")
        parts = []
        if desc:
            parts.append(f"   Description: {desc}")
        if subagent:
            parts.append(f"   Subagent type: {subagent}")
        if prompt:
            parts.append(f"   Prompt: {prompt}")
        return "\n".join(parts) if parts else f"   {json.dumps(inp, ensure_ascii=False)}"
    elif name == "notebook_edit":
        path = inp.get("notebook_path", "")
        cell_id = inp.get("cell_id", "")
        return f"   Path: {path}\n   Cell: {cell_id}"
    elif name == "ask_user_question":
        questions = inp.get("questions", [])
        if questions:
            parts = []
            for q in questions:
                parts.append(f"   Q: {q.get('question', '')}")
            return "\n".join(parts)
        return f"   {json.dumps(inp, ensure_ascii=False)}"
    else:
        return f"   {json.dumps(inp, ensure_ascii=False)}"


def main():
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            ev = json.loads(raw_line)
        except (json.JSONDecodeError, ValueError):
            continue
        output = format_event(ev)
        if output:
            sys.stdout.write(output + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
