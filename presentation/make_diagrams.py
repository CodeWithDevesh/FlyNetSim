"""Flow diagrams for the presentation: one spec -> editable draw.io (.drawio) + SVG + PNG.
Run: python3 presentation/make_diagrams.py   (needs rsvg-convert). Open diagrams/*.drawio in draw.io to edit."""
import os, subprocess, textwrap
from xml.sax.saxutils import escape
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"diagrams"); os.makedirs(OUT,exist_ok=True)
FS=19
KIND={"box":("#dae8fc","#6c8ebf","rounded=1"),"dec":("#fff2cc","#d6b656","rhombus"),"term":("#d5e8d4","#82b366","rounded=1;arcSize=40"),
      "bad":("#f8cecc","#b85450","rounded=1;arcSize=40"),"gcs":("#e1d5e7","#9673a6","rounded=1"),"warm":("#ffe6cc","#d79b00","rounded=1")}
class D:
    def __init__(s,name,W,H): s.name,s.W,s.H=name,W,H; s.n={}; s.e=[]
    def node(s,i,cx,cy,text,kind="box",w=230,h=64):
        if kind=="dec": h=max(h,100); w=max(w,250)
        s.n[i]=dict(cx=cx,cy=cy,w=w,h=h,text=text,kind=kind)
    def pt(s,i,side):
        n=s.n[i]; x,y,w,h=n["cx"],n["cy"],n["w"],n["h"]
        return {"L":(x-w/2,y),"R":(x+w/2,y),"T":(x,y-h/2),"B":(x,y+h/2)}[side]
    def edge(s,a,sa,b,sb,mids=(),label="",dash=False,lab=None):
        s.e.append(dict(a=a,sa=sa,b=b,sb=sb,mids=list(mids),label=label,dash=dash,lab=lab))
    def fit(s):
        for n in s.n.values():
            L=s.lines(n); need=len(L)*(FS+4)+18
            if n['kind']=='dec': need=len(L)*(FS+4)+60
            n['h']=max(n['h'],need)
    def lines(s,n):
        k=n["kind"]; avail=n["w"]*(0.62 if k=="dec" else 0.9); cpl=max(8,int(avail/(FS*0.53)))
        return sum([textwrap.wrap(p,cpl) or [""] for p in n["text"].split("\n")],[])
    def svg(s):
        o=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{s.W}" height="{s.H}" viewBox="0 0 {s.W} {s.H}" font-family="Helvetica, Arial, sans-serif" font-size="{FS}">',
           '<defs><marker id="ar" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" fill="#333"/></marker></defs>',
           f'<rect width="{s.W}" height="{s.H}" fill="#ffffff"/>']
        for e in s.e:
            p=[s.pt(e["a"],e["sa"])]+e["mids"]+[s.pt(e["b"],e["sb"])]
            da=' stroke-dasharray="7 5"' if e["dash"] else ""
            o.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in p)}" fill="none" stroke="#333" stroke-width="1.8"{da} marker-end="url(#ar)"/>')
        for i,n in s.n.items():
            f,st,_=KIND[n["kind"]]; x,y,w,h=n["cx"]-n["w"]/2,n["cy"]-n["h"]/2,n["w"],n["h"]
            if n["kind"]=="dec": o.append(f'<polygon points="{x+w/2},{y} {x+w},{y+h/2} {x+w/2},{y+h} {x},{y+h/2}" fill="{f}" stroke="{st}" stroke-width="1.6"/>')
            else:
                rx=h/2.2 if n["kind"] in("term","bad") else 8
                o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{f}" stroke="{st}" stroke-width="1.6"/>')
            L=s.lines(n); y0=n["cy"]-(len(L)-1)*(FS+4)/2+FS*0.34
            for j,l in enumerate(L): o.append(f'<text x="{n["cx"]}" y="{y0+j*(FS+4)}" text-anchor="middle">{escape(l)}</text>')
        for e in s.e:
            if not e["label"]: continue
            p=[s.pt(e["a"],e["sa"])]+e["mids"]+[s.pt(e["b"],e["sb"])]
            lx,ly=e["lab"] or ((p[0][0]+p[1][0])/2,(p[0][1]+p[1][1])/2-7)
            o.append(f'<text x="{lx}" y="{ly}" text-anchor="middle" font-size="{FS-2}" font-style="italic" fill="#222" paint-order="stroke" stroke="#fff" stroke-width="4">{escape(e["label"])}</text>')
        o.append("</svg>"); return "\n".join(o)
    def drawio(s):
        c=['<mxCell id="0"/>','<mxCell id="1" parent="0"/>']
        for i,n in s.n.items():
            f,st,sh=KIND[n["kind"]]; val=escape("<br>".join(escape(l) for l in s.lines(n)),{'"':"&quot;"})
            style=f"{sh};whiteSpace=wrap;html=1;fillColor={f};strokeColor={st};strokeWidth=1.6;fontSize={FS};"
            c.append(f'<mxCell id="{i}" value="{val}" style="{style}" vertex="1" parent="1"><mxGeometry x="{n["cx"]-n["w"]/2}" y="{n["cy"]-n["h"]/2}" width="{n["w"]}" height="{n["h"]}" as="geometry"/></mxCell>')
        for k,e in enumerate(s.e):
            ex={"L":(0,.5),"R":(1,.5),"T":(.5,0),"B":(.5,1)}
            st=f"endArrow=block;endFill=1;strokeWidth=1.8;html=1;fontSize={FS-2};fontStyle=2;exitX={ex[e['sa']][0]};exitY={ex[e['sa']][1]};entryX={ex[e['sb']][0]};entryY={ex[e['sb']][1]};"+("dashed=1;" if e["dash"] else "")
            pts="<Array as=\"points\">"+"".join(f'<mxPoint x="{x}" y="{y}"/>' for x,y in e["mids"])+"</Array>" if e["mids"] else ""
            c.append(f'<mxCell id="e{k}" value="{escape(e["label"])}" style="{st}" edge="1" parent="1" source="{e["a"]}" target="{e["b"]}"><mxGeometry relative="1" as="geometry">{pts}</mxGeometry></mxCell>')
        body="\n        ".join(c)
        return f'<mxfile host="app.diagrams.net"><diagram id="{s.name}" name="{s.name}"><mxGraphModel dx="{s.W}" dy="{s.H}" grid="1" gridSize="10" page="1" pageScale="1" pageWidth="{s.W}" pageHeight="{s.H}"><root>\n        {body}\n      </root></mxGraphModel></diagram></mxfile>\n'
    def write(s):
        s.fit()
        b=os.path.join(OUT,s.name); open(b+".svg","w").write(s.svg()); open(b+".drawio","w").write(s.drawio())
        subprocess.run(["rsvg-convert","-z","2","-o",b+".png",b+".svg"],check=True)

# ---------------- packet delivery
d=D("packet_delivery",1130,960)
d.node("det",130,130,"UAV detects a victim; key = sector, x, y")
d.node("dup",400,130,"Already known?","dec")
d.node("ig",400,30,"ignore (de-duplicated)","bad",h=44)
d.node("snd",680,130,"For every recipient: ONE direct radio attempt")
d.node("per",680,290,"Delivered? (draw vs. PER)","dec")
d.node("rx",400,290,"Recipient stores the alert and marks it known")
d.node("dtn",960,290,"DTN buffer enabled?","dec")
d.node("lost",960,150,"copy lost","bad",h=44,w=170)
d.node("gcs",400,450,"Recipient is the GCS?","dec")
d.node("done",130,450,"First-known time recorded: latency stops","term")
d.node("fwd",400,610,"Store-carry-forward enabled?","dec")
d.node("carry",130,610,"Peer queues a copy for every recipient not known to hold it",h=80)
d.node("buf",960,450,"QoS-1 buffer per recipient (drop oldest when full)",h=80)
d.node("link",960,610,"Link PER < 0.2?","dec")
d.node("wait",680,610,"keep carrying",w=170)
d.node("chk",960,770,"Recipient already holds it?","dec")
d.node("hand",680,770,"Hand over the copy (delivered late)")
d.node("drop",960,910,"discard copy","bad",h=44,w=170)
d.edge("det","R","dup","L");d.edge("dup","T","ig","B",label="yes",lab=(425,78));d.edge("dup","R","snd","L",label="no")
d.edge("snd","B","per","T");d.edge("per","L","rx","R",label="yes");d.edge("per","R","dtn","L",label="no")
d.edge("rx","B","gcs","T");d.edge("gcs","L","done","R",label="yes");d.edge("gcs","B","fwd","T",label="no",lab=(425,535))
d.edge("fwd","L","carry","R",label="yes")
d.edge("dtn","T","lost","B",label="no",lab=(985,222));d.edge("dtn","B","buf","T",label="yes",lab=(985,372))
d.edge("buf","B","link","T");d.edge("link","L","wait","R",label="no");d.edge("link","B","chk","T",label="yes",lab=(985,692))
d.edge("chk","L","hand","R",label="no");d.edge("chk","B","drop","T",label="yes",lab=(985,842))
d.edge("hand","L","rx","L",mids=[(30,770),(30,290)],label="holder meets recipient later",dash=True,lab=(120,720))
d.write()
# ---------------- control loop
d=D("control_loop",1340,660)
X=[160,500,840,1180];Y=[70,240,410,580]
d.node("bc",X[0],Y[0],"Beacons from peers: position, g, w, state, ETA, claims, scanned set",h=80,w=270)
d.node("view",X[1],Y[0],"Local view of peers, claims and scanned sectors",w=270)
d.node("exp",X[2],Y[0],"Expire leases: overdue peer is suspected, its claims are released",h=80,w=270)
d.node("meas",X[3],Y[0],"Read own battery B (with sensor noise)",w=270)
d.node("w",X[3],Y[1],"Fresh weight w* = (B/Bmax)^alpha",w=270)
d.node("cen",X[2],Y[1],"EW-CVT centroid C* over peers believed active",w=270)
d.node("gate",X[1],Y[1],"Hysteresis gate","dec",w=250)
d.node("keep",X[0],Y[1],"Locked: keep committed g, w",w=270)
d.node("new",X[0],Y[2],"Commit: g = C*, w = w*","term",w=270)
d.node("cl",X[1],Y[2],"Claim sectors: keep mine unless beaten, take free preferred, released work only at base",h=90,w=270)
d.node("chg","chg" and X[2],Y[2],"Claim set changed?","dec",w=250)
d.node("rt",X[3],Y[2],"Rebuild route: nearest-neighbour tour, return to pad",h=80,w=270)
d.node("adv",X[2],Y[3],"Fly route; advertise ETA and claims in next beacon",h=80,w=270)
for a,b in [("bc","view"),("view","exp"),("exp","meas")]: d.edge(a,"R",b,"L")
d.edge("meas","B","w","T");d.edge("w","L","cen","R");d.edge("cen","L","gate","R");d.edge("gate","L","keep","R",label="locked")
d.edge("gate","B","new","T",mids=[(500,330),(160,330)],label="commit",lab=(330,322))
d.edge("keep","B","new","T")
d.edge("new","R","cl","L");d.edge("cl","R","chg","L");d.edge("chg","R","rt","L",label="yes");d.edge("chg","B","adv","T",label="no",lab=(865,495))
d.edge("rt","B","adv","R",mids=[(1180,580)])
d.write()
# ---------------- hysteresis gate
d=D("hysteresis_gate",1470,420)
d.node("in",140,200,"Inputs: battery B(t), centroid C*(t), live set N(t)",w=240,h=80)
d.node("q1",450,200,"Live set N(t) differs from N(t_k)?","dec",w=270,h=130)
d.node("force",450,50,"Forced override: commit now","term",w=240)
d.node("q2",790,200,"Battery down >= 2% of Bmax?","dec",w=270,h=130)
d.node("q3",1120,200,"Centroid moved >= 5 m?","dec",w=270,h=130)
d.node("com",1370,200,"COMMIT: g = C*, w = w*","term",w=170,h=80)
d.node("lock",955,370,"LOCK: keep g, w (chattering suppressed)","bad",w=300,h=60)
d.edge("in","R","q1","L");d.edge("q1","T","force","B",label="yes",lab=(475,115));d.edge("q1","R","q2","L",label="no")
d.edge("q2","R","q3","L",label="yes");d.edge("q2","B","lock","L",mids=[(790,370)],label="no",lab=(765,340))
d.edge("q3","R","com","L",label="yes");d.edge("q3","B","lock","R",mids=[(1120,370)],label="no",lab=(1145,340))
d.write()
# ---------------- failover
d=D("failover_sequence",1250,500)
d.node("ev",130,70,"Event: motor failure or battery 0% - the UAV falls silent","bad",w=230,h=80)
d.node("si",450,70,"Survivors in flight get no signal; silence is normal",w=240,h=80)
d.node("le",770,70,"Advertised return time + lease slack passes",w=240,h=80)
d.node("su",1090,70,"Peer suspected: claims released, live set changes",w=240,h=80)
d.node("ov",1090,235,"Hysteresis forced override (topology changed)","warm",w=240,h=80)
d.node("fo",770,235,"Failover enabled?","dec",w=250)
d.node("ba",450,235,"Released sectors taken only by UAVs at base",w=240,h=80)
d.node("sh",450,400,"Landed UAVs listen 10 s, split work by weighted distance, relaunch","term",w=260,h=90)
d.node("un",770,400,"Sectors stay unsearched","bad",w=220,h=60)
d.edge("ev","R","si","L");d.edge("si","R","le","L");d.edge("le","R","su","L");d.edge("su","B","ov","T");d.edge("ov","L","fo","R")
d.edge("fo","L","ba","R",label="yes");d.edge("fo","B","un","T",label="no",lab=(795,325));d.edge("ba","B","sh","T")
d.write()
# ---------------- pipeline
d=D("uav_pipeline",1330,470)
d.node("rgb",130,60,"Visible camera (RGB)",w=210,h=56);d.node("th",130,150,"Thermal camera (LWIR)",w=210,h=56)
d.node("fuse",440,105,"Early fusion: stack to a 4-channel tensor",w=240,h=70)
d.node("det",750,105,"YOLO11s detector, 1280 px, conf. 0.20",w=240,h=70)
d.node("geo",1060,105,"Georeference: box centre to sector coordinates","warm",w=250,h=70)
d.node("dd",1060,270,"De-duplication: local and swarm-wide",w=250,h=70)
d.node("al",750,270,"Alert: key, class, confidence, x, y",w=240,h=70)
d.node("snd",440,270,"Send to every UAV and GCS: one direct attempt each","gcs",w=250,h=80)
d.node("buf",440,410,"QoS-1 buffer per recipient",w=240,h=60)
d.node("fw",750,410,"Receivers keep copies and forward on later contact",w=250,h=70)
d.edge("rgb","R","fuse","L",mids=[(310,60),(310,90)]);d.edge("th","R","fuse","L",mids=[(310,150),(310,120)])
d.edge("fuse","R","det","L");d.edge("det","R","geo","L");d.edge("geo","B","dd","T");d.edge("dd","L","al","R");d.edge("al","L","snd","R")
d.edge("snd","B","buf","T",label="failed",lab=(465,345));d.edge("buf","R","fw","L",label="flush",dash=True,lab=(595,395))
d.edge("fw","T","al","B",label="re-send",dash=True,lab=(775,345))
d.write()
print("ok")
