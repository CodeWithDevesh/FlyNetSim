"""System-architecture figure: one description -> editable draw.io file + SVG + PDF (for the paper).

Run: python3 paper/figures_src/make_architecture.py   (needs rsvg-convert for the PDF)
Open figures/architecture.drawio in draw.io to edit; File > Export as > PDF (crop) to replace architecture.pdf.
"""
import os, subprocess
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "figures")
os.makedirs(OUT, exist_ok=True)
W, H = 1120, 358
FS = 15  # px, ~7 pt at \textwidth

# id: (x, y, w, h, fill, stroke, title, lines)
N = {
 "arena": (10, 50, 120, 152, "#f5f5f5", "#666666", "Search arena", ["K sectors,", "one RGB +", "thermal frame", "per sector"]),
 "perc": (190, 50, 185, 152, "#dae8fc", "#6c8ebf", "1. Perception", ["RGB + thermal fusion", "YOLO11s, 1280 px", "box → sector position", "alert: victim, time"]),
 "mesh": (433, 50, 185, 152, "#d5e8d4", "#82b366", "2. Mesh comms", ["RF link gives PER", "status msg every 5 s", "per-recipient buffers", "store-carry-forward"]),
 "ctrl": (676, 50, 185, 152, "#ffe6cc", "#d79b00", "3. Swarm control", ["view from beacons", "EW-CVT, weight w(B)", "hysteresis, claims", "lease failover"]),
 "fly": (919, 50, 160, 152, "#e1d5e7", "#9673a6", "Flight & battery", ["route over sectors", "battery drain", "return at 15 %"]),
 "peers": (433, 280, 185, 62, "#f5f5f5", "#666666", "Peer UAVs", ["status, alerts"]),
 "gcs": (919, 280, 160, 62, "#f5f5f5", "#666666", "Ground station", ["passive alert sink"]),
}
CONT = (165, 12, 935, 238)  # dashed container around one UAV
CONT_TITLE = "Every UAV (× N): its own view, its own decisions, no central planner"

# edges: id, source, target, points (absolute polyline), label, label pos (x,y), dashed, both-arrows, exit/entry (drawio)
def mid(a, b): return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
def right(n): x, y, w, h = N[n][:4]; return (x + w, y + h / 2)
def left(n): x, y, w, h = N[n][:4]; return (x, y + h / 2)
def bottom(n, dx=0.5): x, y, w, h = N[n][:4]; return (x + w * dx, y + h)
def top(n, dx=0.5): x, y, w, h = N[n][:4]; return (x + w * dx, y)

E_ = [
 dict(id="e1", s="arena", t="perc", pts=[right("arena"), left("perc")], label="frames", dash=False, both=False, ex=(1, .5), en=(0, .5)),
 dict(id="e2", s="perc", t="mesh", pts=[right("perc"), left("mesh")], label="alerts", dash=False, both=False, ex=(1, .5), en=(0, .5)),
 dict(id="e3", s="mesh", t="ctrl", pts=[right("mesh"), left("ctrl")], label="peers", dash=False, both=False, ex=(1, .5), en=(0, .5)),
 dict(id="e4", s="ctrl", t="fly", pts=[right("ctrl"), left("fly")], label="route", dash=False, both=False, ex=(1, .5), en=(0, .5)),
 dict(id="e5", s="fly", t="ctrl", pts=[bottom("fly", .22), (bottom("fly", .22)[0], 226), (bottom("ctrl", .5)[0], 226), bottom("ctrl", .5)], label="position, battery",
      dash=True, both=False, ex=(.22, 1), en=(.5, 1), lab=(800, 244)),
 dict(id="e6", s="mesh", t="peers", pts=[bottom("mesh"), top("peers")], label="status, alerts", dash=True, both=True, ex=(.5, 1), en=(.5, 0), lab=(526 + 62, 272)),
 dict(id="e7", s="peers", t="gcs", pts=[right("peers"), left("gcs")], label="alerts: on contact or at return to base", dash=False, both=False, ex=(1, .5), en=(0, .5), lab=(768, 306)),
 dict(id="e8", s="gcs", t="fly", pts=[top("gcs", .78), bottom("fly", .78)], label="launch", dash=True, both=False, ex=(.78, 0), en=(.78, 1), lab=(1020, 268)),
]

# ---------------------------------------------------------------- SVG
def svg():
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Helvetica, Arial, sans-serif" font-size="{FS}">',
         '<defs><marker id="ar" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" fill="#333"/></marker>'
         '<marker id="as" markerWidth="9" markerHeight="9" refX="1" refY="4.5" orient="auto-start-reverse"><path d="M0,0 L9,4.5 L0,9 Z" fill="#333"/></marker></defs>',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
    x, y, w, h = CONT
    o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#fffbe6" stroke="#b8860b" stroke-width="1.5" stroke-dasharray="7 5"/>')
    o.append(f'<text x="{x + w / 2}" y="{y + 24}" text-anchor="middle" font-weight="bold">{escape(CONT_TITLE)}</text>')
    for k, (x, y, w, h, fill, stroke, title, lines) in N.items():
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
        ty = y + 28
        o.append(f'<text x="{x + w / 2}" y="{ty}" text-anchor="middle" font-weight="bold">{escape(title)}</text>')
        for i, ln in enumerate(lines):
            o.append(f'<text x="{x + w / 2}" y="{ty + 28 + i * 24}" text-anchor="middle">{escape(ln)}</text>')
    for e in E_:
        pts = " ".join(f"{px},{py}" for px, py in e["pts"])
        da = ' stroke-dasharray="6 4"' if e["dash"] else ""
        ms = ' marker-start="url(#as)"' if e["both"] else ""
        o.append(f'<polyline points="{pts}" fill="none" stroke="#333" stroke-width="1.8"{da} marker-end="url(#ar)"{ms}/>')
        lx, ly = e.get("lab") or (mid(e["pts"][0], e["pts"][-1])[0], mid(e["pts"][0], e["pts"][-1])[1] - 8)
        o.append(f'<text x="{lx}" y="{ly}" text-anchor="middle" font-size="{FS - 2}" fill="#222" paint-order="stroke" stroke="#ffffff" stroke-width="4">{escape(e["label"])}</text>')
    o.append("</svg>")
    return "\n".join(o)

# ---------------------------------------------------------------- draw.io
def drawio():
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    x, y, w, h = CONT
    cells.append(f'<mxCell id="cont" value="{escape(CONT_TITLE)}" style="rounded=1;dashed=1;fillColor=#fffbe6;strokeColor=#b8860b;verticalAlign=top;fontStyle=1;fontSize={FS};arcSize=4;" vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    for k, (x, y, w, h, fill, stroke, title, lines) in N.items():
        val = f"<b>{escape(title)}</b><br>" + "<br>".join(escape(l) for l in lines)
        val = escape(val, {'"': "&quot;"})
        cells.append(f'<mxCell id="{k}" value="{val}" style="rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};strokeWidth=1.6;fontSize={FS};align=center;verticalAlign=top;spacingTop=6;" vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    for e in E_:
        st = (f"endArrow=block;endFill=1;strokeWidth=1.8;fontSize={FS - 2};html=1;edgeStyle=orthogonalEdgeStyle;"
              f"exitX={e['ex'][0]};exitY={e['ex'][1]};entryX={e['en'][0]};entryY={e['en'][1]};")
        if e["dash"]: st += "dashed=1;"
        if e["both"]: st += "startArrow=block;startFill=1;"
        mids = e["pts"][1:-1]
        pts = "<Array as=\"points\">" + "".join(f'<mxPoint x="{px}" y="{py}"/>' for px, py in mids) + "</Array>" if mids else ""
        cells.append(f'<mxCell id="{e["id"]}" value="{escape(e["label"])}" style="{st}" edge="1" parent="1" source="{e["s"]}" target="{e["t"]}"><mxGeometry relative="1" as="geometry">{pts}</mxGeometry></mxCell>')
    body = "\n        ".join(cells)
    return (f'<mxfile host="app.diagrams.net"><diagram id="arch" name="Architecture"><mxGraphModel dx="{W}" dy="{H}" grid="1" gridSize="10" '
            f'page="1" pageScale="1" pageWidth="{W}" pageHeight="{H}" math="0" shadow="0"><root>\n        {body}\n      </root></mxGraphModel></diagram></mxfile>\n')

open(os.path.join(OUT, "architecture.svg"), "w").write(svg())
open(os.path.join(OUT, "architecture.drawio"), "w").write(drawio())
subprocess.run(["rsvg-convert", "-f", "pdf", "-o", os.path.join(OUT, "architecture.pdf"), os.path.join(OUT, "architecture.svg")], check=True)
subprocess.run(["rsvg-convert", "-z", "1.5", "-o", os.path.join(OUT, "architecture.png"), os.path.join(OUT, "architecture.svg")], check=True)
print("wrote", OUT)
