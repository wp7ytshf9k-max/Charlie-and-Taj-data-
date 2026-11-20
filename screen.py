"""Charlie & Taj Rapid Screen v2.5 — provisional research, not betting approval.

Compatible with existing GitHub workflow: python screen.py; artifacts in output/.
QMS reference: CT-QMS-001 v3.73. No invented odds, probabilities or QC approvals.
"""
import csv
import io
import json
import math
import os
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

BASE = 'https://raw.githubusercontent.com/oladeeayo/open-matchday/master/'
TARGET = os.getenv('TARGET_DATE', '').strip() or date.today().isoformat()
datetime.strptime(TARGET, '%Y-%m-%d')
OUT = Path('output')
OUT.mkdir(exist_ok=True)
SEASON_START = int(TARGET[:4]) if int(TARGET[5:7]) >= 7 else int(TARGET[:4]) - 1
SEASON = f'{SEASON_START % 100:02d}{(SEASON_START + 1) % 100:02d}'
RUN_ID = f'CT-{TARGET}-{datetime.now(timezone.utc).strftime("%H%M%S")}'
MODEL = 'rapid-screen-v2.5'
WEIGHTS = {'F': 0.30, 'M': 0.25, 'S': 0.20, 'C': 0.15, 'V': 0.10}


def get(path):
    req = urllib.request.Request(BASE + path, headers={'User-Agent': 'CharlieTajResearch/2.5'})
    with urllib.request.urlopen(req, timeout=35) as response:
        return response.read().decode('utf-8-sig')


def rows(path):
    return list(csv.DictReader(io.StringIO(get(path))))


def norm(value):
    return re.sub(r'[^a-z0-9]', '', str(value).lower())


def clamp(value):
    return max(0.0, min(100.0, float(value)))


def metrics(competition, team, history):
    recent = sorted(history.get((competition, norm(team)), []), reverse=True)
    n = 7 if len(recent) >= 7 else 5 if len(recent) >= 5 else 0
    if not n:
        return None
    last = recent[:n]
    wins = sum(gf > ga for _, gf, ga in last)
    draws = sum(gf == ga for _, gf, ga in last)
    record = ''.join('W' if gf > ga else 'D' if gf == ga else 'L' for _, gf, ga in last)
    dots = ''.join({'W': '🟢', 'D': '🟠', 'L': '🔴'}[x] for x in record)
    return {'matches': n, 'form': round(100 * (3 * wins + draws) / (3 * n), 2),
            'gf': sum(gf for _, gf, _ in last) / n,
            'ga': sum(ga for _, _, ga in last) / n,
            'record': record, 'dots': dots}


def provisional_form_score(home, away, outcome):
    """Uncalibrated form-based screening score, NOT a probability or CR-FOS."""
    diff = home['form'] - away['form']
    attack = (home['gf'] - away['gf']) * 4
    defence = (away['ga'] - home['ga']) * 4
    scores = {
        'H': 55 + 0.38 * diff + attack + defence,
        'A': 45 - 0.38 * diff - attack - defence,
        'D': 65 - abs(diff) * 0.55 - abs(home['gf'] - away['gf']) * 4
             - abs(home['ga'] - away['ga']) * 4,
    }
    return round(clamp(scores[outcome]), 2)


def verified_fos(components):
    """Full CR-FOS only when ALL independently evidenced components exist."""
    if any(components.get(key) is None for key in WEIGHTS):
        return None
    return round(sum(WEIGHTS[key] * clamp(components[key]) for key in WEIGHTS), 2)


def fixture_key(item):
    return (item['competition'], item['date'], norm(item['home']), norm(item['away']))


def choose(outcomes):
    """Unique fixtures across ALL pools; Master has NO fixed H/D/A quota.

    Moonshot is a research watchlist only: draws/away outcomes get upset review
    priority, but cannot be declared high-value without actual odds and evidence.
    """
    eligible = [r for r in outcomes if isinstance(r['rapid_score'], (int, float))]
    used = set()
    selected = []

    def add(pool, count, candidates):
        for row in candidates:
            key = fixture_key(row)
            if key in used:
                continue
            selected.append({'pool': pool, **row})
            used.add(key)
            if sum(r['pool'] == pool for r in selected) >= count:
                break

    # Keep the strongest outcome per fixture, rather than selecting multiple sides.
    ranked = sorted(eligible, key=lambda r: (-r['rapid_score'], r['competition'], r['home'], r['away'], r['outcome']))
    add('Builder', 3, ranked)
    add('Master', 12, ranked)

    # A plausible upset watchlist is not an odds-based Moonshot model.
    # Prefer higher-scoring away/draw hypotheses, never intentionally select
    # the worst scores; QC must obtain market odds and evaluate upside/EV.
    upset_watch = sorted(eligible, key=lambda r: (
        -(r['rapid_score'] if r['outcome'] in ('A', 'D') else -1),
        r['competition'], r['home'], r['away'], r['outcome']))
    add('Moonshot research', 12, upset_watch)
    add('Backup', 20, ranked)
    assert len(selected) == len(used), 'Duplicate fixture in shortlist'
    return selected


def write_csv(path, records, fields):
    with (OUT / path).open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)


def main():
    index = get('LEAGUE_INDEX.md')
    folders = sorted(set(re.findall(r'\b[A-Z]{2,5}_[1-9]_[a-z0-9-]+\b', index)))
    if not folders:
        raise RuntimeError('No league folders parsed from LEAGUE_INDEX.md')
    fixtures, history, errors = [], defaultdict(list), []
    for folder in folders:
        try:
            results = rows(f'data/{folder}/results_{SEASON}.csv')
            upcoming = rows(f'data/{folder}/fixtures_{SEASON}.csv')
            for record in results:
                match_date = record.get('date', '')
                if not match_date or match_date >= TARGET:
                    continue
                try:
                    hg, ag = int(record['ft_home']), int(record['ft_away'])
                    home, away = record['home'], record['away']
                except (ValueError, KeyError, TypeError):
                    continue
                history[(folder, norm(home))].append((match_date, hg, ag))
                history[(folder, norm(away))].append((match_date, ag, hg))
            for record in upcoming:
                if record.get('date') == TARGET and record.get('home') and record.get('away'):
                    fixtures.append({'competition': folder, 'date': TARGET,
                                     'time': record.get('time', ''),
                                     'home': record['home'], 'away': record['away']})
        except Exception as exc:
            errors.append({'competition': folder, 'error': str(exc)[:160]})
    raw_count = len(fixtures)
    unique = {}
    for fixture in fixtures:
        unique.setdefault(fixture_key(fixture), fixture)
    fixtures = list(unique.values())

    outcomes = []
    for fixture in fixtures:
        home = metrics(fixture['competition'], fixture['home'], history)
        away = metrics(fixture['competition'], fixture['away'], history)
        for outcome in ('H', 'D', 'A'):
            rapid = provisional_form_score(home, away, outcome) if home and away else None
            # Form component is provisional, NOT the QMS's verified opponent-adjusted F.
            components = {'F': None, 'M': None, 'S': None, 'C': None, 'V': None}
            missing = ('verified opponent-adjusted form; market evidence; strength model; '
                       'context/team news; source and kickoff verification; calibrated 1X2 '
                       'probabilities; actual odds and EV; independent QC assessment')
            outcomes.append({**fixture, 'outcome': outcome,
                'rapid_score': rapid, 'score_type': 'FORM_HEURISTIC_NOT_PROBABILITY',
                'F': '', 'M': '', 'S': '', 'C': '', 'V': '', 'cr_fos': '',
                'fos_complete': False,
                'home_form_dots': home['dots'] if home else '',
                'away_form_dots': away['dots'] if away else '',
                'home_form_record': home['record'] if home else '',
                'away_form_record': away['record'] if away else '',
                'home_matches_used': home['matches'] if home else 0,
                'away_matches_used': away['matches'] if away else 0,
                'home_form_score': home['form'] if home else '',
                'away_form_score': away['form'] if away else '',
                'status': 'PROVISIONAL_FORM_ONLY' if rapid is not None else 'INSUFFICIENT_LAST5',
                'qc_gate': 'AMBER_PENDING_INDEPENDENT_QC',
                'probability': '', 'odds': '', 'ev': '', 'qc_score': '',
                'risk_index': '', 'p_home': '', 'p_draw': '', 'p_away': '',
                'missing_evidence': missing,
                'moonshot_qualified': False,
                'kickoff_timezone_verified': False})
    selected = choose(outcomes)
    fields = ['pool', 'competition', 'date', 'time', 'home', 'away', 'outcome',
              'rapid_score', 'score_type', 'F', 'M', 'S', 'C', 'V', 'cr_fos', 'fos_complete',
              'home_form_dots', 'away_form_dots', 'home_form_record', 'away_form_record',
              'home_matches_used', 'away_matches_used', 'home_form_score', 'away_form_score',
              'status', 'qc_gate', 'probability', 'odds', 'ev', 'qc_score', 'risk_index',
              'p_home', 'p_draw', 'p_away', 'missing_evidence', 'moonshot_qualified',
              'kickoff_timezone_verified']
    write_csv('shortlist.csv', selected, fields)
    write_csv('all_outcomes.csv', outcomes, fields[1:])
    counts = {pool: sum(row['pool'] == pool for row in selected)
              for pool in ('Builder', 'Master', 'Moonshot research', 'Backup')}
    eligible = sum(isinstance(row['rapid_score'], (int, float)) for row in outcomes)
    fallback = sum(bool((h := metrics(f['competition'], f['home'], history)) and
                        (a := metrics(f['competition'], f['away'], history)) and
                        (h['matches'] == 5 or a['matches'] == 5)) for f in fixtures)
    summary = {
        'date': TARGET, 'version': MODEL, 'qms_reference': 'CT-QMS-001 v3.73',
        'run_id': RUN_ID, 'season': SEASON,
        'competitions_discovered': len(folders), 'competitions_failed': len(errors),
        'fixtures_loaded': len(fixtures), 'outcomes_generated': len(outcomes),
        'outcomes_with_adequate_form': eligible,
        'fixtures_using_five_match_fallback': fallback,
        'shortlist_count': len(selected), 'target_count': 47,
        'target_filled': len(selected) == 47, 'pool_counts': counts,
        'duplicate_fixtures_in_shortlist': len(selected) - len({fixture_key(r) for r in selected}),
        'unique_shortlist_fixtures': len({fixture_key(r) for r in selected}),
        'master_fixed_hda_quota': False,
        'green_gates': 0, 'cr_fos_complete_count': 0,
        'qc_watch_handover': 'ARTIFACT_CREATED_NOT_DELIVERED',
        'cross_source_dedup': 'NOT_TESTED', 'coverage_target': 500,
        'below_500_is_failure': False,
        'source_fixture_duplicates_removed': raw_count - len(fixtures),
        'unfilled_slots': {'Builder': max(0, 3 - counts['Builder']),
                           'Master': max(0, 12 - counts['Master']),
                           'Moonshot': max(0, 12 - counts['Moonshot research']),
                           'Backup': max(0, 20 - counts['Backup'])},
        'source_scope': 'Open Matchday only; worldwide multi-source intake NOT integrated',
        'note': ('Form5/7 score is an uncalibrated heuristic, NOT verified five-component CR-FOS, '
                 '1X2 probability or betting approval. Moonshot is research only. QC Watch must '
                 'retrieve and acknowledge this run artifact independently.'),
        'errors': errors}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))

    with (OUT / 'review.md').open('w', encoding='utf-8') as file:
        file.write(f'# Charlie & Taj provisional research — {TARGET}\n\n')
        file.write(f'{MODEL} | {len(fixtures)} source fixtures | {len(selected)}/47 unique candidates\n\n')
        file.write('Rapid scores are form heuristics, NOT probabilities or complete CR-FOS. No QC approvals.\n\n')
        file.write('| Pool | Match | Pick | Home form | Away form | Rapid score | CR-FOS | QC |\n')
        file.write('|---|---|---|---|---|---:|---|---|\n')
        for row in selected:
            file.write(f'| {row["pool"]} | {row["home"]} vs {row["away"]} | {row["outcome"]} | '
                       f'{row["home_form_dots"]} | {row["away_form_dots"]} | '
                       f'{row["rapid_score"]} | NOT VERIFIED | PENDING |\n')

    ids = {'Builder': 'B', 'Master': 'M', 'Moonshot research': 'U', 'Backup': 'BK'}
    numbered = Counter()
    with (OUT / 'handover.txt').open('w', encoding='utf-8') as file:
        file.write(f'HANDOVER START\nRUN_ID={RUN_ID}\nTARGET_DATE={TARGET}\nMODEL={MODEL}\n')
        file.write('STATUS=PROVISIONAL_RESEARCH_ONLY; QC_WATCH_ACCESS=NOT_VERIFIED\n')
        file.write('SOURCE_SCOPE=Open Matchday only; multi-source intake NOT integrated\n')
        file.write('QC_STATUS=NO_GREEN_APPROVALS; five-component CR-FOS/probability/odds/EV NOT VERIFIED\n')
        for pool, goal in [('Builder', 3), ('Master', 12), ('Moonshot research', 12), ('Backup', 20)]:
            pool_rows = [r for r in selected if r['pool'] == pool]
            file.write(f'POOL={pool}; ACTUAL={len(pool_rows)}; TARGET={goal}; VACANCIES={goal-len(pool_rows)}\n')
            for row in pool_rows:
                numbered[pool] += 1
                ref = f'{ids[pool]}{numbered[pool]:02d}'
                file.write(f'{ref} | {row["competition"]} | {row["date"]} {row["time"]} | '
                           f'{row["home"]} v {row["away"]} | {row["outcome"]} | '
                           f'form={row["home_form_record"]}/{row["away_form_record"]} | '
                           f'rapid_heuristic={row["rapid_score"]} | CR_FOS=NOT_VERIFIED | '
                           f'QC=PENDING | MISSING={row["missing_evidence"]}\n')
        file.write('HANDOVER END\n')
    contract = {'run_id': RUN_ID, 'model': MODEL, 'target_date': TARGET,
                'handover_created': True, 'qc_watch_received': False,
                'qc_watch_acknowledgement_required': True,
                'artifact_files': ['summary.json', 'shortlist.csv', 'all_outcomes.csv',
                                   'review.md', 'handover.txt', 'qc_watch_contract.json'],
                'three_pools_present': all(counts[k] > 0 for k in ('Builder', 'Master', 'Moonshot research')),
                'green_approved': 0, 'source_scope': 'Open Matchday',
                'cr_fos_verified': False,
                'next_action': 'QC Watch must retrieve artifact and record run_id receipt before independent QC.'}
    (OUT / 'qc_watch_contract.json').write_text(json.dumps(contract, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
