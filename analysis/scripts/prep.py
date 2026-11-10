"""Classify every case in the results PDFs as of its sale date and tag its outcome."""
import json,re,subprocess,sys,collections
REPO='/home/claude/sheriff-sale-prep'
sys.path.insert(0,REPO+'/scripts')
rows=json.load(open('/tmp/claude-0/an/all_raw.json'))
FREE_CLEAR=re.compile(r"\bF\s*[&/]\s*C\b|FREE\s*(AND|&)\s*CLEAR", re.I)
def outcome(s):
    s=s or ''
    m=re.match(r'(.*?)\s*-\s*\$([\d,]+(?:\.\d+)?)',s)
    amt=float(m.group(2).replace(',','')) if m else None
    k=(m.group(1) if m else s).strip()
    if k.startswith('Third Party'): return 'sold_3p',amt
    if k.startswith('Overbid'): return 'plaintiff_overbid',amt
    if k.startswith('Cost & Tax') or k.startswith('PLTF Cost'): return 'plaintiff_costs',amt
    if 'Postponed' in k or '(Waived)' in k or 'PP Generally' in k: return 'postponed',None
    if 'Stayed' in k: return 'stayed',None
    if 'Money Made' in k: return 'paid',None
    return 'other',None
out=[]
for sd in sorted(set(r['sale_date'] for r in rows)):
    cs=[dict(r) for r in rows if r['sale_date']==sd]
    for c in cs:
        c['outcome'],c['price']=outcome(c['status'])
        c['status_raw']=c['status']
        if c['outcome'] in('sold_3p','plaintiff_overbid','plaintiff_costs'): c['status']='Active'
    json.dump(cs,open('/tmp/claude-0/an/in.json','w'))
    r=subprocess.run([sys.executable,'-I',REPO+'/scripts/classify.py','/tmp/claude-0/an/in.json','/tmp/claude-0/an/cl.json','--sale-date',sd],capture_output=True,text=True)
    if r.returncode: print(r.stderr[-500:]); sys.exit(1)
    cl=json.load(open('/tmp/claude-0/an/cl.json'))
    for c in cl:
        c['free_clear']=bool(c.get('fc_min_bid')) or bool(FREE_CLEAR.search(c.get('comments') or ''))
        cat=(c.get('sale_category') or '').lower()
        c['deal_type']=('Free & clear tax lien' if c['free_clear'] else 'Tax lien') if cat.startswith('tax lien') else 'Mortgage foreclosure' if cat.startswith('mortgage') else 'HOA/condo judgment' if cat.startswith('hoa') else 'Other'
        m=re.search(r'(\d+)([A-Z]{3})(\d{2})$',c['sale_id'] or '')
        c['listed_ym']=f"20{m.group(3)}-{['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'].index(m.group(2))+1:02d}" if m else None
        out.append(c)
json.dump(out,open('/tmp/claude-0/an/cases.json','w'),default=str)
print(len(out))
print(collections.Counter((c['sale_date'],c['outcome']) for c in out))
print(collections.Counter(c['bucket'] for c in out if c['outcome']=='sold_3p'))
print(collections.Counter(c['bucket_reason'] for c in out if c['outcome']=='sold_3p').most_common(12))
