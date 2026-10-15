"""Day 1 read-only: currency check and overlap under the nonzero-principal definition. Run: python -m pipeline.scout_overlap"""
import sys,itertools; sys.path.insert(0,'.')
from decimal import Decimal
from statistics import median
from collections import Counter, defaultdict
from pathlib import Path
from pipeline.ixbrl import *
import pipeline.ixbrl as X
from pipeline.scout import norm_tokens, _unit
PE='2026-06-30'
RAW=Path('fixtures/raw')
LAB=['ads','hps_corporate_lending','blue_owl_credit_income','blackstone_secured_lending','blue_owl_capital_corp','ares_capital']
data={}; factsd={}; ctxd={}
for l in LAB:
    c,f,t=parse_ixbrl(RAW/f'{l}_10q_{PE}.htm')
    ip = X._split_identifier if l=='ads' else split_pipe_identifier
    data[l]=assemble_investments(c,f,t,PE,identifier_parser=ip); factsd[l]=f; ctxd[l]=c
def funded(rows): return [r for r in rows if (r['fair_value'] is not None or r['cost'] is not None) and r['principal'] not in (None,0) and r['fair_value'] is not None]
# ---- currency check for HPS / ORCIC
IDAX=X.IDENTIFIER_AXIS
for l in ('hps_corporate_lending','blue_owl_credit_income'):
    rows=funded(data[l])
    non=[r for r in rows if _unit(r)!='usd']
    print(f'\n## {l}: parsed funded rows {len(rows)}, nonzero non-USD principal {len(non)}', dict(Counter(_unit(r) for r in non)))
    # units on cost and fair value facts for those identifiers
    nonids={r['identifier'] for r in non}
    cu=Counter(); fu=Counter()
    for f in factsd[l]:
        c=ctxd[l].get(f.context_ref)
        if c and c.instant==PE and c.typed.get(IDAX) in nonids and len(c.dims)==1:
            if f.name==X.INVESTMENT_TAGS['cost']: cu[(f.unit or '').lower()]+=1
            if f.name==X.INVESTMENT_TAGS['fair_value']: fu[(f.unit or '').lower()]+=1
    print('   unit tags on cost facts of non-USD-principal rows:',dict(cu),'| on fair value facts:',dict(fu))
    for cur in ('eur','gbp'):
        rr=[float(r['fair_value']/r['principal']) for r in non if _unit(r)==cur and r['fair_value'] is not None]
        cc=[float(r['cost']/r['principal']) for r in non if _unit(r)==cur and r['cost'] not in (None,0)]
        if rr: print(f'   {cur.upper()} rows {len(rr)}: median FV/principal {median(rr):.3f}, median cost/principal {median(cc):.3f}')
    usd=[float(r['fair_value']/r['principal']) for r in rows if _unit(r)=='usd']
    print(f'   USD rows {len(usd)}: median FV/principal {median(usd):.3f}')
# ---- overlap under nonzero-principal definition
def toks(l, main_only=None):
    rows=funded(data[l])
    if main_only is not None: rows=[r for r in rows if r['identifier'] in main_only]
    out={}
    for r in rows:
        t=norm_tokens(r['raw_name'])
        if len(''.join(t))<6: continue
        out[t]=out.get(t,False) or _unit(r)=='usd'
    return out
# HTML-confirmed main-schedule identifiers for HPS and ORCIC
from pipeline.scout_html import parse_schedule, xbrl_rows, join, AMOUNT_SCALE, _key
main={}
for l in ('hps_corporate_lending','blue_owl_credit_income'):
    s=parse_schedule(l); c,f,xr=xbrl_rows(l); j=join(s['rows'],xr); idx=j['idx']; sched=j['sched']
    used=set()
    for h in s['rows']:
        if h['cost'] is None and h['fair_value'] is None: continue
        used.update(idx.get(_key(h['principal'],h['cost'],h['fair_value'],AMOUNT_SCALE),[]))
    main[l]={sched[i]['identifier'] for i in used}
ads=toks('ads')
def amatch(t):
    for a in ads:
        if len(a)>=len(t) and a[len(a)-len(t):]==t: return a
    return None
def overlaps(T):
    names=list(T)
    res={}
    for f in names:
        res[('ADS',f)]=(len({t for t in T[f] if amatch(t)}), len({t for t in T[f] if amatch(t) and T[f][t] and ads[amatch(t)]}))
    for f,g in itertools.combinations(names,2):
        com={t for t in T[f] if t in T[g]}
        res[(f,g)]=(len(com), len({t for t in com if T[f][t] and T[g][t]}))
    return res
def show(title,T):
    print('\n##',title)
    res=overlaps(T); short={'hps_corporate_lending':'HPS','blue_owl_credit_income':'ORCIC','blackstone_secured_lending':'BXSL','blue_owl_capital_corp':'OBDC','ares_capital':'ARCC'}
    for (a,b),(x,y) in res.items(): print(f"   {a if a=='ADS' else short[a]} - {short[b]}: all {x} / usd-only {y}")
    print('   candidate pairs (distinct names present in at least 2 of {ADS, f, g}, and in all three):')
    for f,g in itertools.combinations(T,2):
        mf={t for t in T[f] if amatch(t)}; mg={t for t in T[g] if amatch(t)}
        com={t for t in T[f] if t in T[g]}
        union=mf|mg|com; three=mf&mg&com
        usd=lambda S:{t for t in S if T[f].get(t,True) and T[g].get(t,True) and (not amatch(t) or ads[amatch(t)])}
        # three-way must have usd principal in all three
        print(f"     ADS+{short[f]}+{short[g]}: names in >=2 BDCs {len(union)} (usd {len(usd(union))}); in all 3 {len(three)} (usd {len(usd(three))})")
T={l:toks(l) for l in LAB[1:]}
show('XBRL parsed funded rows (nonzero principal and fair value), no HTML filter',T)
T2=dict(T)
for l in main: T2[l]=toks(l,main[l])
show('HPS and ORCIC restricted to rows that appear in the main HTML schedule (others unchanged)',T2)
