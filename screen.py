import csv, io, json, os, re, urllib.request
from pathlib import Path
from datetime import date
from collections import defaultdict

BASE='https://raw.githubusercontent.com/oladeeayo/open-matchday/master/'
TARGET=os.getenv('TARGET_DATE',date.today().isoformat())
OUT=Path('output'); OUT.mkdir(exist_ok=True)

def get(path):
    req=urllib.request.Request(BASE+path,headers={'User-Agent':'CharlieTajResearch/1.0'})
    with urllib.request.urlopen(req,timeout=35) as r:return r.read().decode('utf-8-sig')

def rows(path):return list(csv.DictReader(io.StringIO(get(path))))

def norm(x):return re.sub(r'[^a-z0-9]','',x.lower())

index=get('LEAGUE_INDEX.md')
folders=sorted(set(re.findall(r'\b[A-Z]{2,5}_[1-9]_[a-z0-9-]+\b',index)))
if not folders:raise RuntimeError('No league folders parsed; check index format')
fixtures=[]; history=defaultdict(list); errors=[]
for folder in folders:
    try:
        res=rows(f'data/{folder}/results_2627.csv')
        fix=rows(f'data/{folder}/fixtures_2627.csv')
        for r in res:
            if r.get('date','')>=TARGET:continue
            try:h,a=int(r['ft_home']),int(r['ft_away'])
            except (ValueError,KeyError,TypeError):continue
            for side,team,gf,ga in [('H',r['home'],h,a),('A',r['away'],a,h)]:
                history[(folder,norm(team))].append((r['date'],gf,ga,side))
        for r in fix:
            if r.get('date')==TARGET:
                fixtures.append({'competition':folder,'date':r['date'],'time':r.get('time',''),'home':r['home'],'away':r['away']})
    except Exception as e:errors.append({'competition':folder,'error':str(e)[:160]})

def metrics(folder,team):
    last=sorted(history.get((folder,norm(team)),[]),reverse=True)[:5]
    if len(last)<5:return None
    wins=sum(gf>ga for _,gf,ga,_ in last); draws=sum(gf==ga for _,gf,ga,_ in last)
    return {'form5':round(100*(3*wins+draws)/15,2),'gf':sum(x[1] for x in last)/5,'ga':sum(x[2] for x in last)/5,'record':''.join('W' if gf>ga else 'D' if gf==ga else 'L' for _,gf,ga,_ in last)}

out=[]
for f in fixtures:
    h=metrics(f['competition'],f['home']); a=metrics(f['competition'],f['away'])
    # A form-based triage heuristic only; not a calibrated 1X2 probability or official TSI.
    if h and a:
        diff=h['form5']-a['form5']; attack=(h['gf']-a['gf'])*4; defence=(a['ga']-h['ga'])*4
        home_score=max(0,min(100,50+0.38*diff+attack+defence+5))
        away_score=max(0,min(100,50-0.38*diff-attack-defence-5))
        draw_score=max(0,min(100,65-abs(diff)*0.55-abs(h['gf']-a['gf'])*4-abs(h['ga']-a['ga'])*4))
        status='PROVISIONAL_FORM_ONLY'
    else:home_score=away_score=draw_score=None;status='INSUFFICIENT_LAST5'
    for outcome,score in [('H',home_score),('D',draw_score),('A',away_score)]:
        out.append({**f,'outcome':outcome,'rapid_score':round(score,2) if score is not None else '',
                    'home_last5':h['record'] if h else '', 'away_last5':a['record'] if a else '',
                    'home_form5':h['form5'] if h else '', 'away_form5':a['form5'] if a else '',
                    'status':status,'qc_gate':'NOT_ASSESSED','probability':'','odds':'','ev':''})

eligible=[r for r in out if r['rapid_score']!='']
used=set(); selected=[]
def pick(pool,n,outcome=None,reverse=False):
    choices=[r for r in eligible if (outcome is None or r['outcome']==outcome) and (r['competition'],r['home'],r['away']) not in used]
    choices.sort(key=lambda r:float(r['rapid_score']),reverse=not reverse)
    for r in choices[:n]:
        selected.append({'pool':pool,**r});used.add((r['competition'],r['home'],r['away']))

# Builder excludes draws; Master enforces 6H/2D/4A; Moonshot is a WATCHLIST only
pick('Builder',3)
pick('Master',6,'H');pick('Master',2,'D');pick('Master',4,'A')
# Low form-score outcomes are NOT an odds-based moonshot ranking.
pick('Moonshot research',12,reverse=True)
pick('Backup',20)
fields=['pool','competition','date','time','home','away','outcome','rapid_score','home_last5','away_last5','home_form5','away_form5','status','qc_gate','probability','odds','ev']
with (OUT/'shortlist.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(selected)
with (OUT/'all_outcomes.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields[1:]);w.writeheader();w.writerows(out)
summary={'date':TARGET,'competitions_discovered':len(folders),'competitions_failed':len(errors),'fixtures_loaded':len(fixtures),'outcomes_generated':len(out),'outcomes_with_last5':len(eligible),'shortlist_count':len(selected),'pool_counts':{p:sum(x['pool']==p for x in selected) for p in ['Builder','Master','Moonshot research','Backup']},'green_gates':0,'note':'Heuristic scores are NOT calibrated win probabilities, TSI or betting recommendations. Moonshot lacks odds and EV. No automated Sky Bet validation.','errors':errors}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
