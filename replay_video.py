"""Render a compact, silent H.264 cut of the chronological replay."""
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from math import cos, sin, pi, hypot
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont


@lru_cache(None)
def font(size, family="Sans"):
    return ImageFont.truetype("DejaVu" + family + ".ttf", size)


def render_video(data, output):
    nodes, messages = data["nodes"], data["messages"]
    names = {n["id"]: (n.get("names") or [n["id"]])[0] for n in nodes}
    slack = {n["slack_id"]: names[n["id"]] for n in nodes}
    def clean(text):
        text = re.sub(r"<@([A-Z0-9]+)(?:\|[^>]*)?>", lambda m: slack.get(m[1], m[1]), text)
        return " ".join(text.replace("*", "").replace("`", "").split())

    pos = {}
    for i, n in enumerate(nodes):
        angle = 2*pi*i/len(nodes)-pi/2
        pos[n["id"]] = (round(315+211*cos(angle)), round(337+168*sin(angle)))
    paper, ink, mint = "#eeeae0", "#162633", "#8be2c8"
    base = Image.new("RGB", (1280, 720), "#111c27")
    b = ImageDraw.Draw(base)
    b.text((39, 24), "Fridica / Conversation replay", font=font(36,"Serif"), fill=paper)
    b.line((40,84,1240,84), fill="#53636e")
    b.rounded_rectangle((612,106,1240,586),12,fill=paper)
    b.text((42,111),"PARTICIPANTS",font=font(15,"SansMono"),fill=mint)
    b.ellipse((104,169,526,505),outline="#354957",width=1)
    b.text((44,550),"Solid arrow  ·  addressed     /     Dotted  ·  mentioned",font=font(16),fill=paper)
    starting = defaultdict(list)
    for t in data["tasks"]:
        starting[t["start"]].append(t)
    latest = {}
    threads = {}
    tz = ZoneInfo("America/New_York")
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        playlist = []
        for i, m in enumerate(messages):
            for t in starting[i]:
                latest[t["thread"],t["person"]] = t
            frame=base.copy()
            d=ImageDraw.Draw(frame)
            sender=m["sender"]
            x,y=pos[sender]
            targets={}
            for mention in m["mentions"]:
                who=mention["target"]
                targets[who]=targets.get(who,False) or mention["role"]=="addressed"
            for who, direct in targets.items():
                tx,ty=pos[who]
                dx,dy=tx-x,ty-y
                length=hypot(dx,dy)
                color=mint if direct else "#a7b9c8"
                if not length:
                    d.arc((x-32,y-39,x+9,y),60,345,fill=color,width=3)
                    d.polygon([(x+9,y-20),(x+3,y-28),(x+12,y-29)],fill=color)
                    continue
                ux,uy=dx/length,dy/length
                ax,ay=tx-25*ux,ty-25*uy
                if direct:
                    d.line((x,y,ax,ay),fill=color,width=3)
                else:
                    for j in range(23,int(length)-23,13):
                        d.line((x+ux*j,y+uy*j,x+ux*(j+6),y+uy*(j+6)),fill=color,width=2)
                d.polygon([(ax,ay),(ax-12*ux-5*uy,ay-12*uy+5*ux),(ax-12*ux+5*uy,ay-12*uy-5*ux)],fill=color)
            for who,(cx,cy) in pos.items():
                active=who==sender
                d.ellipse((cx-21,cy-21,cx+21,cy+21),fill=mint if active else ink,
                          outline=mint if active or who in targets else "#667c89",width=2)
                d.text((cx,cy),who,anchor="mm",font=font(17,"SansMono"),fill=ink if active else paper)
                d.text((cx,cy+28),names[who],anchor="mt",font=font(15),fill=paper)
            cue=m["cue"]
            thread=threads.setdefault(m["thread"],clean(m["text"]).split(". ")[0])
            d.text((639,130),textwrap.shorten(thread,53,placeholder="…"),font=font(16),fill="#445960")
            d.text((639,176),(cue[1] if cue else " · ".join(m["functions"][:2]).replace("_"," ")).upper(),font=font(16,"SansMono"),fill="#934526")
            heading=cue[2] if cue else names[sender]
            yy=211
            for line in textwrap.wrap(heading,29):
                d.text((639,yy),line,font=font(30,"Serif"),fill=ink);yy+=42
            quote=clean(cue[0] if cue else m["text"])
            yy+=13
            lines=textwrap.wrap(quote,width=42)
            limit=min(6,(505-yy)//32)
            for j,line in enumerate(lines[:limit]):
                if j==limit-1 and len(lines)>limit:line+="…"
                d.text((639,yy),line,font=font(21),fill=ink);yy+=32
            stamp=datetime.fromtimestamp(float(m["ts"]),tz).strftime("%b %d · %H:%M:%S %Z")
            d.text((639,544),names[sender]+"   /   "+stamp,font=font(17),fill="#425660")
            st=latest.get((m["thread"],sender))
            d.text((42,610),"LATEST TASK STATE   /   "+sender,font=font(15,"SansMono"),fill=mint)
            label=(st["status"].replace("_"," ")+"  ·  "+st["task"]) if st else "No task state observed in this thread"
            d.text((42,639),textwrap.shorten(label,91,placeholder="…"),font=font(20),fill=paper)
            d.text((1239,42),f'{i+1:,} / {len(messages):,}',anchor="rm",font=font(20,"SansMono"),fill=paper)
            d.text((1239,626),f'Turn {m["turn"]} · Round {m["round"]}',anchor="rm",font=font(15),fill=paper)
            d.rectangle((40,685,1240,690),fill="#324451")
            d.rectangle((40,685,40+1200*(i+1)/len(messages),690),fill=mint)
            path=folder/f"{i}.jpg"
            frame.save(path,quality=91,subsampling=0)
            playlist.extend([f"file '{path.name}'",f"duration {6 if cue else 0.40}"])
        playlist.append(f"file '{path.name}'")
        manifest=folder/"frames.txt"
        manifest.write_text("\n".join(playlist)+"\n")
        subprocess.run(["ffmpeg","-nostdin","-loglevel","error","-y","-f","concat","-safe","0","-i",
                        str(manifest),"-fps_mode","vfr","-c:v","libx264","-threads","3","-preset","ultrafast",
                        "-crf","21","-pix_fmt","yuv420p","-movflags","+faststart",str(output)],check=True)
