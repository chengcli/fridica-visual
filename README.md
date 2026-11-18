# fridica-visual

Python functions for exploring Fridica conversations before plotting them.
Use Python 3.10 or later. The module uses only the standard library.

Run Python from the repository directory. Pass a live or archived Fridica
SQLite database with a `messages` table. Each call reads one database.

```python
from fridica_visual import list_threads, load_messages

database = "~/.local/state/fridica/state.sqlite3"
for thread in list_threads(database, search="design"):
    print(thread.root_text, thread.message_count)
    for message in load_messages(database, thread):
        print(message.ts, message.sender, message.text)
```

Search matches a literal substring anywhere in the thread, ignoring ASCII
letter case. Omit the search to list every stored thread. Counts include all
stored messages for that thread. A missing root message gives `root_text=None`.
Timestamps retain Slack's original string representation.

## Directed conversation graph

```python
from conversation_graph import build_graph

graph = build_graph([database])
edge = graph["edges"][0]
message = graph["messages"][edge["message"]]
print(edge["source"], "→", edge["target"], message["ts"], message["round"])
```

Pass the live store first, followed by any archives. Duplicate messages across
stores use the first copy. Each explicit Slack user mention produces one edge,
including repeated mentions. Messages without mentions are retained. Nodes
cover both speakers and mentioned users. For reusable initials, pass a
`labels` dictionary keyed by `(workspace, slack_id)`. Unassigned participants
receive unused two-letter codes in sorted ID order.

Each message keeps its exact timestamp and a one-based turn within its thread.
Round is a measure of mention-chain depth. Everyone starts at round 1. After
someone mentions you in round N, your subsequent messages in that thread
reach at least round N+1. Self-mentions create edges but do not advance rounds.
This lets independent exchanges overlap in time. A round does not establish
that a later message answered a particular question.
