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
TOTAL=11; warn=[]

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

# 2 ---------------------------------------------------------------- problem
sl=slide("The problem: finding survivors with a UAV swarm","The first hours decide who is found alive. A swarm covers more area faster, but three problems arise together: seeing people in poor light, getting alerts out over a mostly disconnected network, and coordinating without a central planner while UAVs can be lost silently. Existing coordination methods assume a connected network or announced failures, and perception, networking and control are rarely evaluated together. That is the gap this project fills.")
cw=3.95
card(sl,0.5,1.5,cw,3.5,"Perception","Visible cameras fail in shadow and smoke; thermal cameras struggle when people and background have the same temperature.")
card(sl,0.5+cw+0.2,1.5,cw,3.5,"Communication","Over multi-km areas the UAVs are mostly out of radio range, so alerts cannot rely on a connected network.",hc=ORANGE)
card(sl,0.5+2*(cw+0.2),1.5,cw,3.5,"Coordination","No central planner, different batteries, and a lost UAV is invisible: in flight, silence is normal.",hc=NAVY)
rect(sl,0.5,5.35,12.3,1.35,NAVY)
tb(sl,0.7,5.4,11.9,1.25,[("Our approach",dict(bold=True,size=18,color=RGBColor(0x9F,0xD3,0xDC))),"Every UAV runs perception, mesh communication and control on its own view of the swarm, with no central planner, and the three parts are evaluated together over 1,620 simulated missions."],size=18,color=WHITE,anchor=MSO_ANCHOR.MIDDLE,check=False)

# 3 ---------------------------------------------------------------- architecture
sl=slide("System architecture","Every UAV runs the same three components. The ground station is a passive sink. Perception: 4-channel RGB+thermal YOLO11s. Mesh: lossy radio, per-recipient buffers, store-carry-forward, status beacons every 5 s. Control: own view of peers, EW-CVT weights, hysteresis, claims, lease failover.")
pic(sl,DG("architecture.png"),0.5,1.35,12.3,4.0)
tb(sl,0.5,5.5,4.0,1.4,[("Perception",dict(bold=True,color=NAVY,size=18)),"Fused RGB + thermal detection turns frames into alerts"],size=16)
tb(sl,4.7,5.5,4.0,1.4,[("Mesh communication",dict(bold=True,color=NAVY,size=18)),"Buffered, store-carry-forward alert delivery"],size=16)
tb(sl,8.9,5.5,4.0,1.4,[("Swarm control",dict(bold=True,color=NAVY,size=18)),"Energy-aware sectors, failure detection, failover"],size=16)

# 4 ---------------------------------------------------------------- perception
sl=slide("Perception: RGB + thermal early fusion","The visible and thermal frames are stacked into one four-channel tensor, so only the first convolution changes and the cost is almost nil. The thermal kernel is initialised from the pretrained red kernel. Night: RGB x 0.12 plus noise. Washout: thermal contrast cut to 25 percent plus noise. Both are synthetic degradations of daytime frames. RGB-only scores zero because the network was never trained without the thermal plane. Comparison with Speth et al. is indicative only: 150 of 485 frames, newer architecture.")
tb(sl,0.5,1.4,5.4,5.4,["YOLO11s, 1280 px, one class (person)","Trained on the NII-CU multispectral aerial dataset","Visible + thermal stacked into 4 channels: cheap enough for onboard use","Box centre is mapped into the sector bounds (sector-based georeferencing)"],size=18,bullet=True,space=12)
rows=[["Input","Day","Night","Washout"],["Fused (proposed)","99.8","94.3","61.8"],["Thermal only (RGB masked)","89.0","89.0","0.0"]]
tb(sl,6.3,1.4,6.5,0.4,"AP50 under degraded conditions",size=16,color=NAVY,bold=True,check=False)
table(sl,6.3,1.85,6.5,rows,[2.9,1.2,1.2,1.2],size=15,rowh=0.5,hl=[1])
rows=[["Daytime AP50 / AP75","AP50","AP75"],["YOLOv3 4-channel (Speth et al. 2022)","97.9","76.9"],["YOLO11s 4-channel (proposed)","99.8","85.8"]]
tb(sl,6.3,3.75,6.5,0.4,"Comparison with the base paper",size=16,color=NAVY,bold=True,check=False)
table(sl,6.3,4.2,6.5,rows,[3.9,1.3,1.3],size=15,rowh=0.5,hl=[2])
tb(sl,6.3,5.85,6.5,0.9,"Indicative only: 150 of 485 frames and a newer architecture. Washout is the hardest case (recall 0.39).",size=13)

# 5 ---------------------------------------------------------------- DTN
sl=slide("Delay-tolerant alert delivery","In a multi-km arena the first direct attempt succeeds only 3 to 6 percent of the time. Alerts are kept in per-recipient QoS-1 buffers and flushed when the link PER drops below 0.2, usually at return to base. Any UAV that received an alert is a carrier, so an alert survives the loss of its finder. Radio: log-distance path loss, exponent 2.5, 4 dB shadowing, PER 0.5 at about 520 m.")
pic(sl,DG("packet_delivery.png"),5.9,1.15,7.2,5.9)
tb(sl,0.5,1.5,5.2,5.2,[("Direct attempt first",dict(bold=True,color=NAVY,size=20)),"One attempt to every UAV and the ground station; the swarm is mostly out of range, so most fail",
 ("Buffer, then carry",dict(bold=True,color=NAVY,size=20)),"Failed copies wait in per-recipient buffers and are handed over on contact, usually at base",
 ("Epidemic relaying",dict(bold=True,color=NAVY,size=20)),"Receivers carry copies onward, so alerts survive the loss of their finder"],size=17,space=8)

# 6 ---------------------------------------------------------------- coordination
sl=slide("Energy-aware coordination without a planner","Weight w = (B/Bmax)^alpha. alpha = 0 is plain Voronoi; larger alpha shrinks the territory of weak UAVs, raising the minimum battery from 15.6 to 20.3 percent at alpha 0 to 3 but lengthening the mission from 377 to 488 s. Hysteresis: commit only if battery fell at least 2 percent of Bmax and the centroid moved at least 5 m, or the believed live set changed. In the per-tick re-planning test (sigma 2 percent) commits fall 296 to 31 and sector flips 13.5 to 2.5; in the full decentralised system the effect is small because claims are already sticky. Claim-and-yield: keep claims unless a better claim (smaller d) arrives.")
rect(sl,0.5,1.45,12.3,1.7,LIGHT); rect(sl,0.5,1.45,0.08,1.7,TEAL)
tb(sl,0.8,1.55,11.8,1.5,[("Energy-weighted centroidal Voronoi tessellation (EW-CVT)",dict(bold=True,color=NAVY,size=17)),("w_i = (B_i / B_max)^α        d(s,i) = ‖c_s − g_i‖² / max(0.01, w_i)",dict(size=24,color=NAVY,bold=True)),("Each sector goes to the UAV with the smallest weighted distance: weak batteries get smaller territories",dict(size=15))],size=15,space=4,check=False)
cw=3.95
card(sl,0.5,3.45,cw,3.3,"Energy weighting","Larger α: more reserve (min battery 15.6 → 20.3%) but a longer mission (377 → 488 s)",size=17)
card(sl,0.5+cw+0.2,3.45,cw,3.3,"Hysteresis","Commit a new partition only on a real battery and centroid change: commits fall 296 → 31 per mission",hc=ORANGE,size=17)
card(sl,0.5+2*(cw+0.2),3.45,cw,3.3,"Claim and yield","A UAV keeps its claims unless a better claim arrives, so sectors rarely flip between UAVs",hc=NAVY,size=17)

# 7 ---------------------------------------------------------------- failover
sl=slide("Failure detection and failover","In flight silence tells nothing, because a quiet peer may be out of range or landed. So each peer advertises when its route should bring it home; if it is still missing slack seconds later (60 s by default) it is suspected and its claims are released. Released work is taken only by UAVs at base. Slack trades speed against false alarms: 20/60/120/240 s gives failover 192/231/293/411 s and wrong suspicions 11.2 of 15.6 down to 0.4 of 4.7.")
pic(sl,DG("failover_sequence.png"),0.4,1.3,12.5,3.7)
tb(sl,0.5,5.2,6.2,1.7,["Silence is normal in flight, so a quiet peer is not a failed peer","Each peer advertises its expected return; overdue by the slack means suspected","Only UAVs at base take over released work"],size=16,bullet=True,space=6)
rows=[["Slack (s)","Failover (s)","Wrong suspicions"],["20","192","11.2 of 15.6"],["60 (default)","231","8.3 of 12.6"],["240","411","0.4 of 4.7"]]
table(sl,7.2,5.25,5.6,rows,[1.6,1.6,2.4],size=14,rowh=0.42,hl=[2])

# 8 ---------------------------------------------------------------- setup
sl=slide("Experimental setup","Simulation: a kinematic mission simulator that runs the full perception, mesh and control logic on real multispectral frames. A seed fixes the frame in each sector and every launch battery, so each variant sees identical worlds. Results are paired differences with 95 percent confidence intervals. Transit 50 m/s, search 32 m/s; launch batteries 20 to 100 percent; battery sensor noise 1.5 points; UAV 2 fails silently at t = 80 s in the loss scenario.")
card(sl,0.5,1.5,6.0,5.2,"Simulation",["6 UAVs over a 5 × 5 km arena, 25 sectors, real NII-CU frames","UAV 2 fails silently at t = 80 s in the loss scenario","Arenas of 1.5, 3 and 5 km; swarms of 2 to 12 UAVs","1,620 paired missions; paired differences with 95% confidence intervals"],size=18)
rows=[["Question","Proposed","Compared with"],["Alert forwarding","Epidemic","Spray-and-wait, buffer only"],["Sector allocation","EW-CVT with failover","Static partition"],["Detection","Fused RGB + thermal","Thermal only; Speth et al."]]
table(sl,6.9,1.6,5.9,rows,[1.9,1.9,2.1],size=14,rowh=0.75)
tb(sl,6.9,4.8,5.9,1.8,"Components are also removed one at a time (buffer, forwarding, failover, hysteresis, energy weighting) to measure their individual effect.",size=16)

# 9 ---------------------------------------------------------------- results network
sl=slide("Results: alert delivery","Without the buffer the operator learns of only about 3 percent of victims at 5 km; with it 98 percent. Epidemic forwarding has the lowest alert latency in every scenario but keeps the most copies. At 3 km its latency is 7.6 +/- 1.7 s below spray-and-wait and about 18 s below buffer only, with about 1.9 more copies than spray-and-wait. With a UAV lost the operator recall is 0.978 (epidemic), 0.967 (spray-and-wait) and 0.958 (buffer only).")
stat(sl,0.5,1.4,3.9,"3.4% → 98.0%","victims known to the operator at 5 km, without vs. with the buffer")
stat(sl,4.7,1.4,3.9,"−7.6 s","alert latency vs. spray-and-wait at 3 km",col=ORANGE)
stat(sl,8.9,1.4,3.9,"+1.9 copies","per alert vs. spray-and-wait: the price of epidemic",col=NAVY)
pic(sl,RF("forwarding_tradeoff.png"),1.2,3.05,10.9,3.75)

# 10 ---------------------------------------------------------------- results coordination
sl=slide("Results: coordination and failure recovery","Failover drives the coverage gain after a loss: 98.4 percent against 87.6 percent for the static partition (87.4 percent with failover removed from the full system). The price is a longer mission: 554 s against 353 s, because survivors take over the lost work. The swarm cannot know of the loss until the lost UAV is overdue at base, so failover takes 231 s at 5 km, 143 s at 3 km and 102 s at 1.5 km. EW-CVT has no duplicate scans in the nominal case.")
stat(sl,0.5,1.4,3.9,"98.4% vs 87.4%","coverage after a UAV loss, with vs. without failover")
stat(sl,4.7,1.4,3.9,"231 s","mean failover latency at 5 km (143 s at 3 km)",col=ORANGE)
stat(sl,8.9,1.4,3.9,"554 s vs 353 s","mission time with a loss: the price of recovery",col=NAVY)
pic(sl,RF("coverage_over_time.png"),0.5,3.05,6.6,3.75)
tb(sl,7.4,3.2,5.4,3.5,["With failover the swarm recovers nearly all the lost area, but only after the loss is noticed","Without a loss all variants reach full coverage in about 350 s","Decentralisation costs minutes of failover latency"],size=17,bullet=True,space=12)

# 11 ---------------------------------------------------------------- conclusion
sl=slide("Conclusion and future work","All results come from simulation, and the unfavourable results are reported together with the favourable ones. Limitations: kinematic simulator, one static frame per sector, a modality ablation that masks one plane of a fused network, and simplified decentralisation (common launch, single-hop status messages). Thank the audience and invite questions.")
card(sl,0.5,1.4,6.0,4.6,"Conclusions",["Buffering is the largest effect: operator knowledge 3.4% → 98.0%","Failover recovers 11 points of coverage after a UAV loss","Epidemic relaying is fastest, at the price of more copies","Decentralisation costs minutes of failover latency"],size=18)
card(sl,6.8,1.4,6.0,4.6,"Limitations and future work",["Simulation only: next, camera and wind models and ArduPilot + ns-3 co-simulation","Train separate RGB-only and thermal-only detectors","Status messages carrying third-party state for earlier failure detection"],hc=ORANGE,size=18)
rect(sl,0.5,6.25,12.3,0.6,NAVY)
tb(sl,0.5,6.25,12.3,0.6,"Thank you. Questions?",size=20,color=WHITE,bold=True,align=PP_ALIGN.CENTER,anchor=MSO_ANCHOR.MIDDLE,check=False)

out=os.path.join(HERE,"FlyNetSim_Presentation.pptx"); prs.save(out)
print("saved",out,"slides",len(prs.slides)); print("\n".join(warn) or "no overflow warnings")
