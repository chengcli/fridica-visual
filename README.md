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
