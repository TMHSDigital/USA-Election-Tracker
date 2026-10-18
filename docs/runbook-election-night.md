# Election night runbook (November 3, 2026)

The site is complete without live results. Its job on election night is to
stay up and send people to official results. The experimental live tier is
optional and can be turned off with one change.

Commands are PowerShell on Windows and work the same in any shell with `gh`.

## Before November 1 (go/no-go)

1. CI is green on `main`, including `tests/test_clarity.py` against the
   archived West Virginia 2024 results.
2. For each state in `data/seeds/live-sources-2026.yaml`:
   - Find the 2026 general election results address on the state's official
     site (not a search engine). Set `election_id`.
   - Open `https://results.enr.clarityelections.com/<ST>/<id>/current_ver.txt`
     and `.../<version>/json/en/summary.json` in a browser; copy each contest
     name we will show exactly into `contests`, mapped to our `race_id`.
   - Read the vendor terms linked in `sources/registry.yaml` (`clarity_enr`)
     and record the decision in the PR.
3. Dry run: `gh workflow run live-results.yml -f ignore_window=true` with
   `LIVE_RESULTS_ENABLED` set to `true`, confirm the election night page shows
   the contests with "Unofficial", the reporting text, source link, and fetch
   time, then set the variable back to `false`.
4. Decision: if any step above is not done by November 1, leave
   `LIVE_RESULTS_ENABLED` at `false`. Record the decision here.

Decision log:

- 2026-10-18: adapter and tests pass against archived data. No 2026 election
  ids published yet. Status: off.

## What runs on election night

| Workflow | When | Effect |
|---|---|---|
| `live-results.yml` | every 5 minutes, Nov 3 23:00 UTC to Nov 5 12:00 UTC, only if `LIVE_RESULTS_ENABLED` is `true` | fetches mapped contests, commits to `data`, redeploys |
| `deploy.yml` | after each live update | composes, builds, deploys to Pages |
| `ingest-daily.yml` | 10:17 UTC | normal daily refresh |

Expected lag behind the official source: 5 minute schedule (may be delayed or
skipped by GitHub under load), 2 to 4 minutes to build and deploy, and up to
10 minutes of CDN caching. The page says updates lag by several minutes or
more.

## Turn the live tier on or off

```powershell
gh variable set LIVE_RESULTS_ENABLED --body true    # on
gh variable set LIVE_RESULTS_ENABLED --body false   # off (kill switch)
gh workflow run deploy.yml                          # redeploy so the page reflects it
```

With the variable `false`, the live workflow does nothing and the next deploy
removes the live section; the official results links remain.

## If cron is delayed

Run it by hand: `gh workflow run live-results.yml`. Check progress with
`gh run list --workflow live-results.yml --limit 5`.

## If a source breaks

The adapter fails validation (for example, a renamed contest), keeps the last
good live data, and the page shows the out of date notice with the last fetch
time. Fix the contest mapping in `data/seeds/live-sources-2026.yaml` by PR, or
turn the tier off. Never hand-edit vote numbers.

## Roll back a bad deploy

- Bad code on `main`: `git revert <sha>` and push; `deploy.yml` runs on push.
- Bad data on `data`: find the last good commit with
  `git log origin/data --oneline -10`, then
  `git push origin <good-sha>:data --force-with-lease` and
  `gh workflow run deploy.yml`.
- Pages itself: re-run a previous successful `deploy` run from the Actions tab
  ("Re-run all jobs").

## Traffic

The site is static and served by GitHub's CDN. Nothing calls a third-party
API per visitor except GoatCounter analytics. If traffic is extreme, turn
analytics off for the night to respect GoatCounter's free-tier terms:
`gh variable delete GOATCOUNTER_CODE` then `gh workflow run deploy.yml`.

## Never

- Never show a winner, checkmark, or projection, or summarize who is ahead.
- Never copy numbers from anywhere other than the official source.
- Never edit live numbers by hand.
