"""Day 1 read-only: reconcile HTML schedule totals with XBRL rows. Run: python -m pipeline.scout_reconcile <label>"""

from decimal import Decimal
from collections import Counter, defaultdict
from pipeline.scout_html import *
from pipeline.scout_html import _tables,_first_cell,_key
label=sys.argv[1]
s=parse_schedule(label); ctxs,facts,xr=xbrl_rows(label); j=join(s['rows'],xr)
sched=j['sched']
D=lambda v: Decimal(v or 0)
fv=lambda L: sum((D(r['fair_value']) for r in L),Decimal(0))
print('XBRL schedule rows',len(sched),'FV sum',fv(sched))
# undimensioned total
FV_TAG='us-gaap:InvestmentOwnedAtFairValue'
und=[(f.value,ctxs[f.context_ref].dims) for f in facts if f.name==FV_TAG and ctxs.get(f.context_ref) and ctxs[f.context_ref].instant==PE and not ctxs[f.context_ref].typed]
print('XBRL FV facts at PE without typed identifier (value, dims):')
for v,d in sorted(und,key=lambda x:-abs(x[0] or 0))[:10]: print('   ',v,d)
print('HTML data rows',len(s['rows']),'FV sum x1000',fv(s['rows'])*1000)
print('HTML named totals (no industry subtotals):')
for t in s['totals']:
    n=t['name']
    if re.search(r'Total (Investments|Investment Portfolio|Cash|controlled|non-controlled|Debt Inv|Equity Inv|Joint|Structured Finance Inv)',n,re.I) or n.lower().startswith('total inv'):
        print('   ',n[:90],t['amounts'])
used=set(); 
for h in s['rows']:
    pass
idx=j['idx']
usedset=set()
for h in s['rows']:
    if h['cost'] is None and h['fair_value'] is None: continue
    usedset.update(idx.get(_key(h['principal'],h['cost'],h['fair_value'],AMOUNT_SCALE),[]))
unm=[sched[i] for i in range(len(sched)) if i not in usedset]
print('XBRL rows with no HTML main row:',len(unm),'FV',fv(unm),'| funded among them',sum(1 for r in unm if r['principal'] not in (None,0)))
for r in unm: print('   X',r['raw_name'][:55],'|',r['instrument_type'],'|',r['principal'],r['cost'],r['fair_value'])
print('HTML main rows with no XBRL row:')
for h in j['unmatched_html']: print('   H',h['name'][:60],h['section'],h['principal'],h['cost'],h['fair_value'])
# multi-match
print('HTML rows matching >1 XBRL row:')
for h in s['rows']:
    if h['cost'] is None and h['fair_value'] is None: continue
    hits=idx.get(_key(h['principal'],h['cost'],h['fair_value'],AMOUNT_SCALE),[])
    if len(hits)>1: print('   ',h['name'][:50],h['principal'],h['cost'],h['fair_value'],'-> n XBRL',len(hits),[sched[i]['raw_name'][:30] for i in hits][:3])
