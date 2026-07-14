"""Tool specs for the voice-agent replica MCP server.

Descriptions are **verbatim** from the live Claude reminder tools (captured via
a live probe) — they are the single biggest lever on behavioural parity, so do
not paraphrase them. Input schemas mirror the batched camelCase shapes the live
tools accept. ``user_time_v0`` is a stub the create/update descriptions depend
on (deny it and the agent would call a missing tool); its description is the one
reconstructed string here, flagged inline.
"""

from __future__ import annotations

from typing import Any

_PRIORITY = {"type": "string", "enum": ["none", "low", "medium", "high"]}

_ALARM = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["absolute", "relative"]},
        "date": {"type": "string", "description": "ISO 8601 absolute alarm time."},
        "secondsBefore": {
            "type": "number",
            "description": "Seconds before the due date (relative alarms).",
        },
    },
    "required": ["type"],
}

_RECURRENCE = {
    "type": "object",
    "properties": {
        "rrule": {"type": "string"},
        "humanReadableFrequency": {"type": "string"},
        "frequency": {"type": "string", "enum": ["daily", "weekly", "monthly", "yearly"]},
        "interval": {"type": "integer"},
        "daysOfWeek": {"type": "array", "items": {"type": "string"}},
        "dayOfMonth": {"type": "integer"},
        "position": {"type": "integer"},
        "months": {"type": "array", "items": {"type": "integer"}},
        "end": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["count", "until"]},
                "count": {"type": "integer"},
                "until": {"type": "string"},
            },
        },
    },
    "required": ["frequency"],
}

_ITEM = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "notes": {"type": "string"},
        "url": {"type": "string"},
        "dueDate": {"type": "string", "description": "ISO 8601."},
        "dueDateIncludesTime": {"type": "boolean"},
        "priority": _PRIORITY,
        "completionDate": {"type": "string"},
        "alarms": {"type": "array", "items": _ALARM},
        "recurrence": _RECURRENCE,
    },
    "required": ["title"],
}

_UPDATE = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "notes": {"type": "string"},
        "url": {"type": "string"},
        "priority": _PRIORITY,
        "dueDate": {"type": ["string", "null"]},
        "dueDateIncludesTime": {"type": "boolean"},
        "completionDate": {
            "type": ["string", "null"],
            "description": "Set = complete, null = mark incomplete.",
        },
        "listId": {"type": "string", "description": "Move the reminder to this list."},
        "alarms": {"type": "array", "items": _ALARM},
        "recurrence": _RECURRENCE,
    },
    "required": ["id"],
}


SPECS: list[dict[str, Any]] = [
    {
        "name": "reminder_list_search_v0",
        "description": (
            "Get available reminder lists from the user's Reminders app with "
            "optional search filtering. The number of lists is usually small so "
            "filter parameters are rarely necessary."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"searchText": {"type": "string"}},
        },
    },
    {
        "name": "reminder_search_v0",
        "description": (
            "Search and retrieve reminders from the user's Reminders app. When it "
            "makes sense, you may suggest searching the user's reminders to be "
            "proactively helpful. If you're unsure, ask for consent first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "searchText": {"type": "string"},
                "listId": {"type": "string"},
                "listName": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["incomplete", "completed"],
                    "default": "incomplete",
                },
                "dateFrom": {
                    "type": "string",
                    "description": "ISO 8601; due dates for incomplete, completion dates for completed.",
                },
                "dateTo": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
            },
        },
    },
    {
        "name": "reminder_create_v0",
        "description": (
            "Create one or more reminders in the Reminders app. Users often use "
            "Reminders for todos, shopping lists, groceries, etc. When it makes "
            "sense, suggest adding items to the user's reminders to be proactively "
            "helpful, especially if the user asks you explicitly to add items to a "
            "list. If you're unsure, ask for consent first. Always create a "
            "reminder per item for a list of items, eg a shopping or grocery list, "
            "unless asked to do otherwise. Reminders should be grouped by list ID; "
            "you may use an empty list ID to indicate that the default list should "
            "be used. Be sure to respect the user's timezone: use the user_time_v0 "
            "tool to retrieve the current time and timezone. Use when user says "
            "'remind me', 'reminder', 'todo', or lists items to remember."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "reminderLists": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "listId": {
                                "type": "string",
                                "description": "Empty or omitted = default list.",
                            },
                            "reminders": {"type": "array", "items": _ITEM},
                        },
                        "required": ["reminders"],
                    },
                }
            },
            "required": ["reminderLists"],
        },
    },
    {
        "name": "reminder_update_v0",
        "description": (
            "Updates existing reminders in the user's Reminders app. Can modify "
            "multiple reminders at once, changing properties like title, notes, "
            "due date, priority, completion status, list assignment, alarms, and "
            "recurrence. Each reminder is identified by its unique ID obtained from "
            "reminder search. Be sure to respect the user's timezone: use the "
            "user_time_v0 tool to retrieve the current time and timezone."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"reminderUpdates": {"type": "array", "items": _UPDATE}},
            "required": ["reminderUpdates"],
        },
    },
    {
        "name": "reminder_delete_v0",
        "description": (
            "Deletes existing reminders from the user's Reminders app. Can delete "
            "multiple reminders at once by specifying their unique IDs. Each "
            "reminder is permanently deleted. Exercise caution before deleting "
            "reminders and be sure this is what the user wants."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "reminderDeletions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                        },
                        "required": ["id"],
                    },
                }
            },
            "required": ["reminderDeletions"],
        },
    },
    {
        "name": "user_time_v0",
        # Reconstructed (the live description wasn't captured); a faithful stub is
        # enough — this tool exists only so date-relative create/update calls work.
        "description": (
            "Get the current date, time, and timezone for the user. Call this "
            "before creating or updating reminders with relative dates (e.g. "
            "'tomorrow', 'next week') so due dates resolve in the user's timezone."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]
