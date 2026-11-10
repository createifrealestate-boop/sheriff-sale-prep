import json,sys,math,statistics as st,collections
sys.path.insert(0,'/home/claude/sheriff-sale-prep/scripts')
from score import score_case, cache_key
cfg=json.load(open('/home/claude/sheriff-sale-prep/reference/scoring_config.json'))
S=json.load(open('/tmp/claude-0/an/sold3p.json')); cases=json.load(open('/tmp/claude-0/an/cases.json'))
Z=json.load(open('/tmp/claude-0/an/zillow_hist.json')); Z0=json.load(open('/home/claude/sheriff-sale-prep/state/zillow_cache.json'))
B1=lambda d: d>='2026-06-01'; 
med=lambda xs: st.median(xs) if xs else None
def q(xs,p):
    xs=sorted(xs); i=(len(xs)-1)*p; lo=math.floor(i); hi=math.ceil(i); return xs[lo]+(xs[hi]-xs[lo])*(i-lo)
def summ(g):
    pz=[c['pz'] for c in g if c.get('pz') is not None]; mg=[c['margin'] for c in g if c.get('margin') is not None]
    return {'n':len(g),'price':round(med([c['price'] for c in g])) if g else None,'open':round(med([c['open_eff'] for c in g])) if g else None,
     'over':round(med([c['over_eff'] for c in g])) if g else None,'w5':round(100*sum(1 for c in g if c['ratio_eff']<1.05)/len(g)) if g else None,
     'nz':len(pz),'pz':round(med(pz),2) if pz else None,'pz25':round(q(pz,.25),2) if pz else None,'pz75':round(q(pz,.75),2) if pz else None,
     'margin':round(med(mg),2) if mg else None,'m20':round(100*sum(1 for x in mg if x>=.2)/len(mg)) if mg else None}
G=['Free & clear tax lien','Tax lien','Tax lien (decree)','Mortgage foreclosure','HOA/condo judgment']
R={'batch':{}}
for name,f in [('b2',lambda c: not B1(c['sale_date'])),('b1',lambda c: B1(c['sale_date'])),('all',lambda c: True)]:
    s=[c for c in S if f(c)]; cs=[c for c in cases if f(c)]
    oc=collections.Counter(c['outcome'] for c in cs)
    auc=[c for c in cs if c['outcome'] in('sold_3p','plaintiff_overbid','plaintiff_costs')]
    mfa=[c for c in auc if c['deal_type']=='Mortgage foreclosure']
    zb={}
    for lab,lo,hi in [('<75k',0,75e3),('75-150k',75e3,150e3),('150-250k',150e3,250e3),('250k+',250e3,1e12)]:
        zb[lab]=summ([c for c in s if c.get('zest') and lo<=c['zest']<hi])
    R['batch'][name]={'listings':len(cs),'distinct':len(set(c['case_no'] for c in cs)),'outcomes':dict(oc),
      'auction_rate':round(100*len(auc)/len(cs)),'sold3p_all':oc['sold_3p'],'sold3p_res':len(s),
      'all':summ(s),'groups':{g:summ([c for c in s if c['grp']==g]) for g in G},'zband':zb,
      'mf_plaintiff':(sum(1 for c in mfa if c['outcome']!='sold_3p'),len(mfa)),
      'bucket':dict(collections.Counter(c['bucket'] for c in auc if c['outcome']=='sold_3p')),
      'excl_reasons':dict(collections.Counter(c['bucket_reason'] for c in auc if c['outcome']=='sold_3p' and c['bucket']!='ok')),
      'decree_munis':dict(collections.Counter(c['municipality'] for c in s if c['grp']=='Tax lien (decree)')),
      'months':{m:{'n':sum(1 for c in cs if c['sale_date']==m),'auc':sum(1 for c in auc if c['sale_date']==m),'3p':sum(1 for c in auc if c['sale_date']==m and c['outcome']=='sold_3p')} for m in sorted(set(c['sale_date'] for c in cs))}}
# out-of-sample: per-type k fitted on b1, tested on b2; also fit on b2
def fitk(g):
    g=[c for c in g if c.get('arv')]
    return min(((k/100, med([abs(max(c['open_eff'],k/100*c['arv'])-c['price'])/c['arv'] for c in g])) for k in range(5,90)),key=lambda t:t[1]) if len(g)>=5 else (None,None)
R['fit']={}
for g in G[:4]:
    b1=[c for c in S if c['grp']==g and B1(c['sale_date'])]; b2=[c for c in S if c['grp']==g and not B1(c['sale_date'])]
    k1,_=fitk(b1); k2,_=fitk(b2)
    def err(gs,k): gs=[c for c in gs if c.get('arv')]; return round(100*med([abs(max(c['open_eff'],k*c['arv'])-c['price'])/c['arv'] for c in gs]),1) if gs and k is not None else None
    R['fit'][g]={'k_b1':k1,'k_b2':k2,'err_b2_with_k1':err(b2,k1),'err_b2_with_55':err(b2,.55),'n_b2':len([c for c in b2 if c.get('arv')]),'price_over_arv_b2':round(med([c['pa'] for c in b2 if c.get('pa')]),2) if b2 else None}
K={'Free & clear tax lien':.25,'Tax lien':.40,'Mortgage foreclosure':.52,'HOA/condo judgment':.52,'Other':.45}
def corr(a,b):
    ma,mb=st.mean(a),st.mean(b); return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
def rk(x): s=sorted(range(len(x)),key=lambda i:x[i]); r=[0]*len(x); [r.__setitem__(i,k) for k,i in enumerate(s)]; return r
def scoretest(s,newk):
    res=[]
    for c in s:
        zz=Z.get(cache_key(c)) or Z0.get(cache_key(c))
        if not zz or not zz.get('zestimate') or c.get('margin') is None: continue
        cc=dict(c); cc['opening_bid']=c['open_eff']; c2=dict(cfg)
        if newk: c2['win_pct_of_arv']=0.0 if c['decree'] else K.get(c['deal_type'],.45)
        res.append((score_case(cc,zz,c2)['prelim_score'],c['margin']))
    out={'n':len(res),'spearman':round(corr(rk([a for a,_ in res]),rk([b for _,b in res])),2)}
    for lab,lo,hi in [('0-39',0,40),('40-59',40,60),('60-79',60,80),('80+',80,101)]:
        g=[m for s_,m in res if lo<=s_<hi]; out[lab]=(len(g),round(med(g),2) if g else None,round(100*sum(1 for x in g if x>=.2)/len(g)) if g else None)
    return out
b2=[c for c in S if not B1(c['sale_date'])]
R['score_b2_current']=scoretest(b2,False); R['score_b2_newk']=scoretest(b2,True)
R['score_all_current']=scoretest(S,False); R['score_all_newk']=scoretest(S,True)
# postponement cohort: December 2025 postponed -> outcomes by Nov 2026
by=collections.defaultdict(list)
for c in cases: by[c['case_no']].append(c)
dec=[k for k,v in by.items() if any(x['sale_date']=='2025-12-01' and x['outcome']=='postponed' for x in v)]
fin=collections.Counter()
for k in dec:
    later=sorted([x for x in by[k] if x['sale_date']>'2025-12-01'],key=lambda x:x['sale_date'])
    fin[next((x['outcome'] for x in later if x['outcome']!='postponed'),'still postponed' if later and later[-1]['sale_date']=='2026-11-02' else 'dropped off lists')]+=1
R['dec_cohort']={'n':len(dec),**fin}
R['appearances_12m']=dict(collections.Counter(len(v) for v in by.values())); R['distinct_12m']=len(by)
json.dump(R,open('/tmp/claude-0/an/compare.json','w'),indent=1)
print(json.dumps(R,indent=0)[:12000])
