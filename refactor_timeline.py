"""Source-anchored Snapy V3 milestones; all times come from the matching messages."""
import re
BASELINE_LINES = 42677


def elapsed_hhmm(seconds):
    hours, minutes = divmod(int(seconds) // 60, 60)
    return f"{hours:02d}:{minutes:02d}"

# Selected first reports and substantive revisions. Replace an existing lane entry.
REPORTS = [
    ("At the snapy pin it prints *42,677*", "origin", 0, "Baseline pinned"),
    ("2,655 to 1,867 (-29.7%)", "I", 788, "I budget"),
    ("Lane total: 3,482 to 2,351", "A", 1131, "A budget"),
    ("4,677 to 3,680", "EF", 997, "EF conditional budget"),
    ("Lane O's cut is unchanged at 5,627", "O", 5627, "O proposed cut"),
    ("The evidence supports 4,413 (44.1%) today", "O", 4413, "O evidence check"),
    ("6,428 to 3,329 against", "C", 3099, "C budget"),
    ("8,472 to 7,898 within S", "S", 574, "S budget"),
    ("3,036 → 2,094", "A", 942, "A allocation revised"),
    ("2,792** without it", "R", 701, "R without conditional deletion"),
    ("9,830 to 4,473 (54.5%)", "O", 5357, "O revised budget"),
    ("4,971 to 3,896", "EF", 1075, "EF revised budget"),
    ("2,821 to 2,032", "I", 789, "I revised budget"),
    ("42,572 → 28,551", "total", 14021, "First whole-design draft"),
    ("a provisional 28,691 after figure", "total", 13986, "Corrected baseline and scope"),
    ("42,677 → 28,542 lines", "total", 14135, "Mesh allocation reconciled"),
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


# A response may change a document or a scoped patch without changing the design total.
EFFECTS = [
    ("a provisional 28,691 after figure", "Shared lines counted twice", "Revised design: 28,691 lines remaining"),
    ("RULING V3-4 closes my S rev 2.3 item 1 conflict", "Corner fill missing", "V3-4 closes the corner-fill conflict"),
    ("*`DESIGN.rst` is approved*", "Nine design fixes", "Design revision approved"),
    ("commit net +619; generated headers", "O4 exceeds its budget", "O4 patch growth: +846 → +619 (227 fewer)"),
    ("17 builds in each of 4 cases", "Repeated table rebuild", "Rebuilds per test case: 17 → 0; approved"),
    ("the commit body is now there", "Commit body missing", "Reworded commit approved; code unchanged"),
]


def milestones(messages):
    events, lanes, seen = [], {}, set()
    value = 0
    reconciled = False
    for i,m in enumerate(messages):
        for quote,scope,cut,label in REPORTS:
            if quote not in m["text"] or quote in seen:
                continue
            seen.add(quote)
            previous = value
            if scope == "total":
                value, reconciled = cut, True
            elif not reconciled:
                lanes[scope] = cut
                value = sum(lanes.values())
            else:
                continue
            events.append(dict(i=i,series="curve",value=BASELINE_LINES-value,delta=previous-value,
                               label=label))
        for quote,kind,label in REVIEWS:
            if quote in m["text"] and quote not in seen:
                events.append(dict(i=i,series="review",kind=kind,label=label));seen.add(quote)
        for quote,request,label in EFFECTS:
            if quote in m["text"] and not any(e.get("request")==request for e in events):
                prior=next((e for e in events if e["series"]=="review" and e["label"]==request),None)
                if prior:
                    events.append(dict(i=i,series="effect",request=request,origin=prior["i"],label=label))
        if "V3 design round: kickoff." in m["text"] or "handed approval of `DESIGN.rst` to me" in m["text"]:
            events.append(dict(i=i,series="lead",label="Design lead" if i==0 else "Approval / delivery lead"))
    return events


def chart(messages, events, end, caption):
    """A rolling ledger becomes the integrated estimate at the first full draft."""
    start, finish = float(messages[0]["ts"]), float(messages[-1]["ts"])
    def x(i):
        return 805 + 563*(float(messages[i]["ts"])-start)/max(1,finish-start)
    def y(lines):
        return 274-132*(lines-26000)/18000
    known=[e for e in events if e["i"]<=end]
    budgets=[e for e in known if e["series"]=="curve"]
    reviews=[e for e in known if e["series"]=="review"]
    last=budgets[-1] if budgets else None
    mint, coral, muted="#81e7cb","#ff95a5","#bac4cf"
    parts=[caption(742,119,"Design Convergence",23,bold=True)]
    for amount in (28000,35000,42000):
        at=y(amount)
        parts.extend([f'<path d="M805 {at}h563" stroke="#34404c"/>',caption(794,at+4,str(amount//1000)+"k",13,anchor="end")])
    # Connect only revealed observations. Smooth joins show direction, not measured intermediate counts.
    px,py=x(0),y(BASELINE_LINES)
    path=f"M{px} {py}"
    for b in budgets:
        xx,yy=x(b["i"]),y(b["value"])
        mid=(px+xx)/2
        path+=f" C{mid} {py} {mid} {yy} {xx} {yy}"
        px,py=xx,yy
    now=x(end)
    path+=f" H{now}"
    parts.extend([f'<path d="{path} V274 H805 Z" fill="#253c3b"/>',
                  f'<path d="{path}" fill="none" stroke="{mint}" stroke-width="3.5"/>'])
    for b in budgets:
        parts.append(f'<circle data-message="{b["i"]}" cx="{x(b["i"])}" cy="{y(b["value"])}" r="3.5" fill="{mint}"><title>{b["label"]}: {b["value"]:,}</title></circle>')
    if last:
        author=messages[last["i"]]["sender"]
        net_change = f'{last["value"] - BASELINE_LINES:,}'.replace("-", "−")
        parts.extend([f'<g data-message="{last["i"]}"><circle cx="{now}" cy="{py}" r="14" fill="{mint}"/>',
                      caption(now,py+4,author,12,"#112a28",anchor="middle",bold=True),'</g>',
                      caption(742,347,f'Refactored lines · {net_change}',17,mint,bold=True),
                      caption(1399,347,f'{author} · {last["label"]}',14,muted,anchor="end")])
    # Stagger close-in-time requests across rows, with a guide to their precise report time.
    for j,r in enumerate(reviews):
        xx=x(r["i"]); yy=176+(j%3)*29
        parts.append(f'<g data-message="{r["i"]}"><title>{r["label"]}</title><path d="M{xx} {yy+10}V278" stroke="{coral}" stroke-opacity=".4" stroke-dasharray="2 4"/><path d="M{xx-14} {yy}l14 -11 14 11 -14 11z" fill="#553244" stroke="{coral}"/>')
        parts.extend([caption(xx,yy+4,messages[r["i"]]["sender"],10,anchor="middle",bold=True),'</g>'])
    for f,anchor in [(0,'start'),(.5,'middle'),(1,'end')]:
        stamp=elapsed_hhmm((finish-start)*f)
        parts.append(caption(805+563*f,303,stamp,13,anchor=anchor))
    activity=[e for e in known if e["series"] in ("review","effect")]
    if activity:
        e=activity[-1]
        if e["series"]=="effect":
            reviewer=messages[e["origin"]]["sender"]
            note=f'{reviewer} → {messages[e["i"]]["sender"]}   {e["label"]}'
            parts.append(f'<g data-message="{e["i"]}">'+caption(742,378,note,16,mint,bold=True)+'</g>')
        else:
            note=f'{messages[e["i"]]["sender"]}   Revision requested · {e["label"]}'
            parts.append(f'<g data-message="{e["i"]}">'+caption(742,378,note,16,coral,bold=True)+'</g>')
    return parts
