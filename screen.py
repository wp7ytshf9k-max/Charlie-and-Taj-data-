"""Charlie & Taj rapid research screen v2.4: preliminary ranking, NOT betting approval."""
import csv, io, json, os, re, urllib.request
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

BASE = 'https://raw.githubusercontent.com/oladeeayo/open-matchday/master/'
TARGET = os.getenv('TARGET_DATE', '').strip() or date.today().isoformat()
datetime.strptime(TARGET, '%Y-%m-%d')
OUT = Path('output'); OUT.mkdir(exist_ok=True)
SEASON_START = int(TARGET[:4]) if int(TARGET[5:7]) >= 7 else int(TARGET[:4])-1
SEASON = f'{SEASON_START%100:02d}{(SEASON_START+1)%100:02d}'
RUN_ID = f'CT-{TARGET}-{datetime.utcnow().strftime("%H%M%S")}'

def get(path):
    req = urllib.request.Request(BASE + path, headers={'User-Agent':'CharlieTajResearch/2.4'})
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
        results = rows(f'data/{folder}/results_{SEASON}.csv')
        upcoming = rows(f'data/{folder}/fixtures_{SEASON}.csv')
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

raw_fixture_count=len(fixtures)
# Avoid duplicate source fixtures; do not merge similarly named clubs across competitions.
unique_fixtures = {}
for f in fixtures:
    key = (f['competition'],f['date'],norm(f['home']),norm(f['away']))
    unique_fixtures.setdefault(key,f)
fixtures = list(unique_fixtures.values())

def metrics(competition, team):
    recent = sorted(history.get((competition,norm(team)),[]),reverse=True)
    # Seven is preferred; five is an acceptable minimum.
    n = 7 if len(recent) >= 7 else 5 if len(recent) >= 5 else 0
    if not n:
        return None
    last = recent[:n]
    wins = sum(gf > ga for _,gf,ga in last)
    draws = sum(gf == ga for _,gf,ga in last)
    record = ''.join('W' if gf>ga else 'D' if gf==ga else 'L' for _,gf,ga in last)
    dots = ''.join({'W':'🟢','D':'🟠','L':'🔴'}[x] for x in record)
    return {'matches':n,'form':round(100*(3*wins+draws)/(3*n),2),
            'gf':sum(gf for _,gf,_ in last)/n,
            'ga':sum(ga for _,_,ga in last)/n,
            'record':record,'dots':dots}

outcomes = []
for fixture in fixtures:
    h = metrics(fixture['competition'],fixture['home'])
    a = metrics(fixture['competition'],fixture['away'])
    if h and a:
        diff = h['form']-a['form']
        attack = (h['gf']-a['gf'])*4
        defence = (a['ga']-h['ga'])*4
        scores = {
            'H':max(0,min(100,55+0.38*diff+attack+defence)),
            'A':max(0,min(100,45-0.38*diff-attack-defence)),
            'D':max(0,min(100,65-abs(diff)*0.55-abs(h['gf']-a['gf'])*4-abs(h['ga']-a['ga'])*4))}
        status = 'PROVISIONAL_FORM_ONLY'
    else:
        scores = {'H':None,'D':None,'A':None}
        status = 'INSUFFICIENT_LAST5'
    for outcome,score in scores.items():
        outcomes.append({**fixture,'outcome':outcome,
            'rapid_score':round(score,2) if score is not None else '',
            'home_form_dots':h['dots'] if h else '',
            'away_form_dots':a['dots'] if a else '',
            'home_form_record':h['record'] if h else '',
            'away_form_record':a['record'] if a else '',
            'home_matches_used':h['matches'] if h else 0,
            'away_matches_used':a['matches'] if a else 0,
            'home_form_score':h['form'] if h else '',
            'away_form_score':a['form'] if a else '',
            'status':status,'qc_gate':'AMBER_MISSING_CRITICAL_EVIDENCE',
            'probability':'','odds':'','ev':'','qc_score':'','risk_index':'','p_home':'','p_draw':'','p_away':'',
            'missing_evidence':'calibrated probability; current team news; bookmaker odds; Sky Bet market; kickoff verification'})

eligible = [r for r in outcomes if isinstance(r['rapid_score'],(float,int))]
selected = []
used = set()
def fixture_key(r):
    return (r['competition'],r['date'],norm(r['home']),norm(r['away']))

def pick(pool,count,outcome=None,reverse=False):
    if count <= 0:
        return
    choices = [r for r in eligible if (outcome is None or r['outcome']==outcome) and fixture_key(r) not in used]
    choices.sort(key=lambda r:(float(r['rapid_score']),r['competition'],r['home'],r['away']),reverse=not reverse)
    picked = 0
    for r in choices:
        key = fixture_key(r)
        if key in used:
            continue  # Another outcome from this fixture may already have been picked in this pool.
        selected.append({'pool':pool,**r})
        used.add(key)
        picked += 1
        if picked >= count:
            break

# 47 slots are a TARGET, not a requirement to fabricate candidates.
pick('Builder',3)
pick('Master',6,'H'); pick('Master',2,'D'); pick('Master',4,'A')
# Moonshot requires independent odds/upset model; these are only watchlist possibilities.
pick('Moonshot research',12,reverse=True)
pick('Backup',20)

fields = ['pool','competition','date','time','home','away','outcome','rapid_score',
          'home_form_dots','away_form_dots','home_form_record','away_form_record',
          'home_matches_used','away_matches_used','home_form_score','away_form_score','status','qc_gate',
          'probability','odds','ev','qc_score','risk_index','p_home','p_draw','p_away','missing_evidence']
with (OUT/'shortlist.csv').open('w',newline='',encoding='utf-8') as f:
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(selected)
with (OUT/'all_outcomes.csv').open('w',newline='',encoding='utf-8') as f:
    writer=csv.DictWriter(f,fieldnames=fields[1:]);writer.writeheader();writer.writerows(outcomes)
counts={pool:sum(r['pool']==pool for r in selected) for pool in ['Builder','Master','Moonshot research','Backup']}
summary={'date':TARGET,'version':'rapid-screen-v2.4','run_id':RUN_ID,'season':SEASON,'competitions_discovered':len(folders),
    'competitions_failed':len(errors),'fixtures_loaded':len(fixtures),
    'outcomes_generated':len(outcomes),'outcomes_with_adequate_form':len(eligible),
    'fixtures_using_five_match_fallback':sum(1 for f in fixtures if (lambda h,a: bool(h and a and (h['matches']==5 or a['matches']==5)))(metrics(f['competition'],f['home']),metrics(f['competition'],f['away']))),
    'shortlist_count':len(selected),'target_count':47,'target_filled':len(selected)==47,
    'pool_counts':counts,'duplicate_fixtures_in_shortlist':len(selected)-len(used),
    'unique_shortlist_fixtures':len(used),
    'green_gates':0,'qc_watch_handover':'NOT_CONNECTED','cross_source_dedup':'NOT_TESTED',
    'coverage_target':500,'below_500_is_failure':False,
    'source_fixture_duplicates_removed':raw_fixture_count-len(fixtures),
    'unfilled_slots':{'Builder':max(0,3-counts['Builder']),'Master':max(0,12-counts['Master']),'Moonshot':max(0,12-counts['Moonshot research']),'Backup':max(0,20-counts['Backup'])},'source_scope':'Open Matchday only; additional worldwide websites NOT integrated',
    'note':'Form5/7 ranking is a heuristic, NOT a calibrated 1X2 probability. No validated moonshot odds/EV or Sky Bet checks. Every leg AMBER; no approved bets.',
    'errors':errors}
if len(selected) != len(used):
    raise RuntimeError('QC FAILURE: duplicate fixtures in shortlist')
(OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))

# Human-readable review file; no approval implied.
with (OUT/'review.md').open('w',encoding='utf-8') as f:
    f.write(f"# Charlie & Taj provisional research — {TARGET}\n\n")
    f.write(f"Version 2.4 | {len(fixtures)} source fixtures | {len(selected)}/47 unique candidates | 0 verified GREEN gates\n\n")
    f.write("Scores are heuristic, NOT probabilities. 🟢 win, 🟠 draw, 🔴 loss; most recent first.\n\n")
    f.write("| Pool | Match | Pick | Home form | Away form | Score | QC |\n|---|---|---|---|---|---:|---|\n")
    for r in selected:
        f.write(f"| {r['pool']} | {r['home']} vs {r['away']} | {r['outcome']} | {r['home_form_dots']} | {r['away_form_dots']} | {r['rapid_score']} | AMBER |\n")

# Explicit handover contract: QC must not treat this artifact as a completed handover.
from collections import Counter
ids={'Builder':'B','Master':'M','Moonshot research':'U','Backup':'BK'}
numbered=Counter()
with (OUT/'handover.txt').open('w',encoding='utf-8') as f:
    f.write(f'HANDOVER START\nRUN_ID={RUN_ID}\nTARGET_DATE={TARGET}\nMODEL=rapid-screen-v2.4\n')
    f.write('STATUS=PROVISIONAL_RESEARCH_ONLY; QC_WATCH_ACCESS=NOT_VERIFIED\n')
    f.write('SOURCE_SCOPE=Open Matchday only; worldwide multi-source intake NOT integrated\n')
    f.write('QC_STATUS=NO_GREEN_APPROVALS; probability/odds/EV/market checks NOT VERIFIED\n')
    for pool,goal in [('Builder',3),('Master',12),('Moonshot research',12),('Backup',20)]:
        pool_rows=[r for r in selected if r['pool']==pool]
        f.write(f'POOL={pool}; ACTUAL={len(pool_rows)}; TARGET={goal}; VACANCIES={goal-len(pool_rows)}\n')
        for r in pool_rows:
            numbered[pool]+=1
            id_=f'{ids[pool]}{numbered[pool]:02d}'
            f.write(f'{id_} | {r["competition"]} | {r["date"]} {r["time"]} | {r["home"]} v {r["away"]} | {r["outcome"]} | form={r["home_form_record"]}/{r["away_form_record"]} | heuristic={r["rapid_score"]} | AMBER | MISSING={r["missing_evidence"]}\n')
    f.write('HANDOVER END\n')
# A machine-readable receipt is a source file, not proof that a downstream task received it.
(OUT/'qc_watch_contract.json').write_text(json.dumps({'run_id':RUN_ID,'handover_created':True,'qc_watch_received':False,'three_pools_present':True,'green_approved':0,'source_scope':'Open Matchday'},indent=2),encoding='utf-8')
