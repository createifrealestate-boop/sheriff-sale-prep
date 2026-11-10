import json,sys,statistics as st,collections,math
sys.path.insert(0,'/home/claude/sheriff-sale-prep/scripts')
from score import cache_key, rehab_estimate
cfg=json.load(open('/home/claude/sheriff-sale-prep/reference/scoring_config.json'))
cases=json.load(open('/tmp/claude-0/an/cases.json'))
Z=json.load(open('/tmp/claude-0/an/zillow_hist.json')); Z0=json.load(open('/home/claude/sheriff-sale-prep/state/zillow_cache.json'))
def z(c): k=cache_key(c); return Z.get(k) or Z0.get(k) or {}
med=lambda xs: st.median(xs) if xs else None
def q(xs,p):
    xs=sorted(xs); 
    if not xs: return None
    i=(len(xs)-1)*p; lo=math.floor(i); hi=math.ceil(i); return xs[lo]+(xs[hi]-xs[lo])*(i-lo)
R={}
# 1 outcomes by month (all cases)
months=sorted(set(c['sale_date'] for c in cases))
R['outcomes']=[{ 'sale_date':m, **collections.Counter(c['outcome'] for c in cases if c['sale_date']==m), 'total':sum(1 for c in cases if c['sale_date']==m)} for m in months]
tot=collections.Counter(c['outcome'] for c in cases); R['outcome_totals']=dict(tot); R['n_cases']=len(cases)
# residential auctioned
A=[c for c in cases if c['outcome'] in('sold_3p','plaintiff_overbid','plaintiff_costs')]
R['auctioned']=len(A); R['auctioned_res']=sum(1 for c in A if c.get('residential'))
S=[c for c in A if c['outcome']=='sold_3p' and c.get('residential') and c['price']]
R['n_3p_res']=len(S); R['n_3p_all']=sum(1 for c in A if c['outcome']=='sold_3p')
for c in S:
    zz=z(c); c['zest']=zz.get('zestimate'); c['subject_anch']=zz.get('subject_anchored'); c['z']=zz
    c['open']=c.get('opening_bid') or c.get('cost_tax_bid'); c['ct']=c.get('cost_tax_bid')
    c['over']=c['price']-c['open'] if c['open'] else None
    c['ratio_open']=c['price']/c['open'] if c['open'] else None
    c['at_open']=abs(c['over'])<=1 if c['over'] is not None else None
    if c['zest']:
        c['pz']=c['price']/c['zest']
        rh=rehab_estimate(zz,cfg); basis=c['price']*1.04+rh; c['rehab']=rh
        c['margin']=(c['zest']*0.9-basis)/basis
# 2 price vs opening
def summ(group):
    pr=[c for c in group]; ro=[c['ratio_open'] for c in pr if c['ratio_open']]
    pz=[c['pz'] for c in pr if c.get('pz') is not None]
    mg=[c['margin'] for c in pr if c.get('margin') is not None]
    return {'n':len(pr),'at_open_pct':round(100*sum(1 for c in pr if c['at_open'])/len(pr)) if pr else None,
      'median_price':med([c['price'] for c in pr]),'median_open':med([c['open'] for c in pr if c['open']]),
      'median_over':med([c['over'] for c in pr if c['over'] is not None]),
      'median_ratio_open':round(med(ro),2) if ro else None,
      'n_z':len(pz),'median_pz':round(med(pz),3) if pz else None,'p25_pz':round(q(pz,.25),3) if pz else None,'p75_pz':round(q(pz,.75),3) if pz else None,
      'median_margin':round(med(mg),3) if mg else None,'share_margin20':round(100*sum(1 for x in mg if x>=0.2)/len(mg)) if mg else None}
R['all3p']=summ(S)
R['by_type']={t:summ([c for c in S if c['deal_type']==t]) for t in sorted(set(c['deal_type'] for c in S))}
bands=[(0,5000),(5000,15000),(15000,40000),(40000,1e12)]
R['by_open_band']={f'{lo:.0f}-{hi:.0f}':summ([c for c in S if c['open'] and lo<=c['open']<hi]) for lo,hi in bands}
zb=[(0,75000),(75000,150000),(150000,250000),(250000,1e12)]
R['by_zest_band']={f'{lo:.0f}-{hi:.0f}':summ([c for c in S if c.get('zest') and lo<=c['zest']<hi]) for lo,hi in zb}
R['by_month']={m:summ([c for c in S if c['sale_date']==m]) for m in months}
mun=collections.Counter(c['municipality'] for c in S)
R['by_muni']={m:summ([c for c in S if c['municipality']==m]) for m,n in mun.most_common() if n>=4}
R['anch']={'subject_anchored':summ([c for c in S if c.get('subject_anch')]),'not':summ([c for c in S if c.get('zest') and not c.get('subject_anch')])}
# 3 plaintiff overbids
P=[c for c in A if c['outcome'] in('plaintiff_overbid','plaintiff_costs')]
R['plaintiff']={'n':len(P),'by_type':dict(collections.Counter(c['deal_type'] for c in P))}
R['sold_by_type_share']={}
for t in set(c['deal_type'] for c in A):
    a=[c for c in A if c['deal_type']==t]; R['sold_by_type_share'][t]={'auctioned':len(a),'third_party':sum(1 for c in a if c['outcome']=='sold_3p'),'plaintiff':sum(1 for c in a if c['outcome']!='sold_3p')}
# 4 case age
def age(c):
    if not c.get('listed_ym'): return None
    y,mo=map(int,c['listed_ym'].split('-')); sy,sm=map(int,c['sale_date'][:7].split('-')); return (sy-y)*12+(sm-mo)
for c in cases: c['age']=age(c)
R['age']={o:{'n':len(xs),'median':med(xs),'p25':q(xs,.25),'p75':q(xs,.75)} for o in ['sold_3p','plaintiff_overbid','postponed','stayed'] for xs in [[c['age'] for c in cases if c['outcome']==o and c['age'] is not None]]}
# unique cases across months: how many appear multiple times
byc=collections.defaultdict(list)
for c in cases: byc[c['case_no']].append(c)
R['unique_cases']=len(byc); R['cases_in_all6']=sum(1 for v in byc.values() if len(v)==6)
R['appearances']=dict(collections.Counter(len(v) for v in byc.values()))
# 5 bucket validation
R['bucket_3p']=dict(collections.Counter(c['bucket'] for c in A if c['outcome']=='sold_3p'))
R['bucket_reason_3p_excl']=dict(collections.Counter(c['bucket_reason'] for c in A if c['outcome']=='sold_3p' and c['bucket']!='ok'))
# 6 win pct calibration: model expected = max(open, k*zest)
cal=[c for c in S if c.get('zest') and c['open']]
best=None
for k100 in range(10,81):
    k=k100/100; err=[abs(max(c['open'],k*c['zest'])-c['price'])/c['zest'] for c in cal]
    e=med(err)
    if best is None or e<best[1]: best=(k,e)
R['calib']={'n':len(cal),'best_k':best[0],'median_abs_err_pct_of_zest':round(best[1]*100,1),
  'err_at_55':round(med([abs(max(c['open'],.55*c['zest'])-c['price'])/c['zest'] for c in cal])*100,1),
  'share_price_below_55':round(100*sum(1 for c in cal if c['price']<.55*c['zest'])/len(cal))}
# above-opening sales only
ab=[c for c in cal if not c['at_open']]
R['contested']={'n':len(ab),'median_pz':round(med([c['pz'] for c in ab]),3) if ab else None,'p25':round(q([c['pz'] for c in ab],.25),3) if ab else None,'p75':round(q([c['pz'] for c in ab],.75),3) if ab else None}
un=[c for c in cal if c['at_open']]
R['uncontested']={'n':len(un),'median_pz':round(med([c['pz'] for c in un]),3) if un else None}
json.dump(R,open('/tmp/claude-0/an/results.json','w'),indent=1,default=str)
json.dump(S,open('/tmp/claude-0/an/sold3p.json','w'),indent=0,default=str)
print(json.dumps(R,indent=1,default=str)[:9000])
