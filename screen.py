"""Charlie & Taj rapid research screen v2: preliminary ranking, NOT betting approval."""
import csv, io, json, os, re, urllib.request
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

BASE = 'https://raw.githubusercontent.com/oladeeayo/open-matchday/master/'
TARGET = os.getenv('TARGET_DATE', date.today().isoformat())
datetime.strptime(TARGET, '%Y-%m-%d')
OUT = Path('output'); OUT.mkdir(exist_ok=True)

def get(path):
    req = urllib.request.Request(BASE + path, headers={'User-Agent':'CharlieTajResearch/2.0'})
    with urllib.request.urlopen(req, timeout=35) as response:
        return response.read().decode('utf-8-sig')

def rows(path):
    return list(csv.DictReader(io.StringIO(get(path))))

def norm(value):
    return re.sub(r'[^a-z0-9]', '', str(value).lower())

index = get('LEAGUE_INDEX.md')
folders = sorted(set(re.findall(r'\b[A-Z]{2,5}_[1-9]_[a-z0-9-]+\b', index)))
if not folders:
    raise RuntimeError('No league folders parsed from LEAGUE_INDEX.md')

fixtures = []
history = defaultdict(list)
errors = []
for folder in folders:
    try:
        results = rows(f'data/{folder}/results_2627.csv')
        upcoming = rows(f'data/{folder}/fixtures_2627.csv')
        for r in results:
            match_date = r.get('date', '')
            if not match_date or match_date >= TARGET:
                continue
            try:
                home_goals, away_goals = int(r['ft_home']), int(r['ft_away'])
                home_team, away_team = r['home'], r['away']
            except (ValueError, KeyError, TypeError):
                continue
            history[(folder, norm(home_team))].append((match_date, home_goals, away_goals))
            history[(folder, norm(away_team))].append((match_date, away_goals, home_goals))
        for r in upcoming:
            if r.get('date') == TARGET and r.get('home') and r.get('away'):
                fixtures.append({'competition':folder,'date':TARGET,'time':r.get('time',''),
                                 'home':r['home'],'away':r['away']})
    except Exception as exc:
        errors.append({'competition':folder,'error':str(exc)[:160]})

# Avoid duplicate source fixtures; do not merge similarly named clubs across competitions.
unique_fixtures = {}
for f in fixtures:
    key = (f['competition'],f['date'],norm(f['home']),norm(f['away']))
    unique_fixtures.setdefault(key,f)
fixtures = list(unique_fixtures.values())

def metrics(competition, team):
    last = sorted(history.get((competition,norm(team)),[]),reverse=True)[:7]
    if len(last) < 7:
        return None
    wins = sum(gf > ga for _,gf,ga in last)
    draws = sum(gf == ga for _,gf,ga in last)
    return {'form7':round(100*(3*wins+draws)/21,2),
            'gf':sum(gf for _,gf,_ in last)/7,
            'ga':sum(ga for _,_,ga in last)/7,
            'record7':''.join('W' if gf>ga else 'D' if gf==ga else 'L' for _,gf,ga in last)}

outcomes = []
for fixture in fixtures:
    h = metrics(fixture['competition'],fixture['home'])
    a = metrics(fixture['competition'],fixture['away'])
    if h and a:
        diff = h['form7']-a['form7']
        attack = (h['gf']-a['gf'])*4
        defence = (a['ga']-h['ga'])*4
        scores = {
            'H':max(0,min(100,55+0.38*diff+attack+defence)),
            'A':max(0,min(100,45-0.38*diff-attack-defence)),
            'D':max(0,min(100,65-abs(diff)*0.55-abs(h['gf']-a['gf'])*4-abs(h['ga']-a['ga'])*4))}
        status = 'PROVISIONAL_FORM7_ONLY'
    else:
        scores = {'H':None,'D':None,'A':None}
        status = 'INSUFFICIENT_LAST7'
    for outcome,score in scores.items():
        outcomes.append({**fixture,'outcome':outcome,
            'rapid_score':round(score,2) if score is not None else '',
            'home_last7':h['record7'] if h else '',
            'away_last7':a['record7'] if a else '',
            'home_form7':h['form7'] if h else '',
            'away_form7':a['form7'] if a else '',
            'status':status,'qc_gate':'NOT_ASSESSED',
            'probability':'','odds':'','ev':'',
            'missing_evidence':'calibrated probability; current team news; bookmaker odds; Sky Bet market; kickoff verification'})

eligible = [r for r in outcomes if isinstance(r['rapid_score'],(float,int))]
selected = []
used = set()
def fixture_key(r):
    return (r['competition'],r['date'],norm(r['home']),norm(r['away']))

def pick(pool,count,outcome=None,reverse=False):
    choices = [r for r in eligible if (outcome is None or r['outcome']==outcome) and fixture_key(r) not in used]
    choices.sort(key=lambda r:(float(r['rapid_score']),r['competition'],r['home'],r['away']),reverse=not reverse)
    for r in choices[:count]:
        selected.append({'pool':pool,**r})
        used.add(fixture_key(r))

# 47 slots are a TARGET, not a requirement to fabricate candidates.
pick('Builder',3)
pick('Master',6,'H'); pick('Master',2,'D'); pick('Master',4,'A')
# Moonshot requires independent odds/upset model; these are only watchlist possibilities.
pick('Moonshot research',12,reverse=True)
pick('Backup',20)

fields = ['pool','competition','date','time','home','away','outcome','rapid_score',
          'home_last7','away_last7','home_form7','away_form7','status','qc_gate',
          'probability','odds','ev','missing_evidence']
with (OUT/'shortlist.csv').open('w',newline='',encoding='utf-8') as f:
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(selected)
with (OUT/'all_outcomes.csv').open('w',newline='',encoding='utf-8') as f:
    writer=csv.DictWriter(f,fieldnames=fields[1:]);writer.writeheader();writer.writerows(outcomes)
counts={pool:sum(r['pool']==pool for r in selected) for pool in ['Builder','Master','Moonshot research','Backup']}
summary={'date':TARGET,'version':'rapid-screen-v2','competitions_discovered':len(folders),
    'competitions_failed':len(errors),'fixtures_loaded':len(fixtures),
    'outcomes_generated':len(outcomes),'outcomes_with_last7':len(eligible),
    'shortlist_count':len(selected),'target_count':47,'target_filled':len(selected)==47,
    'pool_counts':counts,'duplicate_fixtures_in_shortlist':len(selected)-len(used),
    'green_gates':0,'source_scope':'Open Matchday only; NOT worldwide 368-fixture coverage',
    'note':'Form7 ranking is a heuristic, NOT a calibrated 1X2 probability. No validated moonshot odds/EV or Sky Bet checks. All QC gates NOT_ASSESSED.',
    'errors':errors}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
