"""Local-only frozen-protocol news audit. Never loads prices or computes correlations."""
import argparse,datetime as dt,decimal,hashlib,json,pathlib,re,unicodedata,urllib.parse
D=decimal.Decimal;UTC=dt.timezone.utc
def sha(b):return hashlib.sha256(b).hexdigest()
def strict_time(s):
 if not isinstance(s,str):raise ValueError('missing_or_nonstring_publication_clock')
 if re.fullmatch(r'[0-9]{8}T[0-9]{6}',s):return dt.datetime.strptime(s,'%Y%m%dT%H%M%S').replace(tzinfo=UTC),'AV_time_published_UTC_vendor_convention'
 if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|[+-][0-9]{2}:[0-9]{2})',s):raise ValueError('date_only_partial_naive_or_unsupported_clock')
 x=dt.datetime.fromisoformat(s.replace('Z','+00:00'));return x.astimezone(UTC),'explicit_timezone_second_precision'
def finite_score(x):
 if isinstance(x,bool) or x is None:raise ValueError('missing_or_boolean_score')
 try:d=D(str(x))
 except decimal.InvalidOperation:raise ValueError('nonnumeric_score')
 if not d.is_finite() or not D(-1)<=d<=D(1):raise ValueError('nonfinite_or_out_of_range_score')
 return d
def label(score):
 if score is None:return None
 return 'negative' if score<=D('-.15') else 'positive' if score>=D('.15') else 'neutral'
def canonical_url(raw):
 if not isinstance(raw,str):return None
 try:
  u=urllib.parse.urlsplit(raw.strip())
  if u.scheme.lower() not in ('http','https') or not u.hostname or u.username or u.password:return None
  tracking={'fbclid','gclid','dclid','msclkid','mc_cid','mc_eid','igshid','srsltid'}
  query=[(k,v) for k,v in urllib.parse.parse_qsl(u.query,keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in tracking]
  port=u.port;host=u.hostname.lower();netloc=host+(':'+str(port) if port and not((u.scheme.lower()=='https' and port==443)or(u.scheme.lower()=='http' and port==80)) else '')
  return urllib.parse.urlunsplit((u.scheme.lower(),netloc,u.path or '/',urllib.parse.urlencode(sorted(query)),''))
 except (ValueError,TypeError):return None
def normalized_headline(s):return ' '.join(unicodedata.normalize('NFKC',s).casefold().split()) if isinstance(s,str) else None
def article_audit(article,index,ticker,release):
 r={'index':index,'original_article':article,'original_article_sha256':sha(json.dumps(article,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()),'eligible_recorded_clock':False,'original_publication_independently_verified':False,'runtime_vintage_qualified':False,'manual_sign':'unknown','manual_sign_reason':'not manually reviewed; no price-based inference','SEC_flags':None,'exclusions':[],'score':None,'own_score_label':None,'canonical_url':None,'normalized_headline':None}
 if not isinstance(article,dict):r['exclusions'].append('article_not_object');return r
 r['canonical_url']=canonical_url(article.get('url'));r['normalized_headline']=normalized_headline(article.get('title'))
 if not r['canonical_url']:r['identity_warning']='missing_or_unusable_URL_manual_identity_validation_required'
 try:
  t,method=strict_time(article.get('time_published'));r['publication_utc']=t.isoformat();r['publication_clock_method']=method
  # Any additional explicit publication clock must agree. Updated-only times never substitute.
  for k in ['datePublished','published_at','original_publication_time']:
   if article.get(k) is not None:
    other,_=strict_time(article[k])
    if other!=t:raise ValueError('conflicting_publication_clocks')
  if t<release-dt.timedelta(hours=48):r['exclusions'].append('before_inclusive_48h_start')
  elif t>=release:r['exclusions'].append('at_or_after_exclusive_release')
  else:r['eligible_recorded_clock']=True;r['window']='recent' if t>=release-dt.timedelta(hours=24) else 'older'
 except ValueError as e:r['clock_uncertain']=True;r['exclusions'].append(str(e))
 entries=article.get('ticker_sentiment');matches=[z for z in entries if isinstance(z,dict) and z.get('ticker')==ticker] if isinstance(entries,list) else []
 r['exact_target_ticker_entries']=matches
 if len(matches)!=1:r['exclusions'].append('missing_exact_target_score' if not matches else 'ambiguous_multiple_exact_target_entries')
 else:
  match=matches[0];r['original_vendor_label']=match.get('ticker_sentiment_label');r['original_relevance_score']=match.get('relevance_score')
  try:d=finite_score(match.get('ticker_sentiment_score'));r['score']=str(d);r['own_score_label']=label(d)
  except ValueError as e:r['exclusions'].append(str(e))
 r['syndication_identity_status']='not_confirmed_from_full_original_source; manual_event_identity_validation_required'
 return r

def dedup(records):
 eligible=[r for r in records if r['eligible_recorded_clock']];parent={r['index']:r['index'] for r in eligible}
 def find(i):
  while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
  return i
 seen={}
 url_titles={}
 for r in eligible:
  if r['canonical_url'] and r['normalized_headline']:url_titles.setdefault(r['canonical_url'],set()).add(r['normalized_headline'])
 conflicts={u for u,titles in url_titles.items() if len(titles)>1}
 for r in eligible:
  r['ambiguous_same_URL_distinct_headlines']=r['canonical_url'] in conflicts
 for r in eligible:
  for typ,key in [('URL',r['canonical_url']),('headline',r['normalized_headline'])]:
   if key and not(typ=='URL' and key in conflicts):
    if (typ,key) in seen:parent[find(r['index'])]=find(seen[(typ,key)])
    else:seen[(typ,key)]=r['index']
 groups={}
 for r in eligible:groups.setdefault(find(r['index']),[]).append(r)
 result=[]
 for members in groups.values():
  # Original publisher cannot be established from AV source-name alone. Do not invent preference.
  rep=min(members,key=lambda r:(r['publication_utc'],r['canonical_url'] or '',r['index']))
  cid='story-'+str(min(r['index'] for r in members));windows=sorted({r['window'] for r in members})
  for r in members:r.update(cluster_id=cid,representative_index=rep['index'],dedup_representative=r['index']==rep['index'])
  result.append({'cluster_id':cid,'representative_index':rep['index'],'member_indices':[r['index'] for r in members],'representative_publication_utc':rep['publication_utc'],'representative_window':rep['window'],'member_windows':windows,'cross_24h_boundary_duplicate':len(windows)>1,'representative_score':None if any(r.get('ambiguous_same_URL_distinct_headlines') for r in members) else rep['score'],'identity_conflict_score_withheld':any(r.get('ambiguous_same_URL_distinct_headlines') for r in members),'original_publisher_preference':'unresolved; earliest eligible then lexical canonical URL, index stable tie-break','same_event_syndication_confirmed':False,'manual_identity_validation_required':True})
 return sorted(result,key=lambda c:(c['representative_publication_utc'],c['representative_index']))
def stats(clusters,window):
 chosen=[c for c in clusters if window=='full' or c['representative_window']==window];scores=[D(c['representative_score']) for c in chosen if c['representative_score'] is not None]
 mean=sum(scores,D(0))/len(scores) if scores else None
 return {'deduplicated_story_count':len(chosen),'numeric_story_count':len(scores),'missing_score_story_count':len(chosen)-len(scores),'provider_recorded_exploratory_mean':str(mean) if mean is not None else None,'own_frozen_label':label(mean),'positive_share':str(D(sum(s>=D('.15') for s in scores))/len(scores)) if scores else None,'negative_share':str(D(sum(s<=D('-.15') for s in scores))/len(scores)) if scores else None,'independently_verified_primary_mean':None,'independently_verified_primary_count':0}
def analyze_event(event,payload,request_status):
 release=dt.datetime.fromisoformat(event['release_at']).astimezone(UTC);result={'ticker':event['ticker'],'release_utc':release.isoformat(),'windows':{'full_start_inclusive':(release-dt.timedelta(hours=48)).isoformat(),'recent_start_inclusive':(release-dt.timedelta(hours=24)).isoformat(),'release_exclusive':release.isoformat()},'coverage':[],'historical_vintage':'historical_vintage_unknown','runtime_vintage_qualified':False,'public_original_publication_verification':'not independently verified by AV timestamps alone','correlations_computed':False}
 result['window_statistics']={w:{'deduplicated_story_count':None,'numeric_story_count':None,'missing_score_story_count':None,'provider_recorded_exploratory_mean':None,'own_frozen_label':None,'independently_verified_primary_mean':None,'independently_verified_primary_count':0} for w in ['full','recent','older']}
 if request_status=='not_collected':result['coverage']=['not_collected'];return result,[],[]
 if request_status!='success' or not isinstance(payload,dict) or any(k in payload for k in ['Information','Note','Error Message']) or not isinstance(payload.get('feed'),list):result['coverage']=['request_failed'];return result,[],[]
 feed=payload['feed'];records=[article_audit(a,i,event['ticker'],release) for i,a in enumerate(feed)];clusters=dedup(records);result['returned_article_count']=len(feed)
 if not feed:result['coverage'].append('valid_empty_provider_window')
 else:result['coverage'].append('observed_nonempty_not_proven_complete')
 try:declared=int(payload.get('items',len(feed)))
 except (ValueError,TypeError):declared=None
 if len(feed)>=1000 or declared is None or declared>len(feed):result['coverage'].append('partial_or_capped')
 if any(r.get('clock_uncertain') for r in records):result['coverage'].append('clock_uncertain')
 result['declared_items']=declared;result['window_statistics']={w:stats(clusters,w) for w in ['full','recent','older']};result['excluded_article_count']=sum(not r['eligible_recorded_clock'] for r in records);result['eligible_recorded_clock_articles']=sum(r['eligible_recorded_clock'] for r in records);result['duplicate_articles_removed']=result['eligible_recorded_clock_articles']-len(clusters);result['stories_requiring_manual_identity_validation']=len(clusters)
 recent=result['window_statistics']['recent']['provider_recorded_exploratory_mean'];older=result['window_statistics']['older']['provider_recorded_exploratory_mean'];result['recent_minus_older_mean']=str(D(recent)-D(older)) if recent is not None and older is not None else None
 return result,records,clusters
