"""23-month analysis: batches, Zestimate cleaning (self-anchored vs resold), resale outcomes, OOS tests."""
import json,sys,math,re,statistics as st,collections,datetime as dt
S='/tmp/claude-0/an/'
sys.path.insert(0,'/home/claude/sheriff-sale-prep/scripts')
from score import score_case, cache_key, rehab_estimate
cfg=json.load(open('/home/claude/sheriff-sale-prep/reference/scoring_config.json'))
S3=json.load(open(S+'sold3p.json')); cases=json.load(open(S+'cases.json'))
Z=json.load(open(S+'zillow_hist.json')); Z0=json.load(open('/home/claude/sheriff-sale-prep/state/zillow_cache.json'))
med=lambda xs: st.median(xs) if xs else None
def q(xs,p):
    xs=sorted(xs)
    if not xs: return None
    i=(len(xs)-1)*p; lo=math.floor(i); hi=math.ceil(i); return xs[lo]+(xs[hi]-xs[lo])*(i-lo)
def batch(d):
    return 'b4' if d<'2025-06-01' else 'b3' if d<'2025-12-01' else 'b2' if d<'2026-06-01' else 'b1'
BL={'b4':'Jan–May 2025','b3':'Jun–Nov 2025','b2':'Dec 2025–May 2026','b1':'Jun–Nov 2026'}
NOW=dt.date(2026,11,11)
def ago_m(s):
    if not s: return None
    m=re.search(r'(\d+)\s*(day|month)',s)
    if not m: return None
    return int(m.group(1))/30 if m.group(2)=='day' else float(m.group(1))
sys.path.insert(0,'/tmp/claude-0/bin')
from fcmin import fc_min
later=collections.defaultdict(list)
for c in cases: later[c['case_no']].append(c['sale_date'])
LAST=max(c['sale_date'] for c in cases)
for c in cases:
    c['forf']=c['outcome']=='sold_3p' and any(d>c['sale_date'] for d in later[c['case_no']])
ALL3=S3
for c in ALL3:
    c['forf']=any(d>c['sale_date'] for d in later[c['case_no']])
    istax=(c.get('sale_category') or '').lower().startswith('tax lien')
    has,mn=fc_min(c['comments']); c['free_clear']=bool(c.get('free_clear')) or has
    paid='PAID IN' in (c['comments'] or '').upper(); c['ct_stale']=paid
    c['minbid']=mn if (istax and mn) else None
    if c['minbid'] is None and istax and c['free_clear'] and c.get('fc_min_bid'): c['minbid']=c['fc_min_bid']
    if c['minbid'] is not None and not paid and c['minbid']>=c['ct']-1: c['minbid']=None
    c['open_eff']=c['minbid'] or (None if paid else (c.get('recalc_ct_bid') or c['ct']))
    stated=c['minbid'] is not None
    c['fc_stated']=stated
    c['decree']=(not stated) and bool(re.search(r'\bDECREE\b|UPSET',c['comments'] or '',re.I)) and istax
    c['over_eff']=c['price']-c['open_eff'] if c['open_eff'] else None; c['ratio_eff']=c['price']/c['open_eff'] if c['open_eff'] else None
    c['grp']='Tax lien (decree)' if c['decree'] else ('Free & clear tax lien' if stated else ('Tax lien' if c['deal_type']=='Free & clear tax lien' else c['deal_type']))
    zz=Z.get(cache_key(c)) or Z0.get(cache_key(c))
    cc=dict(c); cc['opening_bid']=c['open_eff'] or c['price']; cc['fc_min_bid']=c['minbid']
    r=score_case(cc,zz,cfg) if zz else None
    c['score']=r['prelim_score'] if r else None; c['pred_bid']=r['expected_bid'] if (r and c['open_eff']) else None
S3=[c for c in ALL3 if not c['forf']]
for c in S3:
    z=Z.get(cache_key(c)) or Z0.get(cache_key(c)) or {}
    c['zr']=z; c['b']=batch(c['sale_date'])
    sd=dt.date.fromisoformat(c['sale_date']); c['held_m']=(NOW-sd).days/30.4
    zest=z.get('zestimate'); p=c['price']
    lsp=z.get('last_sold_price') or z.get('subject_anchor_price'); la=ago_m(z.get('last_sold_ago') or z.get('subject_anchor_date'))
    kind=z.get('subject_anchor_kind'); sa=z.get('subject_anchored')
    cls='none' if not zest else 'plain'
    c['resale']=None; c['resale_m']=None
    if zest:
        if lsp and abs(lsp-p)/p<=0.05: cls='self'            # Zillow's value is just the sheriff price
        elif lsp and (la is None or la<=c['held_m']+1) and (sa or kind):   # a later sale at a different price
            cls='resold'; c['resale']=lsp; c['resale_m']=(c['held_m']-la) if la is not None else None
        elif kind=='sale' and not lsp:
            if abs(zest-p)/p<=0.05: cls='self'
            else: cls='resold'; c['resale']=zest
        elif kind=='listing': cls='listed'
        elif sa and not kind:
            cls='self' if abs(zest-p)/p<=0.05 else 'anch'
        if cls=='plain' and abs(zest-p)/p<=0.03: cls='self'
    c['zcls']=cls
    c['val']=zest if cls in('plain','resold','listed','anch') else None      # independent value
    if c['val']:
        rh=rehab_estimate(z,cfg); c['rehab']=rh
        c['pv']=p/c['val']; basis=p*1.04+rh; c['mg']=(c['val']*0.9-basis)/basis
    else: c['pv']=None; c['mg']=None
    if c['resale']:
        rh=rehab_estimate({**z,'renovated':False},cfg)   # rehab as if bought unrenovated
        c['rs_ratio']=c['resale']/p; c['rs_gross']=c['resale']-p
        basis=p*1.04+rh; c['rs_net']=(c['resale']*0.9-basis)/basis; c['rs_rehab']=rh
def summ(g,key='pv',mk='mg'):
    pz=[c[key] for c in g if c.get(key) is not None]; mg=[c[mk] for c in g if c.get(mk) is not None]
    go=[c for c in g if c['open_eff']]
    return {'n':len(g),'price':round(med([c['price'] for c in g])) if g else None,'open':round(med([c['open_eff'] for c in go])) if go else None,
     'over':round(med([c['over_eff'] for c in go])) if go else None,'w5':round(100*sum(1 for c in go if c['ratio_eff']<1.05)/len(go)) if go else None,'n_open':len(go),
     'nz':len(pz),'pz':round(med(pz),2) if pz else None,'pz25':round(q(pz,.25),2) if pz else None,'pz75':round(q(pz,.75),2) if pz else None,
     'margin':round(med(mg),2) if mg else None,'m20':round(100*sum(1 for x in mg if x>=.2)/len(mg)) if mg else None}
G=['Free & clear tax lien','Tax lien','Tax lien (decree)','Mortgage foreclosure','HOA/condo judgment']
R={}
# --- A. volumes & outcomes per batch
R['vol']={}
for b in ['b4','b3','b2','b1','all']:
    cs=[c for c in cases if b=='all' or batch(c['sale_date'])==b]; s=[c for c in S3 if b=='all' or c['b']==b]
    oc=collections.Counter(c['outcome'] for c in cs); auc=[c for c in cs if c['outcome'] in('sold_3p','plaintiff_overbid','plaintiff_costs')]
    mfa=[c for c in auc if c['deal_type']=='Mortgage foreclosure']; tla=[c for c in auc if c['deal_type'] in('Tax lien','Free & clear tax lien')]
    R['vol'][b]={'sales':len(set(c['sale_date'] for c in cs)),'listings':len(cs),'distinct':len(set(c['case_no'] for c in cs)),'outcomes':dict(oc),
      'auction_pct':round(100*len(auc)/len(cs),1),'sold3p_all':oc['sold_3p'],'sold3p_res':len(s),
      'mf_plaintiff':[sum(1 for c in mfa if c['outcome']!='sold_3p'),len(mfa)],'tl_plaintiff':[sum(1 for c in tla if c['outcome']!='sold_3p'),len(tla)],
      'tl_plaintiff_who':dict(collections.Counter((c.get('plaintiff') or '')[:30] for c in tla if c['outcome']!='sold_3p').most_common(5)),
      'bucket':dict(collections.Counter(c['bucket'] for c in auc if c['outcome']=='sold_3p')),
      'excl':dict(collections.Counter(c['bucket_reason'][:45] for c in auc if c['outcome']=='sold_3p' and c['bucket']!='ok').most_common(8)),
      'zcls':dict(collections.Counter(c['zcls'] for c in s))}
# --- B. per batch × group, raw (old method: any Zestimate) and clean (independent value)
for c in S3:
    c['pz_raw']=c['price']/c['zr']['zestimate'] if c['zr'].get('zestimate') else None
    if c['pz_raw'] is not None:
        rh=rehab_estimate(c['zr'],cfg); basis=c['price']*1.04+rh; c['mg_raw']=(c['zr']['zestimate']*0.9-basis)/basis
    else: c['mg_raw']=None
R['grp']={b:{g:{'clean':summ([c for c in S3 if c['grp']==g and (b=='all' or c['b']==b)]),'raw':summ([c for c in S3 if c['grp']==g and (b=='all' or c['b']==b)],'pz_raw','mg_raw')} for g in G+['ALL']} for b in ['b4','b3','b2','b1','all']}
for b in R['grp']:
    s=[c for c in S3 if b=='all' or c['b']==b]; R['grp'][b]['ALL']={'clean':summ(s),'raw':summ(s,'pz_raw','mg_raw')}
# by value class within clean
R['by_zcls']={k:summ([c for c in S3 if c['zcls']==k]) for k in ['plain','resold','listed','anch']}
R['by_zcls_batch']={b:{k:summ([c for c in S3 if c['zcls']==k and c['b']==b]) for k in ['plain','resold','listed']} for b in BL}
# --- C. resale outcomes
RS=[c for c in S3 if c.get('resale')]
def rsum(g):
    if not g: return {'n':0}
    return {'n':len(g),'sheriff':round(med([c['price'] for c in g])),'resale':round(med([c['resale'] for c in g])),'ratio':round(med([c['rs_ratio'] for c in g]),2),
      'gross':round(med([c['rs_gross'] for c in g])),'gross25':round(q([c['rs_gross'] for c in g],.25)),'gross75':round(q([c['rs_gross'] for c in g],.75)),
      'net':round(med([c['rs_net'] for c in g]),2),'net20':round(100*sum(1 for c in g if c['rs_net']>=.2)/len(g)),'netneg':round(100*sum(1 for c in g if c['rs_net']<0)/len(g)),
      'p_over_resale':round(med([c['price']/c['resale'] for c in g]),2),'months':round(med([c['resale_m'] for c in g if c['resale_m'] is not None]),1) if any(c['resale_m'] is not None for c in g) else None,
      'rehab':round(med([c['rs_rehab'] for c in g])),'lost_gross':sum(1 for c in g if c['rs_gross']<0)}
R['resale']={'all':rsum(RS),'by_grp':{g:rsum([c for c in RS if c['grp']==g]) for g in G},'by_batch':{b:rsum([c for c in RS if c['b']==b]) for b in BL},
  'by_resale_band':{lab:rsum([c for c in RS if lo<=c['resale']<hi]) for lab,lo,hi in [('<100k',0,1e5),('100-200k',1e5,2e5),('200-300k',2e5,3e5),('300k+',3e5,1e12)]},
  'share_resold_by_batch':{b:[sum(1 for c in S3 if c['b']==b and c['zcls']=='resold'),sum(1 for c in S3 if c['b']==b and c['zcls']=='listed'),sum(1 for c in S3 if c['b']==b and c['zcls']=='self'),sum(1 for c in S3 if c['b']==b)] for b in BL}}
R['resale']['low_resales']=sorted([(c['address'],c['municipality'],c['sale_date'],round(c['price']),c['resale'],c['grp']) for c in RS if c['rs_ratio']<1.3],key=lambda t:t[4]/t[3])[:25]
R['resale']['top']=sorted([(c['address'],c['municipality'],c['sale_date'],round(c['price']),c['resale'],c['grp'],round(c['rs_net'],2)) for c in RS],key=lambda t:-t[6])[:12]
# --- D. value bands (clean), price bands
R['zband']={b:{lab:summ([c for c in S3 if c['val'] and lo<=c['val']<hi and (b=='all' or c['b']==b)]) for lab,lo,hi in [('<75k',0,75e3),('75-150k',75e3,150e3),('150-250k',150e3,250e3),('250k+',250e3,1e12)]} for b in ['b4','b3','y2026','all']}
for lab,lo,hi in [('<75k',0,75e3),('75-150k',75e3,150e3),('150-250k',150e3,250e3),('250k+',250e3,1e12)]:
    R['zband']['y2026'][lab]=summ([c for c in S3 if c['val'] and lo<=c['val']<hi and c['b'] in('b1','b2')])
# --- E. municipalities (23 months)
mun=collections.Counter(c['municipality'] for c in S3)
R['muni']={m:{'n':n,'decree':sum(1 for c in S3 if c['municipality']==m and c['grp']=='Tax lien (decree)'),**{k:v for k,v in summ([c for c in S3 if c['municipality']==m and c['grp']!='Tax lien (decree)']).items() if k in('nz','pz','margin','m20','price')},
   'resold':rsum([c for c in RS if c['municipality']==m]).get('n'),'rs_net':rsum([c for c in RS if c['municipality']==m]).get('net')} for m,n in mun.most_common(25) if n>=8}
# --- F. OOS winning-bid & score tests on 2025 with fixed K
K={'Free & clear tax lien':.25,'Tax lien':.40,'Mortgage foreclosure':.52,'HOA/condo judgment':.52,'Other':.45}
def corr(a,b):
    ma,mb=st.mean(a),st.mean(b); return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
def rk(x): s=sorted(range(len(x)),key=lambda i:x[i]); r=[0]*len(x); [r.__setitem__(i,k) for k,i in enumerate(s)]; return r
def fitk(g):
    g=[c for c in g if c.get('arv_v') and c['open_eff']]
    return min(((k/100, med([abs(max(c['open_eff'],k/100*c['arv_v'])-c['price'])/c['arv_v'] for c in g])) for k in range(5,90)),key=lambda t:t[1]) if len(g)>=8 else (None,None)
for c in S3: c['arv_v']=c['val']
R['fit']={}
for g in G[:4]:
    row={}
    for b in ['b4','b3','b2','b1']:
        gs=[c for c in S3 if c['grp']==g and c['b']==b]; k,e=fitk(gs); gv=[c for c in gs if c['arv_v'] and c['open_eff']]
        kk=0.0 if g=='Tax lien (decree)' else K[g if g in K else 'Other']
        row[b]={'n':len(gv),'k':k,'err_bestk':round(e*100,1) if e is not None else None,
          'err_fixedK':round(100*med([abs(max(c['open_eff'],kk*c['arv_v'])-c['price'])/c['arv_v'] for c in gv]),1) if gv else None,
          'err_55':round(100*med([abs(max(c['open_eff'],.55*c['arv_v'])-c['price'])/c['arv_v'] for c in gv]),1) if gv else None,
          'pv':round(med([c['pv'] for c in gv]),2) if gv else None}
    R['fit'][g]=row
def scoretest(s,newk,valkey='mg'):
    res=[]
    for c in s:
        zz=c['zr']
        if not zz.get('zestimate') or c.get(valkey) is None or not c['open_eff']: continue
        cc=dict(c); cc['opening_bid']=c['open_eff']; c2=dict(cfg)
        if newk: c2['win_pct_of_arv']=0.0 if c['decree'] else K.get(c['deal_type'],.45)
        res.append((score_case(cc,zz,c2)['prelim_score'],c[valkey]))
    if len(res)<5: return {'n':len(res)}
    out={'n':len(res),'spearman':round(corr(rk([a for a,_ in res]),rk([b for _,b in res])),2)}
    for lab,lo,hi in [('0-39',0,40),('40-59',40,60),('60-79',60,80),('80+',80,101)]:
        g=[m for s_,m in res if lo<=s_<hi]; out[lab]=(len(g),round(med(g),2) if g else None,round(100*sum(1 for x in g if x>=.2)/len(g)) if g else None)
    return out
y25=[c for c in S3 if c['b'] in('b3','b4')]; y26=[c for c in S3 if c['b'] in('b1','b2')]
R['score']={'y2025_current':scoretest(y25,False),'y2025_newk':scoretest(y25,True),'y2026_current':scoretest(y26,False),'y2026_newk':scoretest(y26,True),
   'all_current':scoretest(S3,False),'all_newk':scoretest(S3,True),
   'y2025_plainonly_current':scoretest([c for c in y25 if c['zcls']=='plain'],False),'y2025_plainonly_newk':scoretest([c for c in y25 if c['zcls']=='plain'],True)}
# pred bid / actual by group, 2025
R['pred_over_actual_2025']={g:round(med([c['pred_bid']/c['price'] for c in y25 if c['grp']==g and c.get('pred_bid')]),2) for g in G if [c for c in y25 if c['grp']==g and c.get('pred_bid')]}
# --- G. cohorts & repeat appearances over 23 months
by=collections.defaultdict(list)
for c in cases: by[c['case_no']].append(c)
last=max(c['sale_date'] for c in cases)
def cohort(m):
    ks=[k for k,v in by.items() if any(x['sale_date']==m and x['outcome']=='postponed' for x in v)]; fin=collections.Counter(); tt=[]
    for k in ks:
        later=sorted([x for x in by[k] if x['sale_date']>m],key=lambda x:x['sale_date'])
        f=next((x for x in later if x['outcome']!='postponed'),None)
        fin[f['outcome'] if f else ('still postponed' if later and later[-1]['sale_date']==last else 'dropped off lists')]+=1
    return {'n':len(ks),**fin}
R['cohort_jan25']=cohort('2025-01-06'); R['cohort_dec25']=cohort('2025-12-01')
R['appearances']=dict(collections.Counter(min(len(v),10) for v in by.values())); R['distinct']=len(by)
# repeat sales: sold_3p then appears again
rep=[]
for k,v in by.items():
    v=sorted(v,key=lambda x:x['sale_date']); s=[x for x in v if x['outcome']=='sold_3p']
    if s and any(x['sale_date']>s[0]['sale_date'] for x in v):
        rep.append((k,v[0].get('address'),[(x['sale_date'],x['outcome'],x.get('price')) for x in v if x['sale_date']>=s[0]['sale_date']]))
R['resold_cases']={'n':len(rep),'examples':rep[:12]}
# age at sale
def age(c):
    if not c.get('listed_ym'): return None
    y,mo=map(int,c['listed_ym'].split('-')); sy,sm=map(int,c['sale_date'][:7].split('-')); return (sy-y)*12+(sm-mo)
R['age']={o:{'n':len(xs),'median':med(xs),'p25':q(xs,.25),'p75':q(xs,.75)} for o in ['sold_3p','plaintiff_overbid','postponed','stayed'] for xs in [[a for a in (age(c) for c in cases if c['outcome']==o) if a is not None]]}
# --- H. monthly series
ms=sorted(set(c['sale_date'] for c in cases))
R['months']={m:{'n':sum(1 for c in cases if c['sale_date']==m),'auc':sum(1 for c in cases if c['sale_date']==m and c['outcome'] in('sold_3p','plaintiff_overbid','plaintiff_costs')),
   '3p':sum(1 for c in cases if c['sale_date']==m and c['outcome']=='sold_3p'),'3p_res':sum(1 for c in S3 if c['sale_date']==m),
   'price':round(med([c['price'] for c in S3 if c['sale_date']==m])) if [c for c in S3 if c['sale_date']==m] else None,
   'pv':round(med([c['pv'] for c in S3 if c['sale_date']==m and c['pv']]),2) if [c for c in S3 if c['sale_date']==m and c['pv']] else None} for m in ms}
# --- I. fc minimum bids, decree munis by batch
R['fc']={b:{'n':sum(1 for c in S3 if c['grp']=='Free & clear tax lien' and (b=='all' or c['b']==b)),'min':med([c['open_eff'] for c in S3 if c['grp']=='Free & clear tax lien' and (b=='all' or c['b']==b)]),
   'ct':med([c['ct'] for c in S3 if c['grp']=='Free & clear tax lien' and not c['ct_stale'] and (b=='all' or c['b']==b)]),'x':round(med([c['ratio_eff'] for c in S3 if c['grp']=='Free & clear tax lien' and (b=='all' or c['b']==b)]),2) if [c for c in S3 if c['grp']=='Free & clear tax lien' and (b=='all' or c['b']==b)] else None} for b in ['b4','b3','b2','b1','all']}
R['decree_munis']={b:dict(collections.Counter(c['municipality'] for c in S3 if c['grp']=='Tax lien (decree)' and (b=='all' or c['b']==b)).most_common(6)) for b in ['b4','b3','b2','b1','all']}
R['n_val']={'zest':sum(1 for c in S3 if c['zr'].get('zestimate')),'clean':sum(1 for c in S3 if c['val']),'self':sum(1 for c in S3 if c['zcls']=='self'),'n':len(S3)}
# --- J. pooled best K per group over all 23 months; leave-one-batch-out error
R['kpool']={}
for g in G[:4]:
    gs=[c for c in S3 if c['grp']==g]; k,e=fitk(gs); row={'n':len([c for c in gs if c['arv_v'] and c['open_eff']]),'k_all':k,'err_all':round(e*100,1) if e else None}
    loo=[]
    for b in BL:
        tr=[c for c in gs if c['b']!=b]; te=[c for c in gs if c['b']==b and c['arv_v'] and c['open_eff']]; kk,_=fitk(tr)
        if kk is not None and te: loo+= [abs(max(c['open_eff'],kk*c['arv_v'])-c['price'])/c['arv_v'] for c in te]
    row['err_loo']=round(100*med(loo),1) if loo else None
    row['err_55']=round(100*med([abs(max(c['open_eff'],.55*c['arv_v'])-c['price'])/c['arv_v'] for c in gs if c['arv_v'] and c['open_eff']]),1)
    row['pv_med']=round(med([c['pv'] for c in gs if c['pv']]),2); row['pv25']=round(q([c['pv'] for c in gs if c['pv']],.25),2); row['pv75']=round(q([c['pv'] for c in gs if c['pv']],.75),2)
    R['kpool'][g]=row
gs=[c for c in S3 if c['grp']!='Tax lien (decree)']; k,e=fitk(gs); R['kpool']['all_non_decree']={'k':k,'err':round(e*100,1)}
# --- K. forfeited winning bids
F=[c for c in cases if c['forf']]; T=[c for c in cases if c['outcome']=='sold_3p' and c['sale_date']<LAST]
R['forf']={'n':len(F),'of':len(T),'pct':round(100*len(F)/len(T),1),'by_batch':{b:[sum(1 for c in F if batch(c['sale_date'])==b),sum(1 for c in T if batch(c['sale_date'])==b)] for b in BL},
  'by_type':{t:[sum(1 for c in F if c['deal_type']==t),sum(1 for c in T if c['deal_type']==t)] for t in ['Free & clear tax lien','Tax lien','Mortgage foreclosure','HOA/condo judgment','Other']},
  'residential':[sum(1 for c in F if c.get('residential')),sum(1 for c in T if c.get('residential'))]}
nxt=collections.Counter(); chg=[]; gaps=[]
for c in F:
    rows=sorted([x for x in cases if x['case_no']==c['case_no'] and x['sale_date']>c['sale_date']],key=lambda x:x['sale_date'])
    nxt[rows[0]['outcome']]+=1
    fin=next((x for x in rows if x['outcome'] in('sold_3p','plaintiff_overbid','plaintiff_costs')),None)
    if fin and fin['outcome']=='sold_3p' and fin.get('price') and c.get('price'): chg.append(fin['price']/c['price'])
R['forf']['next_listing']=dict(nxt); R['forf']['resold_3p_n']=len(chg); R['forf']['price_change_med']=round(med(chg),2) if chg else None
R['forf']['price_lower_share']=round(100*sum(1 for x in chg if x<1)/len(chg)) if chg else None; R['forf']['price_change_q']=[round(q(chg,.25),2),round(q(chg,.75),2)] if chg else None
R['forf']['price_band']={lab:[sum(1 for c in F if c.get('price') and lo<=c['price']<hi),sum(1 for c in T if c.get('price') and lo<=c['price']<hi)] for lab,lo,hi in [('<25k',0,25e3),('25-75k',25e3,75e3),('75-150k',75e3,150e3),('150k+',150e3,1e12)]}
# forfeited bids vs value
zf=lambda c:(Z.get(cache_key(c)) or Z0.get(cache_key(c)) or {}).get('zestimate')
fv=[c['price']/zf(c) for c in ALL3 if c['forf'] and zf(c)]
R['forf']['pz_forfeited']=round(med(fv),2) if fv else None; R['forf']['n_pz']=len(fv)
# cases flagged with an earlier forfeiture in the notes that later sold: do they go cheaper?
ff=[c for c in S3 if re.search(r'FORF',c['comments'] or '',re.I)]
R['forf']['sold_after_forf_note']={'n':len(ff),'pv':round(med([c['pv'] for c in ff if c['pv']]),2) if [c for c in ff if c['pv']] else None,'n_pv':len([c for c in ff if c['pv']]),'mg':round(med([c['mg'] for c in ff if c['mg'] is not None]),2) if [c for c in ff if c['mg'] is not None] else None}
# --- L. named buyers (only the PDFs printed after deeds were issued)
bu=collections.Counter(); bp=collections.defaultdict(list)
for c in cases:
    m=re.search(r'DEEDED TO\s+(.+?)(?:\.\s|\.$|\s+\d{3}[-. ]|\n|$)',(c['comments'] or ''),re.I)
    if m and c['outcome']=='sold_3p':
        nm=re.sub(r'\s+',' ',m.group(1).upper().strip(' .,')); bu[nm]+=1; bp[nm].append(c.get('price'))
R['buyers']={'n_named':sum(bu.values()),'distinct':len(bu),'llc_share':round(100*sum(v for k,v in bu.items() if re.search(r'LLC|INC|CORP|L\.?P\b|TRUST|PROPERTIES|HOLDINGS|INVEST|CAPITAL|DEVELOPMENT|ENTERPRISE|GROUP|REALTY|HOMES',k))/max(1,sum(bu.values()))),'repeat':{k:v for k,v in bu.most_common(12) if v>=2}}
# --- M. resales split: renovated flips vs as-is
RSok=[c for c in S3 if c.get('resale')]
ren=[c for c in RSok if c['zr'].get('renovated')]; asis=[c for c in RSok if not c['zr'].get('renovated')]
R['resale2']={'all':rsum(RSok),'renovated':rsum(ren),'not_renovated':rsum(asis),'by_grp':{g:rsum([c for c in RSok if c['grp']==g]) for g in G},'by_grp_ren':{g:rsum([c for c in ren if c['grp']==g]) for g in G},
  'by_batch':{b:rsum([c for c in RSok if c['b']==b]) for b in BL},
  'by_resale_band':{lab:rsum([c for c in RSok if lo<=c['resale']<hi]) for lab,lo,hi in [('<100k',0,1e5),('100-200k',1e5,2e5),('200-300k',2e5,3e5),('300k+',3e5,1e12)]},
  'by_price_band':{lab:rsum([c for c in RSok if lo<=c['price']<hi]) for lab,lo,hi in [('<30k',0,3e4),('30-75k',3e4,75e3),('75-150k',75e3,150e3),('150k+',150e3,1e12)]},
  'share_by_batch':{b:{'sold':sum(1 for c in S3 if c['b']==b),'resold':sum(1 for c in S3 if c['b']==b and c['zcls']=='resold'),'listed':sum(1 for c in S3 if c['b']==b and c['zcls']=='listed'),'plain':sum(1 for c in S3 if c['b']==b and c['zcls']=='plain'),'none':sum(1 for c in S3 if c['b']==b and c['zcls']=='none')} for b in BL},
  'loss':[(c['address'],c['municipality'],c['sale_date'],round(c['price']),c['resale'],c['grp']) for c in sorted(RSok,key=lambda c:c['rs_ratio']) if c['rs_ratio']<1.25],
  'ren_ratio_q':[round(q([c['rs_ratio'] for c in ren],.25),2),round(q([c['rs_ratio'] for c in ren],.75),2)] if ren else None,
  'ren_net_q':[round(q([c['rs_net'] for c in ren],.25),2),round(q([c['rs_net'] for c in ren],.75),2)] if ren else None,
  'ren_months_q':[round(q([c['resale_m'] for c in ren if c['resale_m'] is not None],.25),1),round(q([c['resale_m'] for c in ren if c['resale_m'] is not None],.75),1)] if ren else None}
# listed now: asking vs sheriff price
L=[c for c in S3 if c['zcls']=='listed']
R['listed']={'n':len(L),'sheriff':round(med([c['price'] for c in L])) if L else None,'ask':round(med([c['val'] for c in L])) if L else None,'ratio':round(med([c['val']/c['price'] for c in L]),2) if L else None}
# check of the model on real resales: what our score's ARV would have said is unknowable; compare comps median vs resale for renovated flips
cm=[(st.median(c['zr']['comp_sold']),c['resale']) for c in ren if c['zr'].get('comp_sold')]
R['resale2']['comps_vs_resale']={'n':len(cm),'median_ratio':round(med([a/b for a,b in cm]),2) if cm else None}
R['n_sets']={'all3p_res':len(ALL3),'forfeited_res':sum(1 for c in ALL3 if c['forf']),'final_res':len(S3),'with_value':sum(1 for c in S3 if c['val']),'stale_ct':sum(1 for c in S3 if c['ct_stale'])}
json.dump(R,open(S+'deep.json','w'),indent=1,default=str)
json.dump([{k:v for k,v in c.items() if k not in('z','zr')} for c in S3],open(S+'sold3p_deep.json','w'),default=str)
print('ok',R['n_sets'])
