"""Shared frame layout for the interactive and encoded replays."""
from collections import defaultdict
from datetime import datetime
from html import escape
from math import cos, sin, pi, hypot
import re
import textwrap
from zoneinfo import ZoneInfo
from refactor_timeline import chart

FRAMES_PER_SECOND = 4

KINDS = dict(decision="#ffad72", question="#8cccff", proposal="#c2a4ff",
             action_request="#ff8da8", review="#ffd273", commitment="#83dec2",
             finding="#9dd679", status_update="#9abcd4", message="#a5abb7")
STATES = dict(response_requested="#ff99ac", committed="#c5a5ff", in_progress="#5de4cf",
              waiting="#ffc768", closed="#91b1ce", unobserved="#596579")
PAPER, BG, PANEL = "#f4f3ed", "#11151c", "#1a202a"


def frame_groups(messages):
    start = 0
    while start < len(messages):
        remaining = len(messages) - start
        size = min(3, remaining)
        if remaining == 4 or (remaining > 4 and messages[start+1]["thread"] != messages[start+2]["thread"]):
            size = 2
        yield list(range(start, start + size))
        start += size


def caption(x, y, value, size, color=PAPER, *, anchor="start", bold=False, serif=False):
    family = "Georgia,DejaVu Serif,serif" if serif else "Inter,DejaVu Sans,sans-serif"
    return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}" font-size="{size}" '
            f'font-family="{family}" font-weight="{700 if bold else 400}" '
            f'text-anchor="{anchor}">{escape(str(value))}</text>')


def connection(source, target, slot, color, direct):
    x,y = source
    u,v = target
    length = hypot(u-x,v-y)
    if length:
        nx,ny = (v-y)/length,(x-u)/length
        bend = min(88, length*.28) + 24*slot
        cx,cy = (x+u)/2 + nx*bend,(y+v)/2 + ny*bend
        a,b = hypot(cx-x,cy-y),hypot(cx-u,cy-v)
        path = f'M{x+32*(cx-x)/a},{y+32*(cy-y)/a} Q{cx},{cy} {u+33*(cx-u)/b},{v+33*(cy-v)/b}'
    else:
        # Loop toward the centre so outermost nodes stay within the panel.
        s = 1 if x < 360 else -1
        path = f'M{x+s*19},{y-20} C{x+s*(94+slot*9)},{y-61} {x+s*(92+slot*9)},{y+48} {x+s*27},{y+10}'
    dash = '' if direct else ' stroke-dasharray="4 6"'
    return f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.6"{dash} marker-end="url(#tip{slot})"/>'


def compose_frames(data):
    nodes, messages = data["nodes"], data["messages"]
    names = {n["id"]:(n.get("names") or [n["id"]])[0] for n in nodes}
    def clean(text):
        return " ".join(text.replace("*","").replace("`","").split())
    pos = {n["id"]:(361+240*cos(2*pi*i/len(nodes)-pi/2),384+191*sin(2*pi*i/len(nodes)-pi/2))
           for i,n in enumerate(nodes)}
    changes = defaultdict(list)
    for t in data["tasks"]:
        changes[t["start"]].append(t)
    latest = {}
    tz = ZoneInfo("America/New_York")
    groups = list(frame_groups(messages))
    for number, ids in enumerate(groups,1):
        active = defaultdict(list)
        items = []
        for slot,i in enumerate(ids):
            m=messages[i]
            for t in changes[i]:
                latest[t["person"]]=t["status"]
            active[m["sender"]].append(str(slot+1))
            primary=next((k for k in KINDS if k in m["functions"]),"message")
            items.append((m,primary,KINDS[primary]))
        svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 840" width="1440" height="840" role="img" aria-label="Conversation replay frame">',
             f'<rect width="1440" height="840" fill="{BG}"/>',
             caption(38,62,'Fridica / Snapy V3 refactor',38,serif=True),
             caption(1400,54,f'FRAME {number:03} / {len(groups)}',18,anchor='end'),
             '<path d="M38 86 H1402" stroke="#414957"/>',
             caption(40,125,'Participants',22,bold=True),
             caption(690,125,'Outer ring = active speaker',16,'#c5c9d2',anchor='end'),
             '<ellipse cx="361" cy="384" rx="240" ry="191" fill="none" stroke="#36404f" stroke-dasharray="3 8"/>']
        for slot,(m,kind,color) in enumerate(items):
            svg.append(f'<defs><marker id="tip{slot}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="{color}"/></marker></defs>')
            targets={}
            for v in m["mentions"]:
                targets[v["target"]]=targets.get(v["target"],False) or v["role"]=="addressed"
            for target,direct in targets.items():
                svg.append(connection(pos[m["sender"]],pos[target],slot,color,direct))
        leads=[e for e in data["milestones"] if e["series"]=="lead" and e["i"]<=ids[-1]]
        lead=messages[leads[-1]["i"]]["sender"] if leads else None
        reviewers={m["sender"] for m,_,_ in items if "review" in m["functions"]}
        reviewers.update(messages[e["i"]]["sender"] for e in data["milestones"]
                         if e["series"]=="review" and e["i"] in ids)
        for who,(x,y) in pos.items():
            state=latest.get(who,"unobserved")
            color=STATES[state]
            svg.append(f'<g data-person="{escape(who,quote=True)}" role="button" tabindex="0"><title>{escape(names[who])} · {state.replace("_"," ")}</title>')
            if who in active:
                svg.append(f'<circle class="active-ring" cx="{x}" cy="{y}" r="31" fill="none" stroke="{PAPER}" stroke-width="3"/>')
            svg.append(f'<circle cx="{x}" cy="{y}" r="24" fill="{color}"/>')
            svg.extend([caption(x,y+6,who,18,BG,anchor='middle',bold=True),
                        caption(x,y+53,state.replace("_"," "),15,color,anchor='middle',bold=who in active)])
            role = "LEAD · REVIEW" if who==lead and who in reviewers else "LEAD" if who==lead else "REVIEW" if who in reviewers else ""
            if role:
                svg.append(caption(x,y-63,role,13,"#ffd273",anchor="middle",bold=True))
            if who in active:
                svg.append(caption(x,y-39,' / '.join(active[who]),15,anchor='middle',bold=True))
            svg.append('</g>')
        svg.extend(chart(messages,data["milestones"],ids[-1],caption))
        svg.extend([caption(743,425,'Conversation',21,bold=True),
                    caption(1400,425,f'{ids[0]+1:,}–{ids[-1]+1:,} of {len(messages):,}',15,anchor='end')])
        for slot,(m,kind,color) in enumerate(items):
            y=438+slot*65
            cue=m['cue']
            stamp=datetime.fromtimestamp(float(m['ts']),tz).strftime('%H:%M EST')
            quote=clean(cue[0] if cue else m['text'])
            svg.append(f'<g data-message="{ids[slot]}" role="button" tabindex="0"><rect x="740" y="{y}" rx="7" width="663" height="59" fill="{PANEL}"/><rect x="740" y="{y+5}" width="4" height="49" fill="{color}"/>')
            svg.append(caption(756,y+21,f'{slot+1}   {m["sender"]}   ·   {stamp}   ·   T{m["thread"]+1} / R{m["round"]}',15,bold=True))
            svg.append(caption(1386,y+21,(cue[1] if cue else kind.replace('_',' ')).upper(),14,color,anchor='end',bold=True))
            svg.append(caption(756,y+46,textwrap.shorten(quote,68,placeholder='…'),16,serif=True))
            svg.append('</g>')
        svg.extend([caption(40,662,'Last observed task status',19,bold=True),
                    caption(741,662,'Conversation type',19,bold=True)])
        for idx,(name,color) in enumerate(STATES.items()):
            x,y=40+(idx%3)*225,693+idx//3*31
            svg.extend([f'<circle cx="{x+7}" cy="{y-5}" r="7" fill="{color}"/>',caption(x+21,y,name.replace('_',' '),16)])
        for idx,(name,color) in enumerate(KINDS.items()):
            x,y=743+(idx%3)*215,693+idx//3*29
            svg.extend([f'<path d="M{x} {y-5} h16" stroke="{color}" stroke-width="4"/>',caption(x+23,y,name.replace('_',' '),16)])
        svg.extend([caption(40,780,'Solid arrow · addressed     /     Dashed arrow · referenced or unclear',15,'#c5c9d2'),
                    f'<rect x="40" y="804" width="1360" height="4" fill="#313a48"/><rect x="40" y="804" width="{1360*number/len(groups)}" height="4" fill="#aad9cd"/></svg>'])
        yield {'ids':ids,'svg':''.join(svg),'seconds':1 / FRAMES_PER_SECOND}
