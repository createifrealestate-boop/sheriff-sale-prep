import json,re,sys,statistics as st,collections,math
sys.path.insert(0,'/home/claude/sheriff-sale-prep/scripts')
from score import score_case, cache_key
cfg=json.load(open('/home/claude/sheriff-sale-prep/reference/scoring_config.json'))
S=json.load(open('/tmp/claude-0/an/sold3p.json'))
Z=json.load(open('/tmp/claude-0/an/zillow_hist.json')); Z0=json.load(open('/home/claude/sheriff-sale-prep/state/zillow_cache.json'))
MIN=re.compile(r'MIN\w*\s*BID\s*(?:OF\s*)?(?:THE\s*)?\$?\s*([\d,]+\.\d{2})',re.I)
med=lambda xs: st.median(xs) if xs else None
def q(xs,p):
    xs=sorted(xs); i=(len(xs)-1)*p; lo=math.floor(i); hi=math.ceil(i); return xs[lo]+(xs[hi]-xs[lo])*(i-lo)
for c in S:
    m=MIN.search(c['comments'] or '')
    c['minbid']=float(m.group(1).replace(',','')) if m and c['free_clear'] else None
    c['open_eff']=c['minbid'] or (c.get('fc_min_bid') if c['free_clear'] else None) or c.get('recalc_ct_bid') or c['ct']
    stated=c['free_clear'] and c['open_eff']<c['ct']-1
    c['fc_stated']=stated
    c['decree']=(not stated) and bool(re.search(r'\bDECREE\b|UPSET',c['comments'] or '',re.I)) and (c['sale_category'] or '').lower().startswith('tax lien')
    c['over_eff']=c['price']-c['open_eff']; c['ratio_eff']=c['price']/c['open_eff']
    c['grp']='Tax lien (decree)' if c['decree'] else ('Free & clear tax lien' if stated else ('Tax lien' if c['deal_type']=='Free & clear tax lien' else c['deal_type']))
    zz=Z.get(cache_key(c)) or Z0.get(cache_key(c))
    cc=dict(c); cc['opening_bid']=c['open_eff']; cc['fc_min_bid']=c['minbid']
    r=score_case(cc,zz,cfg) if zz else None
    c['score']=r['prelim_score'] if r else None; c['pred_bid']=r['expected_bid'] if r else None; c['arv']=r['arv'] if r else None
    if r: c['pa']=c['price']/r['arv']
def summ(g):
    pz=[c['pz'] for c in g if c.get('pz') is not None]; mg=[c['margin'] for c in g if c.get('margin') is not None]
    return {'n':len(g),'median_price':round(med([c['price'] for c in g])) if g else None,'median_open':round(med([c['open_eff'] for c in g])) if g else None,
     'median_over':round(med([c['over_eff'] for c in g])) if g else None,'median_ratio':round(med([c['ratio_eff'] for c in g]),2) if g else None,
     'within5pct':round(100*sum(1 for c in g if c['ratio_eff']<1.05)/len(g)) if g else None,
     'n_z':len(pz),'pz':round(med(pz),2) if pz else None,'pz25':round(q(pz,.25),2) if pz else None,'pz75':round(q(pz,.75),2) if pz else None,
     'margin':round(med(mg),2) if mg else None,'m20':round(100*sum(1 for x in mg if x>=.2)/len(mg)) if mg else None}
R={}
R['by_grp']={g:summ([c for c in S if c['grp']==g]) for g in ['Free & clear tax lien','Tax lien','Tax lien (decree)','Mortgage foreclosure','HOA/condo judgment']}
R['all']=summ(S)
R['decree_munis']=dict(collections.Counter(c['municipality'] for c in S if c['grp']=='Tax lien (decree)'))
R['fc_minbid']={'with_amount':sum(1 for c in S if c['minbid']),'fc_total':sum(1 for c in S if c['free_clear']),'median_minbid':med([c['minbid'] for c in S if c['minbid']]),'median_ct':med([c['ct'] for c in S if c['minbid']]),'minbid_over_ct':round(med([c['minbid']/c['ct'] for c in S if c['minbid']]),2)}
# calibration by group: price vs ARV(score's conservative arv) and best k
def best_k(g):
    g=[c for c in g if c.get('arv')]
    if len(g)<5: return None
    b=min(((k/100, med([abs(max(c['open_eff'],k/100*c['arv'])-c['price'])/c['arv'] for c in g])) for k in range(5,90)),key=lambda t:t[1])
    e55=med([abs(max(c['open_eff'],.55*c['arv'])-c['price'])/c['arv'] for c in g])
    return {'n':len(g),'median_price_over_arv':round(med([c['pa'] for c in g]),2),'best_k':b[0],'err_best':round(b[1]*100,1),'err_55':round(e55*100,1),
            'pred_over_actual_median':round(med([c['pred_bid']/c['price'] for c in g]),2)}
R['calib']={g:best_k([c for c in S if c['grp']==g]) for g in R['by_grp']}
R['calib']['all']=best_k(S)
# score vs realized margin
sc=[c for c in S if c['score'] is not None and c.get('margin') is not None]
def corr(a,b):
    ma,mb=st.mean(a),st.mean(b); return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
def ranks(x): s=sorted(range(len(x)),key=lambda i:x[i]); r=[0]*len(x); [r.__setitem__(i,k) for k,i in enumerate(s)]; return r
R['score_vs_margin']={'n':len(sc),'spearman':round(corr(ranks([c['score'] for c in sc]),ranks([c['margin'] for c in sc])),2),
  'by_band':{b:{'n':len(g),'margin':round(med([c['margin'] for c in g]),2) if g else None,'m20':round(100*sum(1 for c in g if c['margin']>=.2)/len(g)) if g else None} for b,lo,hi in [('0-39',0,40),('40-59',40,60),('60-79',60,80),('80+',80,101)] for g in [[c for c in sc if lo<=c['score']<hi]]}}
json.dump(R,open('/tmp/claude-0/an/refined.json','w'),indent=1)
json.dump(S,open('/tmp/claude-0/an/sold3p.json','w'),indent=0,default=str)
print(json.dumps(R,indent=1))
