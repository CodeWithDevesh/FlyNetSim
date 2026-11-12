"""One-off converter: IEEEtran version (swarm_sar_paper_ieee.tex) -> IET manuscript-template version (swarm_sar_paper.tex)."""
import re, os
HERE=os.path.dirname(os.path.abspath(__file__)); P=os.path.join(HERE,"..")
s=open(os.path.join(P,"swarm_sar_paper_ieee.tex")).read()
body=s[s.index("\\maketitle")+len("\\maketitle"):s.index("\\begingroup\\scriptsize")]
# drop abstract + keywords (rewritten below)
body=body[body.index("\\end{IEEEkeywords}")+len("\\end{IEEEkeywords}"):]

# ---- structure: related-work run-ins -> numbered subsections; a)/b)/c) run-ins -> run-in third-level headings
body=re.sub(r"(?m)^\\textbf\{([^}]+?)\.\}\s*", lambda m: "\\subsection{%s}\n"%m.group(1), body)
body=re.sub(r"\\emph\{[a-e]\) ([^}]+?)\.\}\s*", lambda m: "\\subsubsection{%s}"%m.group(1), body)
body=body.replace("\\emph{Lease slack.} ","\\subsubsection{Lease slack}")
body=body.replace("\\emph{Lease slack.}","\\subsubsection{Lease slack}")

# ---- UK spelling in prose
uk=[("decentraliz","decentralis"),("Decentraliz","Decentralis"),("centraliz","centralis"),("organiz","organis"),("Organiz","Organis"),
    ("initializ","initialis"),("optimiz","optimis"),("normaliz","normalis"),("generaliz","generalis"),("minimiz","minimis"),("maximiz","maximis"),
    ("summariz","summaris"),("recogniz","recognis"),("utiliz","utilis"),("analyz","analys"),("emphasiz","emphasis"),("synchroniz","synchronis"),
    ("modeled","modelled"),("labeled","labelled"),("behavior","behaviour"),("Behavior","Behaviour"),("neighbor","neighbour"),
    ("favorable","favourable"),("catalog ","catalogue "),("localiz","localis"),("Localiz","Localis"),("georeferenc","georeferenc"),
    ("visualiz","visualis"),("prioritiz","prioritis"),("characteriz","characteris"),("parameteriz","parameteris"),("randomiz","randomis")]
for a,b in uk: body=body.replace(a,b)
body=re.sub(r"\bcenters?\b",lambda m:"centre"+("s" if m.group(0).endswith("s") else ""),body)
body=re.sub(r"\bcentred\b|\bcentered\b","centred",body)
body=re.sub(r"\bcolor\b","colour",body); body=re.sub(r"\bgray\b","grey",body)
body=body.replace("Self-Organization","Self-Organisation")
# footnotesize in tables / algorithm -> small
body=body.replace("\\centering\\footnotesize","\\centering\\small").replace("\\footnotesize\n\\setlength","\\small\n\\setlength")
body=body.replace("\\footnotesize\n\\begin{tabular}","\\small\n\\begin{tabular}").replace("\\footnotesize\n\\begin{algorithmic}","\\small\n\\begin{algorithmic}")
body=body.replace("width=0.36\\textwidth","width=0.47\\textwidth").replace("width=0.5\\textwidth","width=0.7\\textwidth").replace("width=0.84\\textwidth]{architecture.pdf}","width=0.95\\textwidth]{architecture.pdf}")
body=body.replace("\\centering\\small","\\centering\\normalsize").replace("\\small\n\\setlength{\\tabcolsep}","\\normalsize\n\\setlength{\\tabcolsep}")
def grab(b, lab):
    i=b.index("\\label{%s}"%lab)
    cands=[]
    for bg,en in [("\\begin{table*}","\\end{table*}"),("\\begin{figure*}","\\end{figure*}"),("\\begin{table}","\\end{table}"),("\\begin{figure}","\\end{figure}")]:
        j=b.rfind(bg,0,i)
        if j!=-1: cands.append((j,bg,en))
    j,bg,en=max(cands); k=b.index(en,i)+len(en)
    if b[k:k+1]=="\n": k+=1
    return b[:j]+b[k:], b[j:k]
def move(b, labs, marker):
    blks=[]
    for l in labs:
        b,x=grab(b,l); blks.append(x)
    i=b.index(marker)
    return b[:i]+"".join(blks)+"\n"+b[i:]
body=move(body,["tab:perc","tab:speth","fig:covnet"],"\\subsection{Baseline Methods}")
body=move(body,["tab:abl","tab:dtn","fig:fwd"],"\\section{Results and Analysis}")
body=move(body,["tab:alloc","fig:alloc","tab:dec"],"\\subsection{Failure Recovery Analysis}")

# ---- section structure per the manuscript template: Introduction / Methodology / Results / Conclusion
def region(b, start, end, old, new):
    i=b.index(start); j=b.index(end,i)
    return b[:i]+b[i:j].replace(old,new)+b[j:]
body=region(body,"\\section{Related Work}","\\section{Problem Formulation}","\\subsection{","\\subsubsection{")
body=body.replace("\\section{Related Work}","\\subsection{Background}")
body=body.replace("\\section{Problem Formulation}","\\subsection{Problem Statement}")
body=body.replace("\\section{Proposed Methodology}","\\section{Methodology}")
body=region(body,"\\section{Experimental Setup}","\\section{Results and Analysis}","\\subsection{","\\subsubsection{")
body=body.replace("\\section{Results and Analysis}","")
body=body.replace("\\section{Experimental Setup}","\\section{Results}\n\\subsection{Experimental Setup}")
body=body.replace("\\section{Discussion and Limitations}","\\subsection{Discussion and Limitations}")
body=body.replace("\\section{Conclusion and Future Work}","\\section{Conclusion}")
open("/tmp/iet_body.tex","w").write(body)
print(re.findall(r"\\footnotesize|\\scriptsize",body)[:5])
