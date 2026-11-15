"""Free-and-clear minimum bid from the Sheriff's notes, all wordings seen Jan 2025 - Nov 2026."""
import re
FC_TOK=re.compile(r"\bF\s*[&/]?\s*C\b|FREE\s*(?:AND|&)\s*CLEAR",re.I)
DATE=re.compile(r"\b\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4}\b|\b\d{1,2}[/-]\d{1,2}\b")
AMT=re.compile(r"\$+\s*([\d,]{3,}(?:\.\d{1,2})?)|\b([\d,]{4,}\.\d{2})\b|\bMIN\w*\.?\s*(?:BID)?\s*(?:OF)?\s*(?:THE)?\s*([\d,]{4,})\b",re.I)
def fc_min(comments):
    """(has_fc_token, min_bid or None). Looks only at lines that mention free & clear or a minimum bid."""
    has=False; best=None
    for line in (comments or '').split('\n'):
        u=line.upper()
        tok=bool(FC_TOK.search(u)) or bool(re.search(r'\bMIN\w*\.?\s*BID',u))
        if not tok: continue
        if FC_TOK.search(u): has=True
        if re.search(r'REASSESS|DAMAGES|PAID IN|JUDG',u): continue
        s=DATE.sub(' ',u)
        for m in AMT.finditer(s):
            v=float((m.group(1) or m.group(2) or m.group(3)).replace(',',''))
            if 500<=v<=250000 and best is None: best=v
    return has,best
if __name__=='__main__':
    for t in ["F/C O/C FOR A MIN BID OF $15,000.00","O/C F&C MIN BID 4500.00","O/C F/C MIN BID $8000","DECREE F/C ($4,000 FOR 3/2/26)","O/C F/C $7,500.00","O/C FC MIN BID 15,000.00","O/C F/C RCVD 3/19/25 $20,000","F/C MIN BID $$5,000.00","O/C F&C MINIMUM BID OF $3,000.00 DATED 01.04.24","F/C O/C FOR A MIN BID OF THE UPSET PRICE","O /C FC MIN BID 7000.00","F/C O/C MIN $5,600.00","NEED UPDATED FREE AND CLEAR ORDER","O/C F&C 5000.00","F/C UPSET DECREE ($5,000 EXPOSURE 2/2/26)","O/C TO REASSESS DAMAGES TO $91,372.51"]:
        print(fc_min(t),'|',t)
