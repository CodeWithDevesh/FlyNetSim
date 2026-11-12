"""Builds presentation/FlyNetSim_Presentation.pptx (16:9). Diagrams come from presentation/diagrams (draw.io exports)."""
import os
from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DG=lambda n: os.path.join(HERE,"diagrams",n); RF=lambda n: os.path.join(ROOT,"results","figures",n)
LOGO="/home/devesh/DrishtiKon_Report/logo.png"
NAVY=RGBColor(0x12,0x35,0x5B); TEAL=RGBColor(0x1F,0x8A,0x9E); GREY=RGBColor(0x44,0x4B,0x55); LIGHT=RGBColor(0xEE,0xF3,0xF8); WHITE=RGBColor(255,255,255); ORANGE=RGBColor(0xD9,0x7B,0x1A)
FONT="Calibri"
prs=Presentation(); prs.slide_width=Inches(13.333); prs.slide_height=Inches(7.5)
BL=prs.slide_layouts[6]; SW,SH=13.333,7.5
TOTAL=16; warn=[]

def tb(sl,x,y,w,h,paras,size=18,color=GREY,bold=False,align=PP_ALIGN.LEFT,anchor=MSO_ANCHOR.TOP,bullet=False,space=6,check=True):
    box=sl.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h)); tf=box.text_frame; tf.word_wrap=True
    tf.margin_left=tf.margin_right=Inches(0.05); tf.margin_top=tf.margin_bottom=Inches(0.03); tf.vertical_anchor=anchor
    if isinstance(paras,str): paras=[paras]
    est=0
    for i,p in enumerate(paras):
        sz=size; b=bold; col=color; txt=p
        if isinstance(p,tuple): txt,opts=p; sz=opts.get("size",size); b=opts.get("bold",bold); col=opts.get("color",color)
        para=tf.paragraphs[0] if i==0 else tf.add_paragraph()
        para.alignment=align; para.space_after=Pt(space)
        r=para.add_run(); r.text=("•  "+txt) if bullet else txt
        r.font.size=Pt(sz); r.font.bold=b; r.font.color.rgb=col; r.font.name=FONT
        cpl=max(1,int(w*72/(sz*0.5))); est+=(-(-len(r.text)//cpl))*sz*1.2+space
    if check and est/72>h+0.05: warn.append(f"text overflow ~{est/72:.2f}in>{h}in: {str(paras)[:60]}")
    return box

def rect(sl,x,y,w,h,fill,line=None,shape=MSO_SHAPE.RECTANGLE):
    s=sl.shapes.add_shape(shape,Inches(x),Inches(y),Inches(w),Inches(h)); s.fill.solid(); s.fill.fore_color.rgb=fill
    if line: s.line.color.rgb=line; s.line.width=Pt(1)
    else: s.line.fill.background()
    s.shadow.inherit=False; return s

def pic(sl,path,x,y,maxw,maxh,center=True):
    w,h=Image.open(path).size; sc=min(maxw/w,maxh/h); pw,ph=w*sc,h*sc
    px=x+(maxw-pw)/2 if center else x; py=y+(maxh-ph)/2 if center else y
    sl.shapes.add_picture(path,Inches(px),Inches(py),Inches(pw),Inches(ph)); return pw,ph

def slide(title,notes="",n=[0]):
    sl=prs.slides.add_slide(BL); n[0]+=1
    rect(sl,0,0,SW,1.0,NAVY); rect(sl,0,1.0,SW,0.06,TEAL)
    tb(sl,0.5,0.17,11.6,0.7,title,size=30,color=WHITE,bold=True,anchor=MSO_ANCHOR.MIDDLE,check=False)
    s=sl.shapes.add_picture(LOGO,Inches(12.2),Inches(0.12),height=Inches(0.76))
    tb(sl,0.5,7.08,9,0.3,"Decentralised Multispectral UAV Swarms for Search and Rescue",size=10,color=GREY,check=False)
    tb(sl,11.8,7.08,1.05,0.3,f"{n[0]+1} / {TOTAL}",size=10,color=GREY,align=PP_ALIGN.RIGHT,check=False)
    if notes: sl.notes_slide.notes_text_frame.text=notes
    return sl

def card(sl,x,y,w,h,head,body,hc=TEAL,size=18):
    rect(sl,x,y,w,h,LIGHT); rect(sl,x,y,0.08,h,hc)
    tb(sl,x+0.2,y+0.1,w-0.3,0.5,head,size=18,color=NAVY,bold=True,check=False)
    tb(sl,x+0.2,y+0.62,w-0.3,h-0.7,body,size=size,bullet=isinstance(body,list),space=8)

def stat(sl,x,y,w,big,small,col=TEAL):
    rect(sl,x,y,w,1.35,LIGHT); rect(sl,x,y,w,0.07,col)
    tb(sl,x,y+0.12,w,0.65,big,size=32,color=col,bold=True,align=PP_ALIGN.CENTER,check=False)
    tb(sl,x+0.1,y+0.78,w-0.2,0.55,small,size=12,align=PP_ALIGN.CENTER)

def table(sl,x,y,w,rows,colw,size=13,rowh=0.36,boldcol0=True,hl=None):
    t=sl.shapes.add_table(len(rows),len(rows[0]),Inches(x),Inches(y),Inches(w),Inches(rowh*len(rows))).table
    for j,cw in enumerate(colw): t.columns[j].width=Inches(cw)
    for i,r in enumerate(rows):
        t.rows[i].height=Inches(rowh)
        for j,v in enumerate(r):
            c=t.cell(i,j); c.text=""; p=c.text_frame.paragraphs[0]; run=p.add_run(); run.text=str(v)
            run.font.size=Pt(size); run.font.name=FONT; c.margin_left=c.margin_right=Inches(0.06); c.margin_top=c.margin_bottom=Inches(0.02)
            c.vertical_anchor=MSO_ANCHOR.MIDDLE; p.alignment=PP_ALIGN.LEFT if j==0 else PP_ALIGN.CENTER
            c.fill.solid()
            if i==0: c.fill.fore_color.rgb=NAVY; run.font.color.rgb=WHITE; run.font.bold=True
            else:
                c.fill.fore_color.rgb=RGBColor(0xDF,0xF1,0xE6) if (hl and i in hl) else (LIGHT if i%2 else WHITE)
                run.font.color.rgb=GREY; run.font.bold=(j==0 and boldcol0) or (hl is not None and i in hl)
    return t

# 1 ---------------------------------------------------------------- title
sl=prs.slides.add_slide(BL)
rect(sl,0,0,SW,SH,NAVY); rect(sl,0,5.0,SW,0.06,TEAL)
sl.shapes.add_picture(LOGO,Inches(0.7),Inches(0.6),height=Inches(1.5))
tb(sl,2.5,0.7,10,0.5,"National Institute of Technology Raipur",size=26,color=WHITE,bold=True,check=False)
tb(sl,2.5,1.28,10,0.4,"Department of Information Technology",size=18,color=RGBColor(0xC8,0xD6,0xE5),check=False)
tb(sl,0.7,2.4,12,1.9,"Decentralised Multispectral UAV Swarms for Search and Rescue",size=40,color=WHITE,bold=True,check=False)
tb(sl,0.7,3.95,12,0.9,"Early-fusion perception, delay-tolerant networking and energy-aware self-organisation",size=22,color=RGBColor(0x9F,0xD3,0xDC),check=False)
tb(sl,0.7,5.3,6.5,1.6,[("Presented by",dict(size=14,color=RGBColor(0x9F,0xD3,0xDC),bold=True)),"Devesh Agarwal (23118030)","Sankalp Mittal (23118089)","Naman Chaudhary (23118069)"],size=18,color=WHITE,space=3,check=False)
tb(sl,8.2,5.3,4.5,1.2,[("Guided by",dict(size=14,color=RGBColor(0x9F,0xD3,0xDC),bold=True)),"Dr. Rayanoothala Praneetha Sree","B.Tech, Information Technology, Semester 7"],size=18,color=WHITE,space=3,check=False)
sl.notes_slide.notes_text_frame.text="Introduce the team and the guide. One sentence: we built and evaluated a UAV swarm that finds people in disaster areas, even when the radio network is mostly down and a UAV may be lost."

# 2 motivation
sl=slide("Why a UAV swarm for search and rescue?","The first hours decide who is found alive. A swarm covers more area faster, but three practical problems arise together. Perception, communication and control depend on each other, so we study them together.")
tb(sl,0.5,1.3,12.3,0.8,"The first hours after an earthquake or flood decide who is found alive. A swarm of small UAVs covers a wide area much faster than ground teams, but three practical problems arise together.",size=18)
cw=3.95
card(sl,0.5,2.35,cw,3.4,"1  Perception","Visible cameras fail in shadow, dusk and smoke. Thermal cameras show warm people, but struggle when people and background have nearly the same temperature.",size=17)
card(sl,0.5+cw+0.2,2.35,cw,3.4,"2  Communication","Over multi-kilometre areas the UAVs are mostly out of radio range. A design that assumes a connected network would deliver almost nothing.",hc=ORANGE,size=17)
card(sl,0.5+2*(cw+0.2),2.35,cw,3.4,"3  Coordination","No central planner is available, and UAVs have different batteries. A UAV can be lost unnoticed, because in flight silence is normal.",hc=NAVY,size=17)
rect(sl,0.5,6.0,12.3,0.8,NAVY)
tb(sl,0.7,6.05,11.9,0.7,"Problem: design a swarm that detects people, delivers alerts over an intermittent network, and re-organises itself without a central planner.",size=17,color=WHITE,bold=True,anchor=MSO_ANCHOR.MIDDLE,check=False)
# 3 objectives
sl=slide("Objectives and contributions","Four objectives, matched by four contributions.")
card(sl,0.5,1.4,6.0,5.3,"Objectives",["Build a 4-channel RGB + thermal early-fusion person detector and test it by day, night and thermal washout","Design delay-tolerant alert delivery with per-recipient buffers and store-carry-forward relaying","Design decentralised coordination that works on stale local views","Evaluate every component with ablations and baselines, with confidence intervals"],size=19)
card(sl,6.8,1.4,6.0,5.3,"Contributions",["Integrated decentralised architecture: perception + mesh + control on every UAV","EW-CVT partition with dual-threshold hysteresis, claim-and-yield assignment and lease-based failure detection","Per-recipient QoS-1 buffers with epidemic store-carry-forward relaying under a physical radio model","1,620 paired simulated missions, with ablation and comparison with spray-and-wait, buffering only and a static partition"],hc=ORANGE,size=19)
# 4 related work
sl=slide("Related work and the research gap","Each family is strong in its own area, but assumes either a connected network or announced failures.")
rows=[["Family","Strength","Limitation for a sparse swarm"],
 ["Consensus","Provable agreement","Needs repeated exchanges over connected links"],
 ["Voronoi coverage control","Smooth, well-studied partition","Assumes agents see each other; ignores energy unless weighted"],
 ["Unreliable failure detectors","Formal treatment of suspicion","Rely on heartbeats, which fails when silence is normal"],
 ["Delay-tolerant routing","Works without end-to-end paths","Usually studied apart from control"],
 ["Multispectral detection","Better detection in poor light","Seldom evaluated inside a mission with a radio model"]]
table(sl,0.5,1.4,12.3,rows,[3.2,3.3,5.8],size=14,rowh=0.5)
rect(sl,0.5,5.0,12.3,1.5,LIGHT); rect(sl,0.5,5.0,0.08,1.5,ORANGE)
tb(sl,0.75,5.07,11.9,1.4,[("Research gap",dict(bold=True,color=NAVY,size=18)),"A swarm that perceives with fused RGB + thermal frames, delivers alerts over a mostly disconnected network, and re-organises from stale local views, with a failure detector that does not mistake silence for failure."],size=16)
# 5 architecture
sl=slide("System architecture","Every UAV runs the same three components. The ground station is a passive sink.")
pic(sl,DG("architecture.png"),0.5,1.35,12.3,3.9)
tb(sl,0.5,5.4,4.0,1.5,[("Perception",dict(bold=True,color=NAVY,size=17)),"4-channel RGB + thermal YOLO11s turns frames into victim alerts"],size=15)
tb(sl,4.7,5.4,4.0,1.5,[("Mesh communication",dict(bold=True,color=NAVY,size=17)),"Lossy radio, per-recipient buffers, store-carry-forward, status beacons every 5 s"],size=15)
tb(sl,8.9,5.4,4.0,1.5,[("Swarm control",dict(bold=True,color=NAVY,size=17)),"Own view of peers, EW-CVT weights, hysteresis, claims, lease failover"],size=15)
# 6 perception
sl=slide("Perception: RGB + thermal early fusion","Early fusion stacks the planes into one four-channel input, so it adds almost no computation.")
pic(sl,DG("uav_pipeline.png"),0.4,1.3,12.5,3.7)
tb(sl,0.5,5.15,6.0,1.8,["YOLO11s, 1280 px input, one class (person)","Trained on the NII-CU multispectral aerial dataset","Thermal kernel initialised from the pretrained red kernel; no colour jitter"],size=15,bullet=True)
tb(sl,6.8,5.15,6.0,1.8,["Cheap enough for onboard use: only the first convolution changes","Georeferencing is sector-based","Alerts are de-duplicated locally and swarm-wide"],size=15,bullet=True)
# 7 DTN
sl=slide("Delay-tolerant alert delivery","First direct attempt succeeds only 3 to 6 percent of the time; buffers and epidemic relaying deliver the rest.")
pic(sl,DG("packet_delivery.png"),5.9,1.15,7.2,5.9)
tb(sl,0.5,1.35,5.4,5.6,[("Radio model",dict(bold=True,color=NAVY,size=18)),"Log-distance path loss (exponent 2.5), 4 dB shadowing, 15 dB obstruction loss","PER = 0.5 at about 520 m (2.4 GHz, 33 dBm)",("Alert handling",dict(bold=True,color=NAVY,size=18)),"One direct attempt to every UAV and the GCS; failures go to a per-recipient buffer","Buffers flush when link PER < 0.2, usually at return to base","Epidemic forwarding: receivers carry copies onward",("Status beacons",dict(bold=True,color=NAVY,size=18)),"Every 5 s, single-hop, not buffered"],size=15,space=5)
# 8 EW-CVT
sl=slide("Energy-weighted territory partitioning (EW-CVT)","Weight w = (B/Bmax)^alpha. Larger alpha shrinks weak UAVs' territory: more reserve, longer mission.")
rect(sl,0.5,1.4,5.9,1.7,LIGHT); rect(sl,0.5,1.4,0.08,1.7,TEAL)
tb(sl,0.75,1.45,5.5,1.6,[("Weight of UAV i",dict(bold=True,color=NAVY,size=15)),("w_i = (B_i / B_max) ^ α",dict(size=22,color=NAVY,bold=True)),("Preferred owner of sector s",dict(bold=True,color=NAVY,size=15)),("d(s,i) = ‖c_s − g_i‖² / max(0.01, w_i)",dict(size=18,color=NAVY,bold=True))],size=15,space=2,check=False)
tb(sl,0.5,3.35,5.9,3.6,["α = 0: plain Voronoi; larger α shrinks low-battery territories","Launch partition: converged CVT (15 Lloyd iterations)","α is a dial between speed and energy safety, not a free improvement"],size=16,bullet=True)
pic(sl,RF("alpha_sweep.png"),6.6,1.35,6.3,3.0)
rows=[["α","Min battery %","Mission time (s)","Aborts"],["0","15.6","377","0.95"],["1","16.7","358","0.90"],["2","18.3","427","0.45"],["3","20.3","488","0.30"]]
table(sl,6.9,4.6,5.7,rows,[1.0,1.6,1.8,1.3],size=13,rowh=0.4)
# 9 control loop
sl=slide("Decentralised control loop","Runs on every UAV every 5 seconds, from that UAV's own view only.")
pic(sl,DG("control_loop.png"),0.9,1.25,11.5,4.95)
tb(sl,0.5,6.25,12.3,0.8,"Claims use only committed values, so a locked gate means few ownership flips and little re-routing.",size=15)
# 10 hysteresis
sl=slide("Hysteresis gate and claim-and-yield","Commits fall about tenfold with hysteresis in the per-tick test.")
pic(sl,DG("hysteresis_gate.png"),0.4,1.25,12.5,3.55)
tb(sl,0.5,4.95,6.0,2.0,[("Dual-threshold hysteresis",dict(bold=True,color=NAVY,size=17)),"Commit only if battery fell ≥ 2% of Bmax AND the centroid moved ≥ 5 m, or the believed live set changed","Per-tick test, σ = 2%: commits 296 → 31 per mission"],size=14,space=4)
tb(sl,6.8,4.95,6.0,2.0,[("Claim-and-yield",dict(bold=True,color=NAVY,size=17)),"Claim a sector if you are its preferred owner and nobody holds a valid claim","Keep claims unless a better claim arrives; then yield"],size=14,space=4)
# 11 failover
sl=slide("Lease-based failure detection and failover","Silence is normal in flight, so each peer advertises its expected return; overdue by the slack means suspected.")
pic(sl,DG("failover_sequence.png"),0.4,1.25,7.6,3.1)
tb(sl,0.5,4.5,7.5,2.5,["Sortie lease: each peer advertises its expected return time","Suspected after 60 s past the lease (default); withdrawn if the peer is heard again","Only UAVs at base take over released work","UAV aborts at 15% battery; lost at 0%"],size=14,bullet=True,space=4)
rows=[["Slack (s)","Failover (s)","Wrong suspicions"],["20","192","11.2 of 15.6"],["60 (default)","231","8.3 of 12.6"],["120","293","3.6 of 8.0"],["240","411","0.4 of 4.7"]]
table(sl,8.3,1.6,4.6,rows,[1.4,1.4,1.8],size=13,rowh=0.42,hl=[2])
pic(sl,RF("lease_slack_tradeoff.png"),8.3,3.85,4.6,2.9)
# 12 setup
sl=slide("Experimental setup","Kinematic simulator with real multispectral frames; paired seeds; 95 percent confidence intervals.")
card(sl,0.5,1.4,6.0,5.4,"Simulation",["6 UAVs, 5 × 5 km arena, 25 sectors; each sector shows one NII-CU frame","Transit 50 m/s, search 32 m/s; launch batteries 20 to 100%","Loss scenario: UAV 2 fails silently at t = 80 s","Arenas of 1.5, 3 and 5 km; swarms of 2 to 12 UAVs","1,620 paired missions; mission cap 1,500 s"],size=17)
rows=[["Question","Proposed","Baselines"],["Forwarding","Epidemic","Spray-and-wait (L = 3); buffer only"],["Allocation","EW-CVT","Static partition"],["Detector","Fused RGB + thermal","Thermal only (RGB masked); Speth et al. 2022"]]
table(sl,6.8,1.5,6.0,rows,[1.4,1.8,2.8],size=13,rowh=0.62)
tb(sl,6.8,4.2,6.0,2.6,[("Detector conditions",dict(bold=True,color=NAVY,size=16)),"Day: frames unchanged","Night: RGB × 0.12 plus noise","Thermal washout: thermal contrast cut to 25% plus noise"],size=14,space=3)
# 13 detection
sl=slide("Results: detection","Fused model reaches AP50 99.8 by day; washout is the hardest case.")
rows=[["Input","Day AP50","Night AP50","Washout AP50","Washout recall"],["Fused RGB + thermal (proposed)","99.8","94.3","61.8","0.386"],["Thermal only (RGB masked)","89.0","89.0","0.0","0.000"]]
table(sl,0.5,1.4,7.4,rows,[3.1,1.0,1.1,1.2,1.0],size=13,rowh=0.45,hl=[1])
rows=[["Model (Speth et al. 2022 vs ours)","AP50","AP75"],["YOLOv3, RGB","92.4","44.5"],["YOLOv3, thermal (FIR)","97.5","72.7"],["YOLOv3, RGB + FIR ensemble","97.3","54.7"],["YOLOv3, 4-channel","97.9","76.9"],["YOLO11s, 4-channel (proposed)","99.8","85.8"]]
table(sl,0.5,3.0,7.4,rows,[4.4,1.5,1.5],size=13,rowh=0.42,hl=[5])
pic(sl,RF("detection_ap50_by_modality_and_condition.png"),8.2,1.35,4.7,2.5)
stat(sl,8.4,4.2,2.1,"99.8","AP50, daylight"); stat(sl,10.7,4.2,2.1,"94.3","AP50, night",col=ORANGE)
tb(sl,8.2,5.75,4.7,1.2,"Indicative only: 150 of 485 frames, newer architecture.",size=12)
# 14 network
sl=slide("Results: delay-tolerant networking","Buffering is the largest effect; epidemic forwarding is fastest at the price of more copies.")
stat(sl,0.5,1.3,3.9,"3.4% → 98.0%","victims known to the operator, 5 km: without vs. with DTN buffer")
stat(sl,4.7,1.3,3.9,"−7.6 s","alert latency vs. spray-and-wait at 3 km",col=ORANGE)
stat(sl,8.9,1.3,3.9,"+1.9","copies per alert vs. spray-and-wait",col=NAVY)
pic(sl,RF("network_ablation.png"),0.5,2.85,5.6,3.3); pic(sl,RF("forwarding_tradeoff.png"),6.3,2.85,6.6,3.3)
tb(sl,0.5,6.25,12.3,0.7,"At 3 km: epidemic 41.0 s / 4.30 copies; spray-and-wait 48.6 s / 2.37; buffer only 59.2 s / 1.00.",size=14)
# 15 coordination
sl=slide("Results: coordination and failure recovery","Failover drives the coverage gain after a loss; the price is a longer mission.")
stat(sl,0.5,1.3,3.9,"98.4% vs 87.4%","coverage after a UAV loss: with vs. without failover")
stat(sl,4.7,1.3,3.9,"231 s","mean failover latency at 5 km",col=ORANGE)
stat(sl,8.9,1.3,3.9,"0.00","duplicate scans, EW-CVT, no loss",col=NAVY)
pic(sl,RF("coverage_over_time.png"),0.5,2.85,5.6,3.3)
rows=[["Policy","Cover. nominal","Cover. UAV lost","Time lost (s)"],["EW-CVT (proposed)","100.0","98.4","554"],["Static partition","100.0","87.6","353"]]
table(sl,6.5,3.1,6.3,rows,[2.4,1.3,1.4,1.2],size=13,rowh=0.5,hl=[1])
tb(sl,6.5,4.8,6.3,1.5,["Without a loss all policies reach full coverage","EW-CVT has the highest minimum battery (18.8% vs 17.9%)"],size=14,bullet=True)
tb(sl,0.5,6.25,12.3,0.7,"We credit failover, not the weighting, with the coverage gain.",size=14)
# 16 conclusion
sl=slide("Conclusion, limitations and future work","All results come from simulation.")
card(sl,0.5,1.35,4.0,5.0,"Conclusions",["Buffering is the largest effect: 3.4% → 98.0% at 5 km","Failover recovers 11 points of coverage","Epidemic relaying is fastest, at the price of more copies","Decentralisation costs minutes of failover latency","Fused detector: AP50 99.8 by day, 94.3 at night"],size=16)
card(sl,4.7,1.35,4.0,5.0,"Limitations",["Simulation only; kinematic model, no wind","One static frame per sector; same-site train and validation","Modality ablation masks one plane of a fused network","Simplified decentralisation"],hc=ORANGE,size=16)
card(sl,8.9,1.35,3.9,5.0,"Future work",["Train separate RGB-only and thermal-only detectors","Third-party state in status messages","Camera, wind and energy models","ArduPilot + ns-3, then hardware"],hc=NAVY,size=16)
rect(sl,0.5,6.5,12.3,0.45,NAVY)
tb(sl,0.5,6.5,12.3,0.45,"Thank you. Questions?",size=18,color=WHITE,bold=True,align=PP_ALIGN.CENTER,anchor=MSO_ANCHOR.MIDDLE,check=False)
out=os.path.join(HERE,"FlyNetSim_Presentation_16slides_backup.pptx"); prs.save(out)
print("saved",out,len(prs.slides)); print("\n".join(warn) or "no overflow warnings")
