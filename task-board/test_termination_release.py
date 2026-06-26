#!/usr/bin/env python3
"""Regression tests for owner termination releasing list-backed board locks."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import server


def make_task(task_id, status, owner):
    task = {
        "id": task_id,
        "title": f"Task {task_id}",
        "status": status,
        "project": "test",
        "priority": "normal",
        "type": "implementation",
        "requirements": [],
        "acceptanceCriteria": [],
        "files": [],
        "notes": "",
    }
    if status == "claimed":
        task["claimedBy"] = owner
        task["claimedAt"] = "2026-06-25T10:00:00-07:00"
    if status == "reviewing":
        task["reviewClaimedBy"] = owner
        task["reviewClaimedAt"] = "2026-06-25T10:00:00-07:00"
    return task


class FakeHandler:
    def __init__(self):
        self.persisted_board = None
        self.persisted_agents = None
        self.cleared = []

    def normalize_agent_role(self, value):
        return server.TaskBoardHandler.normalize_agent_role(self, value)

    def normalize_agent_model(self, value):
        return server.TaskBoardHandler.normalize_agent_model(self, value)

    def ensure_column(self, columns, column_name):
        return server.TaskBoardHandler.ensure_column(self, columns, column_name)

    def find_task_location(self, columns, task_id):
        return server.TaskBoardHandler.find_task_location(self, columns, task_id)

    def append_note(self, task, note):
        return server.TaskBoardHandler.append_note(self, task, note)

    def agent_name(self, payload, default):
        return payload.get("agentName") or default

    def load_active_agents_state(self):
        return {"agents": []}

    def persist_active_agents_state(self, state):
        self.persisted_agents = state

    def clear_active_agents_for_task(self, task_id, role, timestamp, note):
        self.cleared.append((task_id, role, note))

    def record_task_api_action(self, task, action, agent_name, timestamp):
        task["lastApiAction"] = action
        task["lastApiActor"] = agent_name

    def record_board_api_action(self, board, action, agent_name, timestamp, task_id):
        board.setdefault("apiAuditLog", []).append({
            "action": action,
            "agentName": agent_name,
            "taskId": task_id,
            "at": timestamp,
        })

    def update_board_timestamp(self, board, timestamp):
        board["updatedAt"] = timestamp

    def persist_board(self, board):
        self.persisted_board = board


def with_no_dispatch_persistence(callback):
    original_load = server.load_dispatch_settings
    original_persist = server.persist_dispatch_settings
    try:
        server.load_dispatch_settings = lambda: {"pendingSpawns": [], "pausedRuns": []}
        server.persist_dispatch_settings = lambda settings: None
        callback()
    finally:
        server.load_dispatch_settings = original_load
        server.persist_dispatch_settings = original_persist


def test_terminate_releases_claimed_task_to_todo():
    def run():
        handler = FakeHandler()
        board = {
            "columns": {
                "todo": [],
                "claimed": [make_task("T1", "claimed", "Ada")],
                "review": [],
                "reviewing": [],
                "done": [],
                "archived": [],
            }
        }

        result = server.TaskBoardHandler.terminate_agent(
            handler,
            board,
            board["columns"],
            {"taskId": "T1", "agentName": "owner via viewer", "reason": "test stop"},
        )

        assert result["unclaimedTaskId"] == "T1"
        assert result["destinationColumn"] == "todo"
        assert not board["columns"]["claimed"]
        assert board["columns"]["todo"][0]["id"] == "T1"
        assert board["columns"]["todo"][0]["status"] == "todo"
        assert board["columns"]["todo"][0]["claimedBy"] == ""
        assert handler.cleared and handler.cleared[0][1] == "worker"
        print("PASS: terminate releases claimed task to todo")

    with_no_dispatch_persistence(run)


def test_terminate_releases_reviewing_task_to_review():
    def run():
        handler = FakeHandler()
        board = {
            "columns": {
                "todo": [],
                "claimed": [],
                "review": [],
                "reviewing": [make_task("R1", "reviewing", "Bea")],
                "done": [],
                "archived": [],
            }
        }

        result = server.TaskBoardHandler.terminate_agent(
            handler,
            board,
            board["columns"],
            {"taskId": "R1", "agentName": "owner via viewer", "reason": "test stop"},
        )

        assert result["unclaimedTaskId"] == "R1"
        assert result["destinationColumn"] == "review"
        assert not board["columns"]["reviewing"]
        assert board["columns"]["review"][0]["id"] == "R1"
        assert board["columns"]["review"][0]["status"] == "review"
        assert board["columns"]["review"][0]["reviewClaimedBy"] == ""
        assert handler.cleared and handler.cleared[0][1] == "review"
        print("PASS: terminate releases reviewing task to review")

    with_no_dispatch_persistence(run)


def main():
    tests = [
        test_terminate_releases_claimed_task_to_todo,
        test_terminate_releases_reviewing_task_to_review,
    ]
    for test in tests:
        test()
    print(f"Results: {len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    main()
