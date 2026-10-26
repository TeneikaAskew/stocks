"""New7 descriptive join and predeclared daily sampling only; no native/runtime calls."""
from pathlib import Path as _Path
from research_io import selected_root, mapped_path as Path
from decimal import Decimal as D,localcontext
import json,csv,hashlib,datetime as dt,collections
from frozen_rank_rules import spearman
O=selected_root()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_text(),parse_float=D)
def csvwrite(path,rows):
 with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def sign(v):return 1 if v>0 else -1 if v<0 else 0
def main():
 out=O/'descriptive-results';out.mkdir(exist_ok=False)
 f=load(O/'pre-join-code-freeze.json')
 for path,h in f['sources'].items():assert sha(path)==h,path
 nf=load(O/'news-results/news-computation-freeze.json');assert sha(O/'news-results/events.json')==nf['events_sha256']
 proto=load(O/'frozen-analysis-protocol.json');order=proto['order'];news={e['ticker']:e for e in load(O/'news-results/events.json')};source=Path(f['existing_daily_root']);p=load(source/'selector-protocol-freeze.json');metadata={c['ticker']:c for c in p['cases']};existing={r['ticker']:r for r in load(source/'comparison-results.json')['rows']}
 frozen_inputs=load(O/'pre-outcome-input-freeze.json')['sources'];frozen={r['path']:r for r in frozen_inputs}
 for item in frozen_inputs:assert sha(item['path'])==item['sha256'],item['path']
 rows=[]
 for t in order:
  e=news[t];s=e['window_statistics']['full'];r=existing[t];rows.append({'ticker':t,'numeric_news_stories':s['numeric_story_count'],'vendor_full48h_mean':s['provider_recorded_exploratory_mean'],'vendor_mean_label':s['own_frozen_label'],'existing_opening_gap_pct':str(r['target_opening_gap_pct']),'existing_native_five_day_sustain_pct':str(r['target_native_sustain_5d_pct']),'primary_publisher_qualified_mean':None,'news_coverage':';'.join(e['coverage']),'source_outcome_sha256':sha(source/'comparison-results.json')})
 pairs=[r for r in rows if r['vendor_full48h_mean'] is not None]
 correlations={}
 for label,key in [('opening_gap','existing_opening_gap_pct'),('native_five_day_sustain','existing_native_five_day_sustain_pct')]:
  x=[D(r['vendor_full48h_mean']) for r in pairs];y=[D(r[key]) for r in pairs]
  correlations[label]=spearman(x,y) if len(pairs)>=2 else {'n':len(pairs),'rho_decimal50':None,'reason':'fewer_than_two_usable_pairs'}
 episodes=[];steps=[];months=set();cash_count=0
 for t in order:
  c=metadata[t];files=sorted((source/'prior-projection-v1').glob(t+'-*-prior-selected.json'))+list((source/'target-projection-v2').glob(t+'-*-target-selected.json'));assert len(files)==5
  for path in files:
   assert str(path) in frozen and sha(path)==frozen[str(path)]['sha256'];data=load(path);event=data['event'];date=event['reported_date'];role='target' if 'target-selected' in path.name else 'prior';basis=event['timing_sources'][0]['basis'];raw=data['raw_rows'];dates=[x['date'] for x in raw];assert len(raw)==16 and len(set(dates))==16 and dates==sorted(dates)
   i=dates.index(date);assert i==10;reaction=i if basis=='BMO' else i+1;baseline=i-1 if basis=='BMO' else i;end=i+5;assert end==15
   if role=='prior':
    m=next(x for x in c['candidates'] if x['event']['event_id']==event['event_id']);assert m['dates']==dates;assert dt.date.fromisoformat(dates[end])<dt.date.fromisoformat(c['target_event_exact']['release_date']);maturity=m['maturity']
   else:assert date==c['target_event_exact']['release_date'];assert dates[end]==c['target_calendar_anchors']['native_Dplus5_close'];assert dates[reaction]==c['target_calendar_anchors']['reaction_open'];maturity='completed_historical_window_current_recovery'
   values={}
   for row in raw[baseline:end+1]:
    v={k:D(x) for k,x in row['raw_provider_values'].items()};assert all(x.is_finite() for x in v.values());assert min(v[k] for k in ['1. open','2. high','3. low','4. close'])>0;assert v['3. low']<=min(v['1. open'],v['4. close'])<=max(v['1. open'],v['4. close'])<=v['2. high'];assert v['6. volume']>=0 and v['7. dividend amount']>=0 and v['8. split coefficient']==1
    values[row['date']]=v
   prev=values[dates[baseline]]['4. close'];op=values[dates[reaction]]['1. open'];gap=100*(op/prev-1);gs=sign(gap);firstrev=None;firstfill=None;counts=collections.Counter();previous=op;divs=[]
   for j,datekey in enumerate(dates[reaction:end+1]):
    v=values[datekey];close=v['4. close'];step=close-previous;relation='unavailable_zero_gap' if gs==0 else 'flat' if step==0 else 'continuation' if sign(step)==gs else 'opposite_to_gap';counts[relation]+=1
    if relation=='opposite_to_gap' and firstrev is None:firstrev=datekey
    if gs and firstfill is None and ((gs>0 and close<=prev) or (gs<0 and close>=prev)):firstfill=datekey
    if v['7. dividend amount']!=0:divs.append({'date':datekey,'cash_dividend':str(v['7. dividend amount'])})
    months.add((t,datekey[:7]));steps.append({'ticker':t,'role':role,'event_id':event['event_id'],'session':datekey,'step_ordinal':j,'comparison':'reaction_open_to_close' if j==0 else 'previous_close_to_close','step_pct':str(100*(close/previous-1)),'relation_to_initial_gap':relation,'daily_close_gapfill':gs!=0 and ((gs>0 and close<=prev)or(gs<0 and close>=prev)),'source_selected_sha256':sha(path),'time_resolution':'session_date_only_no_intraday_duration_inference'});previous=close
   cash_count+=len(divs);episodes.append({'ticker':t,'role':role,'event_id':event['event_id'],'release_ts':event['release_ts'],'timing':basis,'baseline_session':dates[baseline],'reaction_session':dates[reaction],'horizon_Dplus5':dates[end],'daily_closing_observations':end-reaction+1,'opening_gap_pct':str(gap),'opening_gap_sign':gs,'first_opposite_closing_step_session':firstrev,'daily_reversal_observed':None if gs==0 else firstrev is not None,'daily_reversal_right_censored':None if gs==0 else firstrev is None,'first_gapfill_close_session':firstfill,'gapfill_right_censored':None if gs==0 else firstfill is None,'continuation_steps':counts['continuation'],'opposite_steps':counts['opposite_to_gap'],'flat_steps':counts['flat'],'zero_gap_unavailable_steps':counts['unavailable_zero_gap'],'cash_dividends_nominal':divs,'split_coefficients_actual_all_one':True,'maturity':maturity,'current_vintage_only':True,'source_selected_sha256':sha(path),'source_private_path':str(path),'source_original_sha256':data['source_provenance']['raw_sha256'],'raw_prices_adjusted_for_cash_dividends':False})
 assert len(episodes)==35 and sum(e['role']=='prior' for e in episodes)==28
 result={'status':'NEW7_POSTHOC_VENDOR_ONLY_DESCRIPTIVE','news_freeze_sha256':sha(O/'news-results/news-computation-freeze.json'),'exact_two_spearman':correlations,'paired_tickers':[r['ticker'] for r in pairs],'rows':rows,'publisher_qualified_primary_pairs':0,'new_native_model_calls':0,'daily_episode_count':35,'daily_step_count':len(steps),'intraday_ticker_month_minimum_full_episode_windows':len(months),'intraday_ticker_months_full_episode_windows':[{'ticker':t,'month':m} for t,m in sorted(months)],'target_reaction_only_intraday_ticker_month_minimum':len({(e['ticker'],e['reaction_session'][:7]) for e in episodes if e['role']=='target'}),'cash_dividend_event_rows_recorded':cash_count,'limits':'Vendor-current-vintage scores; publication/syndication unverified. Daily sampled first opposite closing step is not continuous/intraday reversal time, tradable return, predictive accuracy or causal effect. No old sample rerun.'}
 for n,d in [('comparison.json',result),('daily-episodes-private.json',episodes),('daily-steps.json',steps)]: (out/n).write_text(json.dumps(d,indent=2,default=str)+'\n')
 csvwrite(out/'seven-news-and-existing-outcomes.csv',rows);csvwrite(out/'daily-closing-steps.csv',steps)
 public=[]
 for e in episodes:public.append({k:v for k,v in e.items() if k not in ['source_private_path','source_original_sha256','maturity','cash_dividends_nominal']})
 csvwrite(out/'daily-episode-summary.csv',public)
 (out/'execution-receipt.json').write_text(json.dumps({'finished_at':dt.datetime.now(dt.timezone.utc).isoformat(),'status':result['status'],'spearman_calls':2,'new_provider_calls':0,'raw_original_reads':0,'daily_episodes':35,'steps':len(steps),'code_freeze_sha256':sha(O/'pre-join-code-freeze.json')},indent=2)+'\n')
 print(json.dumps({'correlations':correlations,'daily_episodes':35,'daily_steps':len(steps),'minimum_intraday_ticker_months':len(months)}))
if __name__=='__main__':main()
