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

To include plain-text references, supply participant names and nicknames with
the same workspace/user keys as labels, for example
`build_graph([database], names={("workspace", "U123"): ["Alex Kim", "Alex"]})`.
Edges record their origin in `kind` (`slack` or `name`). Names match whole words
case-insensitively, including possessives. A Slack tag immediately followed by
the same person's name counts once. Both forms contribute to mention rounds.
The local graph snapshot stores the configured aliases in each node's `names`.

## Automatically label all messages

```python
import json
from pathlib import Path
from conversation_labels import auto_label_messages

graph = json.loads(Path("../conversation-graph.json").read_text())
labels = auto_label_messages(graph, checkpoint="../labels.sqlite3")
Path("../conversation-labels.json").write_text(json.dumps(labels, indent=2))
```

The default backend requires a signed-in Claude CLI and sends message text and
the participant roster to its model. Use `model=` to select a model, or pass
`complete(prompt)` to use your own LLM client returning JSON text. With a
custom client, set `model` to a stable backend/model identifier for caching.

Each output row carries the Slack message identity, topics, functions with
verbatim evidence, and one role per mention occurrence. A failed call or an
invalid batch raises an exception. Run again with the same checkpoint to
reuse completed batches. Labels are model judgments and may need review.

## Participant status between messages

```python
import json
from pathlib import Path
from participant_status import auto_label_participant_status

graph = json.loads(Path("../conversation-graph.json").read_text())
labels = json.loads(Path("../conversation-labels.json").read_text())
intervals = auto_label_participant_status(graph, labels, checkpoint="../status.sqlite3")
Path("../participant-status.json").write_text(json.dumps(intervals, indent=2))
```

The function calls Claude in chronological batches within each thread. The output
contains one interval per observed state change for a participant and task. The
task's thread, origin timestamp, and description link requests to later answers.
Each interval includes its exact evidence phrase from the message at `start_ts`.
Intervals include their start and exclude their end. A null end means that the
state was last observed in the snapshot, including when that state is closed.
Before the first observed interval the default is “no open action observed.”
Multiple tasks may overlap. Silence never expires an interval.

Pass `complete(prompt)` to use another LLM returning JSON text. Use a distinct
`model` identifier for each backend/model when sharing a checkpoint. Invalid
batches raise an error; completed batches are reusable on the next run.
