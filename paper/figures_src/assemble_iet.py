import re, os
body=open("/tmp/iet_body.tex").read()
TITLE="Decentralised Multispectral UAV Swarms for Search and Rescue: Early-Fusion Perception, Delay-Tolerant Networking and Energy-Aware Self-Organisation"
ABSTRACT=("Searching a large disaster area with a UAV swarm requires reliable person detection in poor light, continued operation after the loss of an aircraft, "
 "and delivery of findings over radio links that are mostly unavailable. This paper presents a decentralised search-and-rescue system for such conditions that integrates "
 "a four-channel RGB and thermal early-fusion YOLO11 detector, a delay-tolerant mesh with store-carry-forward alert relaying, and a coordination layer that combines "
 "energy-weighted centroidal Voronoi tessellation, dual-threshold hysteresis, sector claiming and lease-based failure detection. Every UAV plans from its own, possibly outdated, "
 "view of the swarm. We evaluate the system in a kinematic simulator that uses real multispectral frames, over 1{,}620 paired missions. "
 "Buffering raises the share of victims known to the operator from 3.4\\% to 98\\% in a 5\\,km arena, and failover recovers 11 points of coverage after a UAV is lost. "
 "Epidemic relaying delivers alerts 7.6\\,s sooner than spray-and-wait at 3\\,km, but it keeps about two more copies of each alert. After a loss, the survivors need about 230\\,s "
 "to detect it, because no UAV can know of the loss before the missing one is overdue at base. All results come from simulation.")
print("abstract words:",len(re.sub(r"\\[a-z]+|[{}]","",ABSTRACT).split()))
KEYWORDS="UAV SWARM, SEARCH AND RESCUE, MULTISPECTRAL FUSION, DELAY-TOLERANT NETWORKING, DECENTRALISED COVERAGE CONTROL"

REF={
"hwang2015kaist":"Hwang, S., Park, J., Kim, N., \\textit{et al.}: `Multispectral pedestrian detection: benchmark dataset and baseline'. Proc. IEEE Conf. Computer Vision and Pattern Recognition, Boston, USA, June 2015",
"liu2016multispectral":"Liu, J., Zhang, S., Wang, S., \\textit{et al.}: `Multispectral deep neural networks for pedestrian detection'. Proc. British Machine Vision Conf., York, UK, September 2016",
"zhang2019weakly":"Zhang, L., Zhu, X., Chen, X., \\textit{et al.}: `Weakly aligned cross-modal learning for multispectral pedestrian detection'. Proc. IEEE/CVF Int. Conf. Computer Vision, Seoul, South Korea, October 2019",
"redmon2016yolo":"Redmon, J., Divvala, S., Girshick, R., \\textit{et al.}: `You only look once: unified, real-time object detection'. Proc. IEEE Conf. Computer Vision and Pattern Recognition, Las Vegas, USA, June 2016",
"jocher2024yolo11":"Jocher, G., Qiu, J.: `Ultralytics YOLO11', 2024, \\nolinkurl{https://github.com/ultralytics/ultralytics}",
"speth2022":"Speth, S., Gon\\c{c}alves, A., Rigault, B., \\textit{et al.}: `Deep learning with RGB and thermal images onboard a drone for monitoring operations', \\textit{J. Field Robot.}, 2022, \\textbf{39}, (6), pp. 840--868 (dataset: \\nolinkurl{https://www.nii-cu-multispectral.org})",
"lloyd1982":"Lloyd, S.P.: `Least squares quantization in PCM', \\textit{IEEE Trans. Inf. Theory}, 1982, \\textbf{28}, (2), pp. 129--137",
"du1999cvt":"Du, Q., Faber, V., Gunzburger, M.: `Centroidal Voronoi tessellations: applications and algorithms', \\textit{SIAM Rev.}, 1999, \\textbf{41}, (4), pp. 637--676",
"cortes2004coverage":"Cort\\'es, J., Mart\\'inez, S., Karatas, T., \\textit{et al.}: `Coverage control for mobile sensing networks', \\textit{IEEE Trans. Robot. Autom.}, 2004, \\textbf{20}, (2), pp. 243--255",
"cortes2005limited":"Cort\\'es, J., Mart\\'inez, S., Bullo, F.: `Spatially-distributed coverage optimization and control with limited-range interactions', \\textit{ESAIM Control Optim. Calc. Var.}, 2005, \\textbf{11}, (4), pp. 691--719",
"aurenhammer1987power":"Aurenhammer, F.: `Power diagrams: properties, algorithms and applications', \\textit{SIAM J. Comput.}, 1987, \\textbf{16}, (1), pp. 78--96",
"fall2003dtn":"Fall, K.: `A delay-tolerant network architecture for challenged internets'. Proc. ACM SIGCOMM, Karlsruhe, Germany, August 2003",
"vahdat2000epidemic":"Vahdat, A., Becker, D.: `Epidemic routing for partially connected ad hoc networks'. Technical Report CS-2000-06, Duke University, 2000",
"spyropoulos2005spray":"Spyropoulos, T., Psounis, K., Raghavendra, C.S.: `Spray and wait: an efficient routing scheme for intermittently connected mobile networks'. Proc. ACM SIGCOMM Workshop on Delay-Tolerant Networking, Philadelphia, USA, August 2005",
"kosaka2023dmlt":"Kosaka, K., Noda, Y., Yokotani, T., \\textit{et al.}: `Implementation and evaluation of the control mechanism among distributed MQTT brokers', \\textit{IEEE Access}, 2023, \\textbf{11}, doi: 10.1109/ACCESS.2023.3335273",
"baidya2018flynetsim":"Baidya, S., Shaikh, Z., Levorato, M.: `FlyNetSim: an open source synchronized UAV network simulator based on ns-3 and Ardupilot'. Proc. ACM Int. Conf. Modeling, Analysis and Simulation of Wireless and Mobile Systems, Montreal, Canada, October 2018, pp. 37--45",
"rappaport2002wireless":"Rappaport, T.S.: `Wireless communications: principles and practice' (Prentice Hall, 2002, 2nd edn.)",
"goodrich2008":"Goodrich, M.A., Morse, B.S., Gerhardt, D., \\textit{et al.}: `Supporting wilderness search and rescue using a camera-equipped mini UAV', \\textit{J. Field Robot.}, 2008, \\textbf{25}, (1--2), pp. 89--110",
"burgard2005":"Burgard, W., Moors, M., Stachniss, C., \\textit{et al.}: `Coordinated multi-robot exploration', \\textit{IEEE Trans. Robot.}, 2005, \\textbf{21}, (3), pp. 376--386",
"gerkey2004":"Gerkey, B.P., Matari\\'c, M.J.: `A formal analysis and taxonomy of task allocation in multi-robot systems', \\textit{Int. J. Robot. Res.}, 2004, \\textbf{23}, (9), pp. 939--954",
"olfatisaber2007":"Olfati-Saber, R., Fax, J.A., Murray, R.M.: `Consensus and cooperation in networked multi-agent systems', \\textit{Proc. IEEE}, 2007, \\textbf{95}, (1), pp. 215--233",
"bekmezci2013":"Bekmezci, \\.I., Sahingoz, O.K., Temel, \\c{S}.: `Flying ad-hoc networks (FANETs): a survey', \\textit{Ad Hoc Netw.}, 2013, \\textbf{11}, (3), pp. 1254--1270",
"zeng2016":"Zeng, Y., Zhang, R., Lim, T.J.: `Wireless communications with unmanned aerial vehicles: opportunities and challenges', \\textit{IEEE Commun. Mag.}, 2016, \\textbf{54}, (5), pp. 36--42",
"alhourani2014":"Al-Hourani, A., Kandeepan, S., Lardner, S.: `Optimal LAP altitude for maximum coverage', \\textit{IEEE Wirel. Commun. Lett.}, 2014, \\textbf{3}, (6), pp. 569--572",
"jia2021llvip":"Jia, X., Zhu, C., Li, M., \\textit{et al.}: `LLVIP: a visible-infrared paired dataset for low-light vision'. Proc. IEEE/CVF Int. Conf. Computer Vision Workshops, Montreal, Canada, October 2021",
"wang2023yolov7":"Wang, C.-Y., Bochkovskiy, A., Liao, H.-Y.M.: `YOLOv7: trainable bag-of-freebies sets new state-of-the-art for real-time object detectors'. Proc. IEEE/CVF Conf. Computer Vision and Pattern Recognition, Vancouver, Canada, June 2023, pp. 7464--7475",
"schwager2009":"Schwager, M., Rus, D., Slotine, J.-J.: `Decentralized, adaptive coverage control for networked robots', \\textit{Int. J. Robot. Res.}, 2009, \\textbf{28}, (3), pp. 357--375",
"demers1987":"Demers, A., Greene, D., Hauser, C., \\textit{et al.}: `Epidemic algorithms for replicated database maintenance'. Proc. ACM Symp. Principles of Distributed Computing, Vancouver, Canada, August 1987, pp. 1--12",
"chandra1996":"Chandra, T.D., Toueg, S.: `Unreliable failure detectors for reliable distributed systems', \\textit{J. ACM}, 1996, \\textbf{43}, (2), pp. 225--267",
"hayashibara2004":"Hayashibara, N., D\\'efago, X., Yared, R., \\textit{et al.}: `The $\\varphi$ accrual failure detector'. Proc. IEEE Symp. Reliable Distributed Systems, Florianopolis, Brazil, October 2004, pp. 66--78",
"gray1989":"Gray, C.G., Cheriton, D.R.: `Leases: an efficient fault-tolerant mechanism for distributed file cache consistency'. Proc. ACM Symp. Operating Systems Principles, Litchfield Park, USA, December 1989, pp. 202--210",
"kwok2007":"Kwok, A., Mart\\'inez, S.: `Energy-balancing cooperative strategies for sensor deployment'. Proc. IEEE Conf. Decision and Control, New Orleans, USA, December 2007, pp. 6136--6141",
"munir2024":"Munir, A., Dutta, A., Parasuraman, R.: `Energy-aware coverage planning for heterogeneous multi-robot system', arXiv:2411.02230, 2024",
"grontved2023":"Gr{\\o}ntved, K.A.R., Lundquist, U.P.S., Christensen, A.L.: `Decentralized multi-UAV trajectory task allocation in search and rescue applications'. Proc. IEEE Int. Conf. Advanced Robotics, Abu Dhabi, UAE, December 2023, pp. 35--41",
"giacomossi2026":"Giacomossi, L., \\textit{et al.}: `Market-based replanning for safety-critical UAV swarms in search and rescue missions', arXiv:2606.01970, 2026",
}
# conference venue/city details above were added for IET style; keep only those I'm confident about -> strip uncertain location/month strings
def simplify(t):
    return t
# citation order
order=[]
for m in re.finditer(r"\\cite\{([^}]*)\}",body):
    for k in m.group(1).split(","):
        k=k.strip()
        if k and k not in order: order.append(k)
missing=[k for k in order if k not in REF]; unused=[k for k in REF if k not in order]
print("cited",len(order),"missing",missing,"unused",unused)
bib="\\begin{thebibliography}{99}\n"+"\n".join("\\bibitem{%s} %s."%(k,REF[k]) for k in order)+"\n\\end{thebibliography}\n"
bib=re.sub(r"`","`",bib)
bib=bib.replace("`","\\textquoteleft{}").replace("'.","\\textquoteright{}.").replace("',","\\textquoteright{},")
bib=re.sub(r"\\textquoteright\{\}\s*\(", "\\\\textquoteright{} (", bib)
PRE=r"""% Decentralised multispectral UAV swarm for search and rescue -- IET manuscript template version.
% Build: cd paper && tectonic swarm_sar_paper.tex   (XeLaTeX; on Overleaf choose the XeLaTeX compiler)
% All numbers come from results/README.md (1,620 paired simulated missions).
\documentclass[10pt,a4paper,twocolumn]{article}
\usepackage[a4paper,left=1.5cm,right=1.5cm,top=2cm,bottom=2.2cm,columnsep=0.4cm]{geometry}
\usepackage{fontspec}
\IfFontExistsTF{TeX Gyre Termes}{\setmainfont{TeX Gyre Termes}}{\IfFontExistsTF{Nimbus Roman}{\setmainfont{Nimbus Roman}}{}}
\usepackage{amsmath,amssymb}
\usepackage[nocompress]{cite}
\usepackage{graphicx}
\usepackage{dblfloatfix}
\usepackage{booktabs}
\usepackage{xcolor}
\usepackage{url}
\usepackage{algorithm}
\usepackage{algorithmic}
\usepackage{titlesec}
\usepackage[font=normalsize,labelsep=space,skip=4pt,justification=justified,singlelinecheck=false]{caption}
\usepackage[colorlinks=true,linkcolor=blue!60!black,citecolor=blue!60!black,urlcolor=blue!60!black,breaklinks=true]{hyperref}
\graphicspath{{../results/figures/}{./figures/}{./}}
\captionsetup[figure]{name=Fig.}
\captionsetup[table]{name=Table}
\renewcommand{\dbltopfraction}{0.95}\renewcommand{\dblfloatpagefraction}{0.7}\setcounter{dbltopnumber}{4}\renewcommand{\topfraction}{0.9}\setcounter{topnumber}{3}
\setcounter{secnumdepth}{3}
\titleformat{\section}{\bfseries\fontsize{12}{14}\selectfont}{\thesection}{1.2em}{}
\titleformat{\subsection}{\itshape\normalsize}{\thesubsection}{0.5em}{}
\titleformat{\subsubsection}[runin]{\itshape\normalsize}{\thesubsubsection}{0.5em}{}[:\enspace]
\titlespacing*{\section}{0pt}{10pt plus 2pt}{4pt}
\titlespacing*{\subsection}{0pt}{6pt plus 2pt}{2pt}
\titlespacing*{\subsubsection}{0pt}{4pt}{0pt}
\renewcommand{\thetable}{\arabic{table}}
\setlength{\parindent}{0pt}\setlength{\parskip}{5pt plus 1pt}
\pagestyle{plain}
\makeatletter
\renewenvironment{thebibliography}[1]{\section{References}\list{\@biblabel{\@arabic\c@enumiv}}{\settowidth\labelwidth{\@biblabel{#1}}\leftmargin\labelwidth\advance\leftmargin\labelsep\setlength{\parsep}{0pt}\setlength{\itemsep}{2pt}\usecounter{enumiv}\let\p@enumiv\@empty\renewcommand\theenumiv{\@arabic\c@enumiv}}\sloppy\clubpenalty4000\@clubpenalty\clubpenalty\widowpenalty4000\sfcode`\.\@m}{\def\@noitemerr{\@latex@error{Empty thebibliography}\@ehc}\endlist}
\makeatother
\newcommand{\cli}[1]{\texttt{-{}-#1}}
\newcommand{\pmsd}[2]{#1{\small$\pm$#2}}
\setlength{\textfloatsep}{6pt plus 2pt minus 2pt}\setlength{\floatsep}{6pt plus 2pt minus 2pt}\setlength{\intextsep}{6pt plus 2pt minus 2pt}
\begin{document}
"""
import re as _re
_sent=_re.split(r"(?<=[a-z0-9\\}])\.\s+(?=[A-Z])",ABSTRACT)
_sent=[x if x.endswith(".") else x+"." for x in _sent]
_k=3
ABS_L=" ".join(_sent[:_k]); ABS_R=" ".join(_sent[_k:])
FRONT=(r"""\twocolumn[{%
\begin{center}
{\fontsize{18}{25}\selectfont\bfseries TITLE_HERE\par}\vspace{12pt}
\textbf{\textit{Naman Chaudhary}}$^{1}$, \textbf{\textit{Sankalp Mittal}}$^{2}$, \textbf{\textit{Garima Sinha}}$^{3}$, \textbf{\textit{Rayanoothala Praneetha Sree}}$^{4}$, \textbf{\textit{Devesh Agarwal}}$^{5*}$\\[4pt]
{\footnotesize\itshape $^{1}$Department of Information Technology, National Institute of Technology Raipur, Raipur, Chhattisgarh, India\\
$^{2}$Department of Information Technology, National Institute of Technology Raipur, Raipur, Chhattisgarh, India\\
$^{3}$Department of Information Technology, National Institute of Technology Raipur, Raipur, Chhattisgarh, India\\
$^{4}$Department of Information Technology, National Institute of Technology Raipur, Raipur, Chhattisgarh, India\\
$^{5}$Department of Information Technology, National Institute of Technology Raipur, Raipur, Chhattisgarh, India\\
$^{*}$Email: dagarwal030.btech2023@it.nitrr.ac.in}\\[8pt]
\end{center}
\small\noindent\textbf{Keywords}: KEYWORDS_HERE\par\vspace{8pt}
\noindent\textbf{\normalsize Abstract}\par\vspace{2pt}
\noindent ABS_FULL_HERE\par
\vspace{8pt}
}]
""").replace("TITLE_HERE",TITLE.upper().replace("&","\\&")).replace("KEYWORDS_HERE",KEYWORDS).replace("ABS_FULL_HERE",ABSTRACT)
out=PRE+FRONT+body.replace("\\section{Introduction}","\\section{Introduction}",1)+"\n"+bib+"\n\\end{document}\n"
open("swarm_sar_paper.tex","w").write(out)
