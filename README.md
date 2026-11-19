# Charlie & Taj — Rapid Screen prototype

This is a runnable **research-only** GitHub Actions pipeline, not a deployed system. It reads the open-matchday public CSVs, finds fixtures on a selected date, calculates last-five W/D/L form and ranks three possible outcomes per fixture. It attempts to allocate Builder 3, Master 12 (6H/2D/4A), Moonshot research 12, and 20 backups, without repeating fixtures.

**Critical limitations:** only competitions in open-matchday are covered (not the FootyCheck 368/370 worldwide list); team history is restricted to the same competition and season; Rapid Score is an uncalibrated heuristic, not the approved full TSI, 1X2 probabilities, EV or GREEN QC. Moonshot research picks are deliberately exploratory and **not** proven high-odds bets. Missing history is not imputed. Do not place bets based on these outputs. Data source: https://github.com/oladeeayo/open-matchday — personal, informational, non-commercial terms; check upstream rights.

## Run on GitHub
1. Create a **private** GitHub repository, and upload the contents of this folder, including `.github/workflows/rapid-screen.yml`.
2. Open **Actions → Charlie Taj Rapid Screen → Run workflow**. Enter `2026-11-20` to test the requested date, or leave blank for today's UTC date.
3. Open the completed run and download `rapid-screen-output` from **Artifacts**. Read `summary.json` first; `shortlist.csv` and `all_outcomes.csv` are included.
4. The workflow also schedules a daily 07:15 UTC run. Scheduled runs can be delayed or disabled by GitHub; this does not automatically deliver data to ChatGPT QC Watch.

The first run should be treated as a connectivity/schema test. Review any competition errors in summary.json before trusting the fixture count. If fewer than 47 distinct eligible fixtures exist, the shortlist will be shorter rather than fabricated.
