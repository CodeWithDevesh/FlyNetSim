# Builds refs.tex from the paper's REF dictionary, in order of first citation in project_report.tex
import re, runpy, io, contextlib, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
src=open("../paper/figures_src/assemble_iet.py").read()
i=src.index("REF={"); j=src.index("order=[]")
ns={}; exec(src[i:j],ns); REF=ns["REF"]
tex=open("project_report.tex").read()
order=[]
for m in re.finditer(r"\\cite\{([^}]*)\}",tex):
    for k in m.group(1).split(","):
        k=k.strip()
        if k and k not in order: order.append(k)
miss=[k for k in order if k not in REF]; print("cited",len(order),"missing",miss)
open("refs.tex","w").write("\\begin{thebibliography}{99}\n"+"\n".join("\\bibitem{%s} %s."%(k,REF[k]) for k in order if k in REF)+"\n\\end{thebibliography}\n")
