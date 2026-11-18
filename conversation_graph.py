"""Build a JSON-serializable directed multigraph from Fridica stores."""

from collections import defaultdict
from contextlib import closing
from decimal import Decimal
from itertools import product
import re
from string import ascii_uppercase

from fridica_visual import _connect


MENTION = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")


def build_graph(databases, *, labels=None):
    """Merge stores in priority order. Labels map (workspace, Slack ID) to two letters."""
    records = {}
    people = set()
    for database in databases:
        with closing(_connect(database)) as connection:
            for workspace, channel, ts, root, sender, text in connection.execute(
                "SELECT workspace, channel, ts, root_ts, sender, text FROM messages"
            ):
                key = (workspace, channel, ts)
                if key in records:
                    continue
                targets = MENTION.findall(text)
                records[key] = (root, sender, text, targets)
                people.add((workspace, sender))
                people.update((workspace, target) for target in targets)

    aliases = dict(labels or {})
    if any(not re.fullmatch("[A-Z]{2}", label) for label in aliases.values()):
        raise ValueError("Labels must be two uppercase ASCII letters")
    reserved = set(aliases.values())
    if len(reserved) != len(aliases) or len(people | aliases.keys()) > 676:
        raise ValueError("Each participant needs a unique two-letter label")
    available = ("".join(pair) for pair in product(ascii_uppercase, repeat=2))
    for person in sorted(people - aliases.keys()):
        aliases[person] = next(label for label in available if label not in reserved)

    nodes = [
        dict(id=aliases[person], workspace=person[0], slack_id=person[1])
        for person in sorted(people)
    ]
    messages = []
    edges = []
    positions = defaultdict(int)
    incoming_round = defaultdict(int)
    for workspace, channel, ts in sorted(records, key=lambda k: (Decimal(k[2]), k[:2])):
        root, sender, text, targets = records[workspace, channel, ts]
        thread = (workspace, channel, root)
        source = aliases[workspace, sender]
        positions[thread] += 1
        round_no = incoming_round[thread, source] + 1
        message_index = len(messages)
        messages.append(dict(workspace=workspace, channel=channel, root_ts=root,
                             ts=ts, sender=source, text=text, turn=positions[thread],
                             round=round_no))
        for target_id in targets:
            target = aliases[workspace, target_id]
            edges.append(dict(source=source, target=target, message=message_index))
            if source != target:
                incoming_round[thread, target] = max(incoming_round[thread, target], round_no)
    return dict(nodes=nodes, messages=messages, edges=edges)
