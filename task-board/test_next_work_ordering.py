#!/usr/bin/env python3
"""Focused validation for next-work age ordering and metadata."""

import json
import os
import sys
import tempfile
import copy

sys.path.insert(0, os.path.dirname(__file__))

import server

PRIORITY_ORDER = server.PRIORITY_ORDER


def make_task(task_id, title="Test", priority="normal", status="todo",
              created_at="2026-06-24T10:00:00-07:00", review_requested_at="",
              depends_on=None):
    t = {
        "id": task_id,
        "title": title,
        "project": "test",
        "priority": priority,
        "type": "implementation",
        "status": status,
        "createdAt": created_at,
        "requirements": [],
        "acceptanceCriteria": [],
        "files": [],
        "notes": "",
    }
    if review_requested_at:
        t["reviewRequestedAt"] = review_requested_at
    if depends_on is not None:
        t["dependsOn"] = depends_on
    return t


class FakeHandler:
    def ensure_column(self, columns, name):
        return columns.setdefault(name, [])

    def is_valid_task(self, task):
        return isinstance(task, dict) and bool(str(task.get("id", "") or "").strip())

    def find_task_location(self, columns, task_id):
        return server.TaskBoardHandler.find_task_location(self, columns, task_id)

    def task_in_terminal_state(self, columns, task_id):
        return server.TaskBoardHandler.task_in_terminal_state(self, columns, task_id)

    def get_unresolved_depends_on(self, columns, task):
        return server.TaskBoardHandler.get_unresolved_depends_on(self, columns, task)

    def get_derived_blocking_ids(self, columns, task_id):
        return server.TaskBoardHandler.get_derived_blocking_ids(self, columns, task_id)

    def pop_task(self, columns, col_name, task_id):
        col = columns.get(col_name, [])
        for i, t in enumerate(col):
            if str(t.get("id") or "").strip() == task_id:
                return col.pop(i)
        raise ValueError(f"Task {task_id} not in {col_name}")

    def task_exists(self, columns, task_id):
        for col_tasks in columns.values():
            for t in col_tasks:
                if str(t.get("id") or "").strip() == task_id:
                    return True
        return False

    def agent_name(self, payload, default):
        return payload.get("agentName") or default

    def persist_board(self, board):
        pass

    def update_board_timestamp(self, board, ts):
        board["updatedAt"] = ts

    def record_task_api_action(self, task, action, agent, ts):
        pass

    def record_board_api_action(self, board, action, agent, ts, task_id):
        pass

    def require_not_paused(self, action):
        pass


def test_priority_before_age():
    """Higher priority task should be selected even if it is newer."""
    h = FakeHandler()
    older_normal = make_task("T1", priority="normal", created_at="2026-06-20T10:00:00-07:00")
    newer_high = make_task("T2", priority="high", created_at="2026-06-24T10:00:00-07:00")
    columns = {"todo": [older_normal, newer_high]}
    result = server.TaskBoardHandler.select_next_work_candidate(h, columns, "todo", "createdAt")
    assert result["candidate"]["id"] == "T2", f"Expected T2 (high priority) but got {result['candidate']['id']}"
    print("PASS: priority before age")


def test_oldest_first_within_same_priority():
    """Within same priority, oldest task should be selected first."""
    h = FakeHandler()
    older = make_task("T1", priority="normal", created_at="2026-06-20T10:00:00-07:00")
    newer = make_task("T2", priority="normal", created_at="2026-06-24T10:00:00-07:00")
    columns = {"todo": [newer, older]}
    result = server.TaskBoardHandler.select_next_work_candidate(h, columns, "todo", "createdAt")
    assert result["candidate"]["id"] == "T1", f"Expected T1 (older) but got {result['candidate']['id']}"
    print("PASS: oldest first within same priority")


def test_oldest_first_three_tasks():
    """Three same-priority tasks: oldest selected first."""
    h = FakeHandler()
    t1 = make_task("T1", created_at="2026-06-22T10:00:00-07:00")
    t2 = make_task("T2", created_at="2026-06-20T10:00:00-07:00")
    t3 = make_task("T3", created_at="2026-06-24T10:00:00-07:00")
    columns = {"todo": [t1, t3, t2]}
    result = server.TaskBoardHandler.select_next_work_candidate(h, columns, "todo", "createdAt")
    assert result["candidate"]["id"] == "T2", f"Expected T2 (oldest) but got {result['candidate']['id']}"
    print("PASS: oldest first among three tasks")


def test_review_oldest_first_by_review_requested_at():
    """Reviewer next-work: oldest reviewRequestedAt first within same priority."""
    h = FakeHandler()
    older = make_task("R1", status="review", priority="normal",
                      created_at="2026-06-18T10:00:00-07:00",
                      review_requested_at="2026-06-20T10:00:00-07:00")
    newer = make_task("R2", status="review", priority="normal",
                      created_at="2026-06-20T10:00:00-07:00",
                      review_requested_at="2026-06-24T10:00:00-07:00")
    columns = {"review": [newer, older]}
    result = server.TaskBoardHandler.select_next_work_candidate(h, columns, "review", "reviewRequestedAt")
    assert result["candidate"]["id"] == "R1", f"Expected R1 (older reviewRequestedAt) but got {result['candidate']['id']}"
    print("PASS: reviewer oldest first by reviewRequestedAt")


def test_blocked_summary_ordering():
    """blockedSummary should be in priority + oldest-first order."""
    h = FakeHandler()
    dep = make_task("DEP", status="claimed", created_at="2026-06-19T10:00:00-07:00")
    older_blocked = make_task("T1", priority="high", created_at="2026-06-20T10:00:00-07:00",
                              depends_on=["DEP"])
    newer_blocked = make_task("T2", priority="high", created_at="2026-06-24T10:00:00-07:00",
                              depends_on=["DEP"])
    normal_blocked = make_task("T3", priority="normal", created_at="2026-06-18T10:00:00-07:00",
                               depends_on=["DEP"])
    columns = {"todo": [newer_blocked, normal_blocked, older_blocked], "claimed": [dep]}
    result = server.TaskBoardHandler.select_next_work_candidate(h, columns, "todo", "createdAt")
    assert result["candidate"] is None
    assert result["reason"] == "all-blocked"
    summary = result["blockedSummary"]
    assert len(summary) == 3, f"Expected 3 blocked, got {len(summary)}"
    assert summary[0]["taskId"] == "T1", f"Expected T1 (high, oldest) first, got {summary[0]['taskId']}"
    assert summary[1]["taskId"] == "T2", f"Expected T2 (high, newer) second, got {summary[1]['taskId']}"
    assert summary[2]["taskId"] == "T3", f"Expected T3 (normal) third, got {summary[2]['taskId']}"
    assert "createdAt" in summary[0], "blockedSummary entries should include createdAt"
    assert "orderingTimestamp" in summary[0], "blockedSummary entries should include orderingTimestamp"
    print("PASS: blocked summary ordering and metadata")


def test_next_work_response_metadata():
    """build_next_work_response should include status, sourceColumn, createdAt, orderingTimestamp."""
    h = FakeHandler()
    task = make_task("T1", title="Test Task", priority="high", created_at="2026-06-20T10:00:00-07:00")
    selection = {
        "candidate": task,
        "sourceColumn": "todo",
        "ageField": "createdAt",
        "orderingTimestamp": "2026-06-20T10:00:00-07:00",
        "blockedByTaskIds": [],
        "blockingTaskIds": [],
    }
    response = server.TaskBoardHandler.build_next_work_response(h, selection)
    assert response["eligible"] is True
    assert response["taskId"] == "T1"
    assert response["status"] == "todo", f"Expected status 'todo', got {response.get('status')}"
    assert response["sourceColumn"] == "todo", f"Expected sourceColumn 'todo', got {response.get('sourceColumn')}"
    assert response["createdAt"] == "2026-06-20T10:00:00-07:00", f"Expected createdAt, got {response.get('createdAt')}"
    assert response["orderingTimestamp"] == "2026-06-20T10:00:00-07:00"
    assert "detailUrl" in response
    assert "blockedByTaskIds" in response
    assert "blockingTaskIds" in response
    print("PASS: next-work response metadata")


def test_next_work_response_review_requested_at():
    """build_next_work_response should include reviewRequestedAt when present."""
    h = FakeHandler()
    task = make_task("R1", status="review", created_at="2026-06-20T10:00:00-07:00",
                     review_requested_at="2026-06-22T10:00:00-07:00")
    selection = {
        "candidate": task,
        "sourceColumn": "review",
        "ageField": "reviewRequestedAt",
        "orderingTimestamp": "2026-06-22T10:00:00-07:00",
        "blockedByTaskIds": [],
        "blockingTaskIds": [],
    }
    response = server.TaskBoardHandler.build_next_work_response(h, selection)
    assert response["reviewRequestedAt"] == "2026-06-22T10:00:00-07:00"
    assert response["sourceColumn"] == "review"
    print("PASS: next-work response includes reviewRequestedAt")


def test_no_work_response_unchanged():
    """No-work response should still work correctly."""
    h = FakeHandler()
    columns = {"todo": []}
    result = server.TaskBoardHandler.select_next_work_candidate(h, columns, "todo", "createdAt")
    assert result["candidate"] is None
    assert result["reason"] == "no-work"
    assert result["blockedSummary"] == []
    response = server.TaskBoardHandler.build_next_work_response(h, result)
    assert response["eligible"] is False
    assert response["reason"] == "no-work"
    print("PASS: no-work response unchanged")


def test_blocked_summary_includes_priority():
    """blockedSummary entries should include priority field."""
    h = FakeHandler()
    dep = make_task("DEP", status="claimed")
    blocked = make_task("T1", priority="high", created_at="2026-06-20T10:00:00-07:00",
                        depends_on=["DEP"])
    columns = {"todo": [blocked], "claimed": [dep]}
    result = server.TaskBoardHandler.select_next_work_candidate(h, columns, "todo", "createdAt")
    assert result["reason"] == "all-blocked"
    assert result["blockedSummary"][0]["priority"] == "high"
    print("PASS: blocked summary includes priority")


class ClaimFakeHandler(FakeHandler):
    """Extended FakeHandler that supports claim-next operations."""

    def select_next_work_candidate(self, columns, source_column, age_field):
        return server.TaskBoardHandler.select_next_work_candidate(self, columns, source_column, age_field)

    def build_next_work_response(self, selection):
        return server.TaskBoardHandler.build_next_work_response(self, selection)

    def require_not_paused(self, action):
        if getattr(self, "_paused", False):
            status = {
                "isPaused": True,
                "pausedUntil": "2026-06-25T02:00:00-07:00",
                "remainingSeconds": 3600,
                "remainingText": "1h 0m",
                "pauseReason": "Rate-limit cooldown",
                "message": "Task board is paused.",
            }
            payload = {
                "error": "Task board is paused.",
                "paused": True,
                "isPaused": True,
                "pausedUntil": "2026-06-25T02:00:00-07:00",
                "remainingSeconds": 3600,
                "remainingText": "1h 0m",
                "pauseReason": "Rate-limit cooldown",
                "action": action,
            }
            raise server.JsonResponseError("Task board is paused.", status=423, payload=payload)

    def get_columns(self, board):
        return board


def _make_board(todo=None, review=None):
    return {
        "columns": {
            "todo": todo or [],
            "claimed": [],
            "review": review or [],
            "reviewing": [],
            "done": [],
            "archived": [],
        },
        "updatedAt": "",
    }


def test_claim_next_worker_success_metadata():
    """Successful claim_next_worker includes full selection metadata."""
    h = ClaimFakeHandler()
    task = make_task("T1", title="Worker Task", priority="high",
                     created_at="2026-06-20T10:00:00-07:00")
    board = _make_board(todo=[task])
    columns = board["columns"]
    payload = {"agentName": "testworker"}
    result = server.TaskBoardHandler.claim_next_worker(h, board, columns, payload)
    assert result["claimed"] is True
    assert result["taskId"] == "T1"
    assert result["sourceColumn"] == "todo", f"Expected sourceColumn 'todo', got {result.get('sourceColumn')}"
    assert result["orderingTimestamp"] == "2026-06-20T10:00:00-07:00", f"Expected orderingTimestamp, got {result.get('orderingTimestamp')}"
    assert result["blockedByTaskIds"] == [], f"Expected blockedByTaskIds [], got {result.get('blockedByTaskIds')}"
    assert "blockingTaskIds" in result, "Missing blockingTaskIds"
    assert result["createdAt"] == "2026-06-20T10:00:00-07:00"
    assert result["taskIds"] == ["T1"]
    assert "detailUrl" in result
    assert "claimedAt" in result
    assert result["status"] == "claimed"
    assert result["title"] == "Worker Task"
    assert result["priority"] == "high"
    assert task["status"] == "claimed"
    assert task["claimedBy"] == "testworker"
    print("PASS: claim_next_worker success metadata")


def test_claim_next_review_success_metadata():
    """Successful claim_next_review includes full selection metadata."""
    h = ClaimFakeHandler()
    task = make_task("R1", title="Review Task", priority="normal",
                     created_at="2026-06-18T10:00:00-07:00",
                     review_requested_at="2026-06-22T10:00:00-07:00")
    board = _make_board(review=[task])
    columns = board["columns"]
    payload = {"agentName": "testreviewer"}
    result = server.TaskBoardHandler.claim_next_review(h, board, columns, payload)
    assert result["claimed"] is True
    assert result["taskId"] == "R1"
    assert result["sourceColumn"] == "review", f"Expected sourceColumn 'review', got {result.get('sourceColumn')}"
    assert result["orderingTimestamp"] == "2026-06-22T10:00:00-07:00", f"Expected orderingTimestamp from reviewRequestedAt, got {result.get('orderingTimestamp')}"
    assert result["blockedByTaskIds"] == [], f"Expected blockedByTaskIds [], got {result.get('blockedByTaskIds')}"
    assert "blockingTaskIds" in result, "Missing blockingTaskIds"
    assert result["createdAt"] == "2026-06-18T10:00:00-07:00"
    assert result["reviewRequestedAt"] == "2026-06-22T10:00:00-07:00"
    assert result["taskIds"] == ["R1"]
    assert "detailUrl" in result
    assert "reviewClaimedAt" in result
    assert result["status"] == "reviewing"
    assert result["title"] == "Review Task"
    assert task["status"] == "reviewing"
    assert task["reviewClaimedBy"] == "testreviewer"
    print("PASS: claim_next_review success metadata")


def test_claim_next_worker_paused_returns_423():
    """Paused claim_next_worker returns HTTP 423 with paused metadata."""
    h = ClaimFakeHandler()
    h._paused = True
    task = make_task("T1", created_at="2026-06-20T10:00:00-07:00")
    board = _make_board(todo=[task])
    columns = board["columns"]
    payload = {"agentName": "testworker"}
    try:
        server.TaskBoardHandler.claim_next_worker(h, board, columns, payload)
        assert False, "Expected JsonResponseError"
    except server.JsonResponseError as e:
        assert e.status == 423, f"Expected 423, got {e.status}"
        assert e.payload["paused"] is True
        assert e.payload["isPaused"] is True
        assert "pausedUntil" in e.payload
        assert "remainingSeconds" in e.payload
        assert "remainingText" in e.payload
        assert e.payload["pauseReason"] == "Rate-limit cooldown"
    assert task["status"] == "todo", "Task should not have moved during pause"
    assert len(columns["todo"]) == 1, "Todo column should be unchanged"
    assert len(columns["claimed"]) == 0, "Claimed column should be empty"
    print("PASS: claim_next_worker paused returns 423")


def test_claim_next_review_paused_returns_423():
    """Paused claim_next_review returns HTTP 423 with paused metadata."""
    h = ClaimFakeHandler()
    h._paused = True
    task = make_task("R1", status="review", created_at="2026-06-20T10:00:00-07:00",
                     review_requested_at="2026-06-22T10:00:00-07:00")
    board = _make_board(review=[task])
    columns = board["columns"]
    payload = {"agentName": "testreviewer"}
    try:
        server.TaskBoardHandler.claim_next_review(h, board, columns, payload)
        assert False, "Expected JsonResponseError"
    except server.JsonResponseError as e:
        assert e.status == 423, f"Expected 423, got {e.status}"
        assert e.payload["paused"] is True
        assert e.payload["isPaused"] is True
        assert "pausedUntil" in e.payload
        assert "remainingSeconds" in e.payload
        assert "remainingText" in e.payload
        assert e.payload["pauseReason"] == "Rate-limit cooldown"
    assert task["status"] == "review", "Task should not have moved during pause"
    assert len(columns["review"]) == 1, "Review column should be unchanged"
    assert len(columns["reviewing"]) == 0, "Reviewing column should be empty"
    print("PASS: claim_next_review paused returns 423")


def test_claim_next_worker_moves_exactly_one_task():
    """claim_next_worker atomically moves exactly one task to claimed."""
    h = ClaimFakeHandler()
    t1 = make_task("T1", priority="high", created_at="2026-06-20T10:00:00-07:00")
    t2 = make_task("T2", priority="normal", created_at="2026-06-21T10:00:00-07:00")
    columns = {"todo": [t1, t2], "claimed": []}
    board = {"columns": columns, "updatedAt": ""}
    payload = {"agentName": "testworker"}
    result = server.TaskBoardHandler.claim_next_worker(h, board, columns, payload)
    assert result["claimed"] is True
    assert result["taskId"] == "T1"
    assert len(columns["todo"]) == 1, "Only one task should be removed from todo"
    assert columns["todo"][0]["id"] == "T2"
    assert len(columns["claimed"]) == 1
    assert columns["claimed"][0]["id"] == "T1"
    print("PASS: claim_next_worker moves exactly one task")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

    original_active_pause = server.active_pause_status
    server.active_pause_status = lambda: {"isPaused": False}

    try:
        test_priority_before_age()
        test_oldest_first_within_same_priority()
        test_oldest_first_three_tasks()
        test_review_oldest_first_by_review_requested_at()
        test_blocked_summary_ordering()
        test_next_work_response_metadata()
        test_next_work_response_review_requested_at()
        test_no_work_response_unchanged()
        test_blocked_summary_includes_priority()
        test_claim_next_worker_success_metadata()
        test_claim_next_review_success_metadata()
        test_claim_next_worker_paused_returns_423()
        test_claim_next_review_paused_returns_423()
        test_claim_next_worker_moves_exactly_one_task()
        print("\nAll tests passed!")
    finally:
        server.active_pause_status = original_active_pause
