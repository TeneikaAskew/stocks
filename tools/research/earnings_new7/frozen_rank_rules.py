"""Exactly two authorized post-hoc vendor-only Spearman sensitivities; no fitting."""
from pathlib import Path
from decimal import Decimal as D,localcontext
import csv,json,hashlib,datetime as dt
O=Path(__file__).parent

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def average_ranks(values):
 ordered=sorted(range(len(values)),key=lambda i:(values[i],i));ranks=[None]*len(values);j=0
 while j<len(ordered):
  k=j+1
  while k<len(ordered) and values[ordered[k]]==values[ordered[j]]:k+=1
  rank=(D(j+1)+D(k))/2
  for i in ordered[j:k]:ranks[i]=rank
  j=k
 return ranks

def spearman(x,y):
 rx=average_ranks(x);ry=average_ranks(y);n=D(len(x));mx=sum(rx)/n;my=sum(ry)/n;cov=sum((a-mx)*(b-my) for a,b in zip(rx,ry));xx=sum((a-mx)**2 for a in rx);yy=sum((b-my)**2 for b in ry)
 if xx==0 or yy==0:raise ValueError('constant vector, not estimable')
 with localcontext() as ctx:ctx.prec=50;rho=cov/(xx*yy).sqrt()
 return {'n':len(x),'rho_decimal50':str(rho),'news_average_ranks':[str(v) for v in rx],'outcome_average_ranks':[str(v) for v in ry],'centered_rank_cross_product':str(cov),'news_rank_sum_squares':str(xx),'outcome_rank_sum_squares':str(yy)}
