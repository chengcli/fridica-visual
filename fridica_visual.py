"""Read conversation data from one Fridica SQLite store."""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Thread:
    workspace: str
    channel: str
    root_ts: str
    root_text: str | None
    message_count: int


@dataclass(frozen=True)
class Message:
    ts: str
    sender: str
    text: str


def _connect(database: str | Path) -> sqlite3.Connection:
    uri = Path(database).expanduser().resolve().as_uri()
    return sqlite3.connect(f"{uri}?mode=ro", uri=True)


def list_threads(database: str | Path, search: str = "") -> list[Thread]:
    """List oldest threads first. Match a literal substring in any message."""
    query = """
        SELECT workspace, channel, root_ts,
               MAX(CASE WHEN ts = root_ts THEN text END), COUNT(*)
        FROM messages
        GROUP BY workspace, channel, root_ts
        HAVING MAX(instr(lower(text), lower(?))) > 0
        ORDER BY CAST(root_ts AS NUMERIC), workspace, channel
    """
    with closing(_connect(database)) as connection:
        return [Thread(*row) for row in connection.execute(query, (search,))]


def load_messages(database: str | Path, thread: Thread) -> list[Message]:
    """Read the stored messages for a thread in Slack timestamp order."""
    query = """
        SELECT ts, sender, text FROM messages
        WHERE workspace = ? AND channel = ? AND root_ts = ?
        ORDER BY CAST(ts AS NUMERIC), ts
    """
    key = (thread.workspace, thread.channel, thread.root_ts)
    with closing(_connect(database)) as connection:
        return [Message(*row) for row in connection.execute(query, key)]
