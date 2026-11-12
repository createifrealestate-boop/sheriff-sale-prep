import json,re,collections,statistics as st,math,sys
S='/tmp/claude-0/an/'
d=json.load(open(S+'sold3p_deep.json')); cases=json.load(open(S+'cases.json'))
med=lambda xs: st.median(xs) if xs else None
def q(xs,p):
    xs=sorted(xs); i=(len(xs)-1)*p; lo=math.floor(i); hi=math.ceil(i); return xs[lo]+(xs[hi]-xs[lo])*(i-lo)
by=collections.defaultdict(list)
for c in cases: by[c['case_no']].append(c)
# 1. forfeiture validation
n=0;withf=0;ex=[]
for k,v in by.items():
    v=sorted(v,key=lambda x:x['sale_date'])
    for i,x in enumerate(v):
        if x['outcome']=='sold_3p' and i<len(v)-1:
            n+=1; nxt=v[i+1]; m=int(x['sale_date'][5:7]); dd=int(x['sale_date'][8:10]); yy=x['sale_date'][2:4]
            pat=rf"FORF\w*[^\n]*\b0?{m}[./-]0?{dd}[./-](20)?{yy}"
            if re.search(pat,nxt['comments'] or '',re.I): withf+=1
            elif len(ex)<8: ex.append((x['sale_date'],x.get('address'),nxt['sale_date'],nxt['outcome'],(nxt['comments'] or '')[:150].replace('\n',' / ')))
print('later appearance after a 3p sale:',n,'next listing notes a forfeiture on that date:',withf); [print(e) for e in ex]
anyf=sum(1 for k,v in by.items() for i,x in enumerate(sorted(v,key=lambda x:x['sale_date'])) if x['outcome']=='sold_3p' and i<len(v)-1 and re.search('FORF',sorted(v,key=lambda x:x['sale_date'])[i+1]['comments'] or '',re.I))
print('next listing mentions FORF at all:',anyf)
# 2. combined-year group tables
G=['Free & clear tax lien','Tax lien','Tax lien (decree)','Mortgage foreclosure','HOA/condo judgment']
def row(g):
    pv=[c['pv'] for c in g if c['pv'] is not None]; mg=[c['mg'] for c in g if c['mg'] is not None]; go=[c for c in g if c['open_eff']]
    return dict(n=len(g),price=round(med([c['price'] for c in g])) if g else None,open=round(med([c['open_eff'] for c in go])) if go else None,w5=round(100*sum(1 for c in go if c['ratio_eff']<1.05)/len(go)) if go else None,
                nz=len(pv),pv=round(med(pv),2) if pv else None,pv25=round(q(pv,.25),2) if pv else None,pv75=round(q(pv,.75),2) if pv else None,mg=round(med(mg),2) if mg else None,m20=round(100*sum(1 for x in mg if x>=.2)/len(mg)) if mg else None)
out={}
for lab,bs in [('2025',('b3','b4')),('2026',('b1','b2')),('all',('b1','b2','b3','b4'))]:
    s=[c for c in d if c['b'] in bs and not c['forf']]
    out[lab]={g:row([c for c in s if c['grp']==g]) for g in G}; out[lab]['ALL']=row(s); out[lab]['ALL ex decree']=row([c for c in s if c['grp']!='Tax lien (decree)'])
    print('==',lab); [print(f"{g[:22]:22}",v) for g,v in out[lab].items()]
# plain-only (Zillow value not reset by a later sale/listing), by year
for lab,bs in [('2025',('b3','b4')),('2026',('b1','b2'))]:
    s=[c for c in d if c['b'] in bs and not c['forf'] and c['zcls']=='plain']; print('plain only',lab,row(s))
# 3. price distribution of final residential 3p sales
s=[c for c in d if not c['forf']]
print('price q',[round(q([c['price'] for c in s],p)) for p in (.1,.25,.5,.75,.9)], 'under50k',round(100*sum(1 for c in s if c['price']<50000)/len(s)),'under100k',round(100*sum(1 for c in s if c['price']<100000)/len(s)))
# opening-bid bands for non-decree: how far over opening
# 4. count of 3p per sale (final, residential)
ms=sorted(set(c['sale_date'] for c in d)); per=[sum(1 for c in s if c['sale_date']==m) for m in ms]; print('final res 3p per sale: median',med(per),min(per),max(per))
# 5. MF: plaintiff share by year; 3p share
for lab,pre in [('2025','2025'),('2026','2026')]:
    a=[c for c in cases if c['sale_date'].startswith(pre) or (lab=='2026' and c['sale_date']=='2025-12-01')]
    if lab=='2025': a=[c for c in a if c['sale_date']!='2025-12-01']
    mf=[c for c in a if c['deal_type']=='Mortgage foreclosure' and c['outcome'] in('sold_3p','plaintiff_overbid','plaintiff_costs')]
    print(lab,'MF auctioned',len(mf),'plaintiff',sum(1 for c in mf if c['outcome']!='sold_3p'))
json.dump(out,open(S+'extra.json','w'),indent=1)
# 6. forfeit re-auction: time and price detail
F=[c for c in cases if c.get('outcome')=='sold_3p' and any(x['sale_date']>c['sale_date'] for x in by[c['case_no']])]
gaps=[];chg=[]
for c in F:
    later=sorted([x for x in by[c['case_no']] if x['sale_date']>c['sale_date']],key=lambda x:x['sale_date'])
    fin=next((x for x in later if x['outcome']=='sold_3p'),None)
    if fin:
        gaps.append((int(fin['sale_date'][:4])-int(c['sale_date'][:4]))*12+int(fin['sale_date'][5:7])-int(c['sale_date'][5:7])); chg.append(fin['price']/c['price'])
print('forfeit -> next 3p sale: n',len(gaps),'gap months',collections.Counter(gaps).most_common(6),'price ratio med',round(med(chg),2),'lower',sum(1 for x in chg if x<1),'higher',sum(1 for x in chg if x>1))
# multiple forfeits
mf=collections.Counter(sum(1 for x in v if x['outcome']=='sold_3p') for v in by.values()); print('cases by # of 3p sales',dict(mf))
