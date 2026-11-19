"""Source-anchored Snapy V3 milestones; all times come from the matching messages."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

# Numeric series have independent scopes. Lane budgets are never summed.
REPORTS = [
    ("At the snapy pin it prints *42,677*", "target", 8536, "Whole-source target"),
    ("2,655 to 1,867 (-29.7%)", "lane", 2655-1867, "I estimate"),
    ("minus 882 or 30.7%", "lane", 882, "A forcing estimate"),
    ("4,677 to 3,680", "lane", 4677-3680, "EF conditional estimate"),
    ("6,428 to 3,329 against", "lane", 6428-3329, "C estimate"),
    ("8,472 to 7,898 within S", "lane", 8472-7898, "S estimate"),
    ("9,830 to 4,473 (54.5%)", "lane", 9830-4473, "O estimate"),
    ("a provisional 28,691 after figure", "plan", 42677-28691, "Whole-source provisional"),
    ("42,677 → 28,542 lines", "plan", 42677-28542, "Whole-source design"),
    ("O1 -2,510, O2 -2,369, O2b -362, O3 +5, O4 +846", "patch", 2510+2369+362-5-846, "O1–O4 patch net"),
    ("commit net +619; generated headers", "patch", 2510+2369+362-5-619, "O1–O4 revised net"),
]
REVIEWS = [
    ("Your 42,738 = 42,677", "Accounting error", "Shared lines counted twice"),
    ("Item 1 leaves row 0 hydro_u corners unfilled", "Design error", "Corner fill missing"),
    ("I approve it once one text commit", "Changes requested", "Nine design fixes"),
    ("O4 waits: it is 768 net lines", "Changes requested", "O4 exceeds its budget"),
    ("I recommend request changes on pydisort", "Changes requested", "Commit body missing"),
    ("kintera #105, 98fc3608: request changes. The K2", "Changes requested", "Repeated table rebuild"),
]
ROOT = re.compile(r'\b(?:V3 design round|V3 lane (?:EF|[RICSAKXO])\b|V3 wave [01]\b|Wave 0 reviewer roles in the V3 carry-out)',re.I)


def select_v3(graph, labels, intervals):
    """Keep the V3 project threads and remap edges to their new message positions."""
    def thread(m):
        return tuple(m[k] for k in ("workspace","channel","root_ts"))
    included = {thread(m) for m in graph["messages"] if m["turn"] == 1 and ROOT.search(m["text"][:250])}
    old = [i for i,m in enumerate(graph["messages"]) if thread(m) in included]
    remap = {i:j for j,i in enumerate(old)}
    return (dict(nodes=graph["nodes"], messages=[graph["messages"][i] for i in old],
                 edges=[dict(e,message=remap[e["message"]]) for e in graph["edges"] if e["message"] in remap]),
            [m for m in labels if thread(m) in included], [r for r in intervals if thread(r) in included])


def milestones(messages):
    events = []
    seen = set()
    for i,m in enumerate(messages):
        for quote,series,value,label in REPORTS:
            if quote in m["text"] and quote not in seen:
                events.append(dict(i=i,series=series,value=value,label=label));seen.add(quote)
        for quote,kind,label in REVIEWS:
            if quote in m["text"] and quote not in seen:
                events.append(dict(i=i,series="review",kind=kind,label=label));seen.add(quote)
        if "V3 design round: kickoff." in m["text"] or "handed approval of `DESIGN.rst` to me" in m["text"]:
            events.append(dict(i=i,series="lead",label="Design lead" if i==0 else "Approval / delivery lead"))
    return events


def chart(messages, events, end, caption):
    """Draw data known by this frame against a fixed wall-clock domain."""
    start, finish = float(messages[0]["ts"]), float(messages[-1]["ts"])
    def x(i):
        return 811 + 568*(float(messages[i]["ts"])-start)/max(1,finish-start)
    def y(lines):
        return 279-126*lines/16000
    colors=dict(plan="#bfacff",patch="#65dfbf",lane="#8acbff",target="#e7ce90")
    parts=[caption(742,119,"Snapy V3 · lines removed",23,bold=True),caption(1398,119,"Report time · EST",15,anchor="end")]
    for amount in (0,8000,16000):
        at=y(amount)
        parts.extend([f'<path d="M810 {at}h570" stroke="#34404c"/>',caption(799,at+5,str(amount//1000)+"k",14,anchor="end")])
    observed=[e for e in events if e["i"]<=end]
    now=x(end)
    for series,color in colors.items():
        points=[e for e in observed if e["series"]==series]
        path=""
        for e in points:
            xx,yy=x(e["i"]),y(e["value"])
            path+=(f'M{xx} {yy}' if not path else f' H{xx} V{yy}')
            parts.append(f'<circle data-message="{e["i"]}" cx="{xx}" cy="{yy}" r="4" fill="{color}"><title>{e["label"]}: {e["value"]:,} lines</title></circle>')
        if path and series!="lane":
            dash=' stroke-dasharray="5 5"' if series=="target" else ""
            parts.append(f'<path d="{path} H{now}" fill="none" stroke="{color}" stroke-width="2"{dash}/>')
    for e in observed:
        if e["series"]=="review":
            xx=x(e["i"])
            parts.append(f'<path data-message="{e["i"]}" d="M{xx-5} 284h10l-5 8z" fill="#ff95a5"><title>{messages[e["i"]]["sender"]} · {e["label"]}</title></path>')
    parts.append(f'<path d="M{now} 146V280" stroke="#d6dee5" stroke-dasharray="2 4"/>')
    tz=ZoneInfo("America/New_York")
    for f in (0,.5,1):
        stamp=datetime.fromtimestamp(start+(finish-start)*f,tz).strftime('%b %d %H:%M')
        parts.append(caption(811+568*f,310,stamp,13,anchor=('start' if f==0 else 'end' if f==1 else 'middle')))
    for xx,k,label in [(742,'plan','Whole design'),(902,'patch','Lane O patch'),(1068,'lane','Lane estimates'),(1242,'target','Target')]:
        parts.append(caption(xx,336,'● '+label,15,colors[k]))
    reports=[e for e in observed if e['series'] in colors]
    if reports:
        r=reports[-1]; parts.append(caption(742,360,f'{r["label"]} · {r["value"]:,} lines',16,colors[r["series"]],bold=True))
    reviews=[e for e in observed if e['series']=='review']
    if reviews:
        r=reviews[-1];parts.append(caption(742,385,f'▼ {messages[r["i"]]["sender"]} · {r["kind"]} · {r["label"]}',15,'#ff95a5'))
    return parts
