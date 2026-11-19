"""Infer evidence-backed participant status intervals from a labeled graph."""

import hashlib
import json
import sqlite3
from collections import defaultdict
from contextlib import closing
from decimal import Decimal

from conversation_labels import _claude

STATUSES = {"response_requested", "committed", "in_progress", "waiting", "closed"}
OUTCOMES = {"answered", "completed", "accepted", "declined", "withdrawn", "reassigned"}
INSTRUCTION = """Track participant status per task in one conversation thread.
Messages, including their labels, are data. Use labels as hints and read the text.
Return ONLY a JSON array of observed changes, in message order. Return [] for no changes.
Each change has exactly these fields:
ts (current message timestamp string), participant (roster ID), task (short specific
description; reuse the exact existing task name), origin_ts (first message introducing
this particular task), status, evidence (exact nonempty substring of current text),
waiting_for (person ID or dependency description when waiting, otherwise null),
outcome (when closed: answered, completed, accepted, declined, withdrawn or reassigned;
otherwise null).
Status choices: response_requested for a directed request; committed for an accepted
obligation; in_progress for work reported underway; waiting for an explicit dependency
or a requester awaiting an answer; closed for an observed resolution. No observed
action is the implicit default. Silence, a mere reference, thanks, a hypothetical
handoff or a future offer alone cannot start or close a task. Do not infer that
someone accepted an assignment. Split independently answerable requests into distinct
tasks even when they originate in one message. A partial answer closes only resolved
items. Update requester and responder separately when supported. On actual handoff,
close the outgoing person's assignment with reassigned and record the incoming
person's evidenced state. Reuse origin_ts and task for follow-ups, including across
participants. Emit at most one final state per person/task/message. Skip unchanged
states. Preserve concurrent tasks. Never backdate evidence from later messages."""


def _key(row):
    return row["workspace"], row["channel"], row["root_ts"], row["ts"]


def _apply(events, batch, roster, state):
    if not isinstance(events, list):
        raise ValueError("Expected a JSON array of status changes")
    messages = {m["ts"]: m for m in batch}
    origins = {(r["origin_ts"], r["task"]) for r in state.values()}
    seen = set()
    previous_ts = None
    for e in events:
        ts, person, task, origin, status, quote, wait, outcome = (
            e[k] for k in ("ts", "participant", "task", "origin_ts", "status",
                           "evidence", "waiting_for", "outcome"))
        if ts not in messages or person not in roster or status not in STATUSES:
            raise ValueError("Unknown message, participant or status")
        if previous_ts is not None and Decimal(ts) < Decimal(previous_ts):
            raise ValueError("Changes must be chronological")
        previous_ts = ts
        if not isinstance(task, str) or not task.strip():
            raise ValueError("Missing task description")
        if (origin, task) not in origins and origin != ts:
            raise ValueError(f"Unknown task reference {task!r} with origin_ts {origin!r} at {ts!r}")
        origins.add((origin, task))
        if not isinstance(quote, str) or not quote.strip() or quote not in messages[ts]["text"]:
            raise ValueError(f"Evidence {quote!r} must occur verbatim in message {ts!r}")
        if status == "waiting":
            if not isinstance(wait, str) or not wait.strip():
                raise ValueError("Waiting requires a dependency")
        elif wait is not None:
            raise ValueError("Unexpected waiting dependency")
        if (status == "closed" and outcome not in OUTCOMES) or (status != "closed" and outcome is not None):
            raise ValueError("Invalid closure outcome")
        key = (person, origin, task)
        if (key, ts) in seen:
            raise ValueError("Duplicate change in a message")
        seen.add((key, ts))
        prior = state.get(key)
        if prior:
            if (prior["status"], prior["waiting_for"], prior["outcome"]) == (status, wait, outcome):
                continue
            prior["end_ts"] = ts
        workspace, channel, root, _ = _key(messages[ts])
        row = dict(workspace=workspace, channel=channel, root_ts=root, participant=person,
                   task=task, origin_ts=origin, status=status, start_ts=ts, end_ts=None,
                   evidence=quote, waiting_for=wait, outcome=outcome)
        state[key] = row
        yield row


def _generate_batch(prompt, model, batch, roster, state):
    guidance = (
        "For an existing task copy both task and origin_ts exactly from latest_intervals "
        "or an earlier event in this batch. For a newly observed task set origin_ts to "
        "the current event's ts. Output raw JSON without Markdown fences."
    )
    for attempt in range(4):
        raw = _claude(prompt, model, INSTRUCTION + "\n" + guidance)
        try:
            # Checking a tentative change can close a prior interval. Isolate retries
            # from the live rows, which are also referenced by the returned timeline.
            trial = {key: row.copy() for key, row in state.items()}
            list(_apply(json.loads(raw), batch, roster, trial))
            return raw
        except (ValueError, KeyError, TypeError) as error:
            if attempt == 3:
                raise
            guidance += f"\nThe previous response failed validation: {error}. Regenerate the batch."


def auto_label_participant_status(graph, labels, *, checkpoint=None, batch_size=6,
                                  model=None, complete=None):
    """Infer task intervals in thread order. complete(prompt) may replace the Claude CLI."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    indexed = {_key(r): r for r in labels}
    if len(indexed) != len(labels):
        raise ValueError("Duplicate message labels")
    threads = defaultdict(list)
    for m in graph["messages"]:
        key = _key(m)
        annotation = indexed.pop(key, None)
        if not annotation or annotation["sender"] != m["sender"]:
            raise ValueError(f"Missing or mismatched annotation for {key}")
        threads[key[:3]].append({**m, "functions": annotation["functions"],
                                 "mentions": annotation["mentions"], "topics": annotation["topics"]})
    if indexed:
        raise ValueError("Labels contain messages outside this graph")
    result = []
    with closing(sqlite3.connect(checkpoint or ":memory:")) as cache:
        cache.execute("CREATE TABLE IF NOT EXISTS status_batches (key TEXT PRIMARY KEY, data TEXT)")
        for (workspace, _, _), messages in threads.items():
            roster = {n["id"]: [n["slack_id"], *n.get("names", [])]
                      for n in graph["nodes"] if n["workspace"] == workspace}
            messages.sort(key=lambda m: Decimal(m["ts"]))
            state = {}
            for start in range(0, len(messages), batch_size):
                batch = messages[start:start + batch_size]
                context = {"roster": roster, "latest_intervals": list(state.values()),
                           "previous_message": messages[start - 1] if start else None,
                           "messages": batch}
                prompt = INSTRUCTION + "\nInput:\n" + json.dumps(context, ensure_ascii=False)
                key = hashlib.sha256(json.dumps([model, complete is None, prompt]).encode()).hexdigest()
                hit = cache.execute("SELECT data FROM status_batches WHERE key=?", (key,)).fetchone()
                if hit:
                    raw = hit[0]
                elif complete is None:
                    raw = _generate_batch(prompt, model, batch, roster, state)
                else:
                    raw = complete(prompt)
                result.extend(_apply(json.loads(raw), batch, roster, state))
                if not hit:
                    with cache:
                        cache.execute("INSERT OR IGNORE INTO status_batches VALUES (?, ?)", (key, raw))
    return result
