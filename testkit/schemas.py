"""JSON Schema fragments for the reminder tool inputs.

Mirror the batched, camelCase shapes the live reminder_*_v0 tools accept.
Assembled into full tool specs in ``tools.py``.
"""

from __future__ import annotations

PRIORITY = {"type": "string", "enum": ["none", "low", "medium", "high"]}

ALARM = {
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

RECURRENCE = {
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

ITEM = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "notes": {"type": "string"},
        "url": {"type": "string"},
        "dueDate": {"type": "string", "description": "ISO 8601."},
        "dueDateIncludesTime": {"type": "boolean"},
        "priority": PRIORITY,
        "completionDate": {"type": "string"},
        "alarms": {"type": "array", "items": ALARM},
        "recurrence": RECURRENCE,
    },
    "required": ["title"],
}

UPDATE = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "notes": {"type": "string"},
        "url": {"type": "string"},
        "priority": PRIORITY,
        "dueDate": {"type": ["string", "null"]},
        "dueDateIncludesTime": {"type": "boolean"},
        "completionDate": {
            "type": ["string", "null"],
            "description": "Set = complete, null = mark incomplete.",
        },
        "listId": {"type": "string", "description": "Move the reminder to this list."},
        "alarms": {"type": "array", "items": ALARM},
        "recurrence": RECURRENCE,
    },
    "required": ["id"],
}
