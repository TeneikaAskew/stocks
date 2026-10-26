"""Frozen-rule NEWS-only computation. Does not open daily results or price files."""
from pathlib import Path as _Path
from research_io import selected_root, mapped_path as Path, check_new7_protocol
import json,hashlib,datetime as dt,csv
from frozen_news_rules import analyze_event
O=selected_root()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 assert not (O/'news-results').exists()
 freeze=json.loads((O/'analysis-code-freeze.json').read_text())
 for p,h in freeze['news_sources'].items():assert sha(O/p)==h
 protocol=check_new7_protocol(json.loads((O/'frozen-analysis-protocol.json').read_text()));r=json.loads((O/'acquisition/batch-receipt.json').read_text());requests={q['call_id']:q for q in r['requests']}
 out=O/'news-results';out.mkdir();events=[];articles=[];clusters=[]
 for event in protocol['events']:
  q=requests.get(event['ticker']);payload=None;status='not_collected'
  if q:
   status='success' if q.get('status')=='HTTP200_NEWS_FEED_CAPTURED_COVERAGE_ONLY' else 'failure'
   if status=='success':assert sha(q['raw_path'])==q['raw_sha256'];payload=json.loads(Path(q['raw_path']).read_text())
  e,a,c=analyze_event(event,payload,status);e['acquired_at_current']=q.get('ended_at') if q else None;e['raw_sha256']=q.get('raw_sha256') if q else None
  events.append(e);articles.extend({'ticker':event['ticker'],**x} for x in a);clusters.extend({'ticker':event['ticker'],**x} for x in c)
 for n,d in [('events.json',events),('article-audit-private.json',articles),('clusters-private.json',clusters)]: (out/n).write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
 rows=[]
 for e in events:
  row={'ticker':e['ticker'],'release_utc':e['release_utc'],'coverage':';'.join(e['coverage']),'returned_articles':e.get('returned_article_count'),'removed_duplicates':e.get('duplicate_articles_removed'),'excluded_articles':e.get('excluded_article_count')}
  for w,st in e['window_statistics'].items():row.update({w+'_n':st['numeric_story_count'],w+'_mean':st['provider_recorded_exploratory_mean'],w+'_label':st['own_frozen_label']})
  row['independently_publisher_qualified_primary_mean']=None;rows.append(row)
 with (out/'seven-news-window-statistics.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 result={'at_current_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'NEWS_FROZEN_BEFORE_NEW_JOIN','batch_receipt_sha256':sha(O/'acquisition/batch-receipt.json'),'source_freeze_sha256':sha(O/'analysis-code-freeze.json'),'correlation_calls':0,'price_reads':0,'events_sha256':sha(out/'events.json'),'article_audit_sha256':sha(out/'article-audit-private.json'),'clusters_sha256':sha(out/'clusters-private.json'),'primary_qualified':0,'event_count':7,'source_receipts':[{k:q.get(k) for k in ['call_id','raw_sha256','raw_bytes','status','started_at','ended_at']} for q in r['requests']]}
 (out/'news-computation-freeze.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(rows))
if __name__=='__main__':main()
