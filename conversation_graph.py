"""Build a JSON-serializable directed multigraph from Fridica stores."""

from collections import defaultdict
from contextlib import closing
from decimal import Decimal
from itertools import product
import re
from string import ascii_uppercase

from fridica_visual import _connect


MENTION = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")


def _name_patterns(names):
    by_workspace = defaultdict(dict)
    for (workspace, user), variants in names.items():
        for name in variants:
            key = name.strip().lower()
            if not key or by_workspace[workspace].setdefault(key, user) != user:
                raise ValueError(f"Empty or ambiguous participant name: {name!r}")
    patterns = {}
    for workspace, users in by_workspace.items():
        choices = "|".join(re.escape(name) for name in sorted(users, key=len, reverse=True))
        patterns[workspace] = (re.compile(r"(?<!\w)(?:" + choices + r")(?!\w)", re.I), users)
    return patterns


def _mentions(text, names):
    # Scan Slack markup, code and URLs as units so their contents cannot create name hits.
    markup = re.compile(r"```[\s\S]*?```|`[^`\n]*`|<[^<>\n]+>|https?://[^\s<>]+")
    end = 0
    preceding_tag = None
    for token in markup.finditer(text):
        yield from _plain_mentions(text, end, token.start(), names, preceding_tag)
        tag = MENTION.fullmatch(token.group())
        preceding_tag = tag.group(1) if tag else None
        if tag:
            yield preceding_tag, "slack"
        end = token.end()
    yield from _plain_mentions(text, end, len(text), names, preceding_tag)


def _plain_mentions(text, start, stop, names, preceding_tag):
    if names:
        pattern, users = names
        for match in pattern.finditer(text, start, stop):
            user = users[match.group().lower()]
            if user == preceding_tag and not text[start:match.start()].strip(" \t"):
                continue
            yield user, "name"


def build_graph(databases, *, labels=None, names=None):
    """Merge stores in priority order. Labels map (workspace, Slack ID) to two letters."""
    names = names or {}
    patterns = _name_patterns(names)
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
                targets = list(_mentions(text, patterns.get(workspace)))
                records[key] = (root, sender, text, targets)
                people.add((workspace, sender))
                people.update((workspace, target) for target, _ in targets)

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
        dict(id=aliases[person], workspace=person[0], slack_id=person[1], names=list(names.get(person, ())))
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
        for target_id, kind in targets:
            target = aliases[workspace, target_id]
            edges.append(dict(source=source, target=target, message=message_index, kind=kind))
            if source != target:
                incoming_round[thread, target] = max(incoming_round[thread, target], round_no)
    return dict(nodes=nodes, messages=messages, edges=edges)
