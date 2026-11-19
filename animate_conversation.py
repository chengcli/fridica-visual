"""Generate a standalone, offline animated replay from a Fridica snapshot."""
import argparse
from collections import defaultdict
import json
import re
from pathlib import Path

# Source excerpts anchor the editorial cues to their messages in this snapshot.
MOMENTS = [
    ("I can't post the claim yet.", "Claim deferred", "Linfeng holds off on owning lane R"),
    ("I won't take the lane O alternate slot or the lane O review.", "Refusal", "Isaac declines the lane O role"),
    ("Item 1 leaves row 0 hydro_u corners unfilled; the PM ruling remains open.", "Debate", "Tianhao challenges the corner-fill design"),
    ("Tianhao's reading is right: as written, S leaves `hydro_u`'s corners unfilled.", "Ruling", "Cheng settles the corner-fill dispute"),
    ("The only problem is the commit message: it has just the subject line, and P2 specifies a three-paragraph body.", "Changes requested", "Jiheng withholds approval on pydisort"),
]


def message_key(row, clock="ts"):
    return tuple(row[k] for k in ("workspace", "channel", "root_ts", clock))


def replay_data(graph, labels, intervals):
    """Align messages, participant roles and task intervals for both renderers."""
    rows = graph["messages"]
    if not rows:
        raise ValueError("The graph contains no messages")
    indices = {message_key(m): i for i, m in enumerate(rows)}
    label_map = {message_key(m): m for m in labels}
    if indices.keys() != label_map.keys() or len(indices) != len(rows) or len(labels) != len(rows):
        raise ValueError("Graph and annotations must describe the same unique messages")
    mentions = defaultdict(list)
    for edge in graph["edges"]:
        mentions[edge["message"]].append(edge["target"])
    threads = {}
    messages = []
    for i, row in enumerate(rows):
        key = message_key(row)
        label = label_map[key]
        if mentions[i] != [m["target"] for m in label["mentions"]]:
            raise ValueError(f"Mention mismatch at {key}")
        thread = threads.setdefault(key[:3], len(threads))
        cue = next((c for c in MOMENTS if c[0] in row["text"]), None)
        messages.append(dict(thread=thread, ts=row["ts"], sender=row["sender"], text=row["text"],
                             turn=row["turn"], round=row["round"], mentions=label["mentions"],
                             functions=list(label["functions"]), cue=cue))
    tasks = []
    for row in intervals:
        start = indices[message_key(row, "start_ts")]
        end = indices[message_key(row, "end_ts")] if row["end_ts"] else len(rows)
        tasks.append(dict(start=start, end=end, thread=messages[start]["thread"],
                          person=row["participant"], task=row["task"], status=row["status"],
                          evidence=row["evidence"], waiting=row["waiting_for"], outcome=row["outcome"]))
    return dict(nodes=graph["nodes"], messages=messages, tasks=tasks)


def anonymize(data):
    """Replace roster names and recorded account aliases before either export."""
    accounts = {"CL": ("chengcli",), "CS": ("cshsgy",), "TH": ("happysky19", "tianhaol"),
                "LF": ("linfel", "Linfeng Li"), "XZ": ("UCzhangxi",), "JL": ("JiachenLiu-Atmos", "Jiachen Liu"),
                "ZH": ("zoeyzyhu", "Zoey Hu"), "JH": ("jihenghu", "Jiheng Hu"),
                "XY": ("XinyueWang05", "Xinyue Wang")}
    lookup = {}
    for node in data["nodes"]:
        for name in [node["slack_id"], *node.get("names", []), *accounts.get(node["id"], ())]:
            lookup[name.casefold()] = node["id"]
    choices = "|".join(re.escape(k) for k in sorted(lookup, key=len, reverse=True))
    pattern = re.compile(r"(?<![^\W_])(?:" + choices + r")(?![^\W_])", re.I)
    def scrub(value):
        value = re.sub(r"<@([A-Z0-9]+)(?:\|[^>]*)?>", lambda m: lookup.get(m[1].lower(), "participant"), value)
        value = re.sub(r"<https?://[^>\n]+>", "[link]", value)
        value = re.sub(r"https?://[^\s<>|]+", "[link]", value)
        value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", value)
        value = pattern.sub(lambda m: lookup[m[0].casefold()], value)
        return re.sub(r"\b(" + "|".join(lookup.values()) + r") [ \t]*\1\b", r"\1", value)
    for m in data["messages"]:
        m["text"] = scrub(m["text"])
        if m["cue"]:
            m["cue"] = [scrub(t) for t in m["cue"]]
    for t in data["tasks"]:
        for key in ("task", "evidence", "waiting"):
            if t[key]:
                t[key] = scrub(t[key])
    data["nodes"] = [{"id": n["id"]} for n in data["nodes"]]


def render_replay(graph, labels, intervals, output):
    data = replay_data(graph, labels, intervals)
    anonymize(data)
    from replay_frame import compose_frames
    frames = compose_frames(data)
    if Path(output).suffix.lower() == ".mp4":
        from replay_video import render_video
        return render_video(frames, output)
    data["frames"] = list(frames)
    payload = json.dumps(data,
                         ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    template = Path(__file__).with_name("replay.html").read_text()
    Path(output).write_text(template.replace("__REPLAY_DATA__", payload), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("graph", "labels", "intervals", "output"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    render_replay(*(json.loads(path.read_text()) for path in (args.graph, args.labels, args.intervals)),
                  args.output)
