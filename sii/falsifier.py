from dataclasses import dataclass
@dataclass
class Outcome:
 hit_100:bool=False; hit_200:bool=False; hit_300:bool=False; days_to_100:int|None=None; days_to_200:int|None=None; days_to_300:int|None=None; max_return:float=0.0; max_drawdown:float=0.0
def forward_outcome(rows,start,horizon_days=756):
 rows=sorted(rows,key=lambda x:x['date']); base=next((r.get('adj_close',r.get('close')) for r in rows if r['date']>=start),None)
 if base in (None,0):return Outcome()
 o=Outcome(); peak=base
 for r in rows:
  if r['date']<start:continue
  p=r.get('adj_close',r.get('close'))
  if p is None:continue
  ret=p/base-1; o.max_return=max(o.max_return,ret); peak=max(peak,p); o.max_drawdown=min(o.max_drawdown,p/peak-1)
  days=(r['date']-start).days
  if days<=horizon_days:
   if not o.hit_100 and ret>=1:o.hit_100=True;o.days_to_100=days
   if not o.hit_200 and ret>=2:o.hit_200=True;o.days_to_200=days
   if not o.hit_300 and ret>=3:o.hit_300=True;o.days_to_300=days
 return o
