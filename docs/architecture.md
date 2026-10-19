# Architecture

Status: v0 build, written 2026-10-18. Election day is Tuesday, November 3, 2026.

## Goals and constraints

A public, neutral, static site covering the 2026 U.S. House, U.S. Senate, and
governor elections, with a citation on every figure. $0 budget, no server,
hands-off operation, survives election night traffic. See the README for the
user-facing summary and `methodology.md` (site page) for data rules.

## System overview

```
 sources (FEC bulk, congress-legislators, Census TIGER/ACS, Dataverse, curated seeds)
        |
        v
 ingest/ (Python 3.12, uv)          one adapter per source: fetch -> validate -> normalize -> emit
        |                           failures keep the adapter's last good output
        v
 `data` branch (orphan)             raw adapter outputs + status.json, committed by Actions
        |
        v
 ingest compose                     joins adapters into the site bundle (races, states,
        |                           sources, downloads, boundaries, status)
        v
 site/ (Astro 7, static)            pages rendered at build time; downloads and boundary
        |                           files copied to /data/
        v
 GitHub Pages (Fastly CDN)
```

### Ingestion

- `ingest/src/ingest/core/adapter.py` defines the interface. The runner wraps
  each adapter in an isolation boundary: an exception at any step leaves the
  adapter's previous output directory untouched and records the error in
  `status.json` (`ok`, `last_success_at`, `retrieved_at`, `has_data`).
- Schemas are Pydantic models in `core/models.py`. Every emitted row must carry
  `source_ids` that resolve to a source record emitted by the same adapter, or
  the adapter fails validation.
- HTTP uses retries with jittered exponential backoff on 408/425/429/5xx and
  honors `Retry-After`. API keys are passed as parameters and redacted in logs.
- Plausibility floors (minimum row counts, expected district counts per state,
  100 senators, FEC header columns) catch silently truncated or reshaped data.

Adapters in v0:

| id | Source | Cadence | Notes |
|---|---|---|---|
| `state_offices` | `data/seeds/state-election-offices.yaml` | daily | Curated official URLs |
| `candidates_official` | `data/seeds/governors-2026.csv`, `data/seeds/federal-candidates-2026/*.csv` | daily | Curated from official state lists |
| `legislators` | unitedstates/congress-legislators (CC0) | daily | Incumbents, FEC ids, Senate class |
| `fec` | FEC bulk `cn26.zip`, `weball26.zip` | daily | No key, no rate limit |
| `history` | MEDSL Senate (CC0), Cha-Kuriwaki-Snyder candidates (CC0) | daily, 30 day stale threshold | |
| `boundaries` | Census TIGER/Line `cd120` (2026) per state | daily, 8 day stale threshold | Missouri override, see below |
| `acs` | Census ACS 5-year 2020-2024 API | daily | Needs `CENSUS_API_KEY` |
| `live_clarity` | Clarity ENR (experimental) | election night | Behind `LIVE_RESULTS_ENABLED` |

### Compose

`ingest compose` builds the site bundle from whatever adapter outputs exist.
It never fetches. It derives the race list (435 House seats plus the DC
delegate from the 2020 apportionment; Senate class 2 seats plus specials
detected from senators whose term ends on election day; governor states from
the seed), picks the candidate list per race (official seed, else FEC
registrant fallback for federal races, else "unavailable"), orders candidates
(ballot order when complete in the source, else last name), matches FEC
finance strictly, and writes per-race JSON plus downloads. It fails if any
referenced source id is undefined.

### Site

- Astro 7, static output, base path `/USA-Election-Tracker/`.
- Race and state pages ship zero JavaScript. District maps are inline SVG
  rendered at build time. The national map on the home page (Albers equal-area
  composite, every state an SVG link) and each state's district map (every
  district an SVG link) are also build-time SVG. Only the ballot lookup page
  (about 4 KB) and the search page (Pagefind UI, loaded from the site itself)
  run scripts.
- Typeface: Public Sans (SIL OFL, the U.S. Web Design System face), self-hosted
  from the `@fontsource-variable/public-sans` package. One variable woff2 of
  about 50 KB is preloaded; no third-party font service. One accent color
  (dark ochre), no party colors, one map fill; dark mode mirrors every token.
- Every figure is wrapped in an element marked `data-figure` containing a
  citation link (`data-cite`) to the Sources page. `scripts/check-site.mjs`
  fails the build if any figure lacks a citation, any citation points to a
  missing source, banned framing words appear, an em dash or emoji appears, or
  race/state pages exceed 100 KB of JS.
- i18n: Astro i18n routing with `en` only; all UI strings in
  `src/i18n/en.json`, long-form pages in `src/content/en/*.md`. Spanish is added
  by a locale file and content folder.

### Storage

Generated data lives on the orphan `data` branch, not `main`. The branch holds
raw adapter outputs; the deploy workflow composes and builds from it. Size
today is about 15 MB, dominated by boundary files that change rarely.

### Workflows

| Workflow | Trigger | Does |
|---|---|---|
| `ci.yml` | PR, push to main | copy style check; ruff; pytest (fixtures only); seed validation; smoke test that runs every adapter offline (all fail), composes from last good data, builds, typechecks, runs site checks, Lighthouse CI |
| `ingest-daily.yml` | 10:17 UTC daily, manual | runs adapters, commits to `data`, opens or updates an `ingest-failure` issue, dispatches deploy |
| `deploy.yml` | push to main, dispatch | compose + build + `actions/deploy-pages` |
| `link-check-weekly.yml` | Mondays | checks every official URL; opens or updates a `link-check` issue |
| `live-results.yml` | election night only, gated | see runbook |

## Verified platform facts (2026-10-18)

GitHub Pages (docs.github.com, "GitHub Pages limits"):

- Published site max 1 GB; soft bandwidth limit 100 GB/month; deployments time
  out after 10 minutes. The 10 builds/hour soft limit does not apply to custom
  Actions workflows, but "rate limits may apply".
- Responses carry `Cache-Control: max-age=600` through Fastly. A query string
  does not create a new cache key in testing, so cache-busting query strings do
  not work. Whether a deploy purges the CDN is not documented.
- Range requests return 206 (PMTiles would work), but with `Accept-Encoding:
  gzip` the range applies to the gzipped body.

GitHub Actions:

- Shortest schedule is every 5 minutes; schedules "can be delayed during
  periods of high loads" and "some queued jobs may be dropped", especially at
  the top of the hour. Scheduled workflows in public repos are disabled after
  60 days without repository activity.
- Standard runners are free for public repositories.

## Conflicts with the original brief, and what we did

1. **FEC lists are not ballots.** The FEC has no field for ballot
   qualification or primary results, and lists thousands of registrants. With
   maintainer approval, House and Senate candidates come from official state
   lists (curated seed, same model as governors), FEC is used for finance and
   as a clearly labeled fallback. Ohio House is on the fallback because Ohio
   publishes no statewide certified House list.
2. **Census Geocoder has no CORS.** Confirmed by header tests and the Census
   documentation. JSONP works but would run a third-party script per visitor.
   Per the brief, the lookup uses device geolocation plus selecting a district
   on a state map. No addresses are collected at all.
3. **MapLibre and PMTiles are not used in v0.** MapLibre 6 is about 430 KB
   gzipped (library plus worker), which breaks the 100 KB JS budget and adds
   work for the keyboard and table alternatives. Static SVG maps meet the v0
   need (geography only, no basemap) with zero JS, and the lookup draws its
   own SVG. PMTiles on Pages was verified to work if a basemap is wanted in v1.
   This is a deviation from the stated stack; flagged for maintainer review.
4. **The MEDSL House dataset needs a Dataverse guestbook response**, so it
   cannot be fetched unattended. House and governor history comes from the
   CC0 "Candidates in American General Elections" dataset (2006 to 2024);
   Senate history from MEDSL. MEDSL publishes no governor time series.
5. **ACS needs an API key now** (keyless requests are redirected). A free key
   must be stored as the `CENSUS_API_KEY` secret. ACS 2020-2024 is tabulated
   for 119th Congress lines, so demographics are shown only for the 41 states
   whose lines did not change (plus Missouri, which kept its 2024 lines).
6. **Missouri's Census 2026 boundary file is wrong for 2026.** It still holds
   the 2025 plan, which the Supreme Court did not allow for 2026 (application
   26A388, Sept 25, 2026). We use TIGER2025 `cd119` for Missouri, recorded in
   `data/seeds/boundary-sets-2026.yaml`.
7. **Clarity ENR covers only West Virginia and Colorado statewide** among the
   states checked. Georgia moved to Enhanced Voting, Arkansas to Tally,
   Kentucky runs its own system. Clarity's WAF blocks default user agents and
   its vendor terms need human review. The live tier is therefore small and
   experimental by design.
8. **Live updates cannot be faster than about 10 to 20 minutes end to end**:
   5 minute cron (best effort under load) plus build and deploy (about 2 to 4
   minutes) plus up to 10 minutes of CDN caching. The election night page
   states this. The runbook covers manual dispatch if cron is delayed.
9. **GoatCounter's free tier is for "reasonable public usage"** and says
   millions of pageviews per day is not. If election night traffic is very
   high, we may need to turn analytics off for the night (one repository
   variable) rather than risk abuse of a donated service.

## Redistricting for 2026

Nine states have new maps for 2026 (Census 120th Congress notice): AL, CA,
FL, LA, NC, OH, TN, TX, UT. Each boundary set names its enacting law, ballot
measure, or court order. Missouri's attempted 2025 map is not in effect.
Failed or blocked attempts in VA, IN, NY, and MD did not change 2026 maps.
Several cases remain pending (TX, CA, FL, TN, LA, AL, UT); the weekly review
should recheck them, and any change is committed to the boundary plan on `main`.

## Neutrality controls in code

- Candidate order: ballot order only when every candidate in the race has one
  from the source; otherwise last name. Never by money, party, or incumbency.
- Party labels are rendered verbatim; FEC fallback party codes are labeled as
  FEC codes.
- No party colors exist in the stylesheet. Maps encode geography only.
- `check-site.mjs` blocks framing words (battleground, toss-up, key race,
  surge, winner, and others) in rendered pages.
- Incumbents and challengers share one table layout; incumbency is a Yes/No
  column.

## v1 design hooks

- `Office` already reserves `state_upper`, `state_lower`, `ballot_measure`.
  Race ids are `<year>-<office>-<state>[-<district>][-special]`, stable as
  offices are added.
- Results are a separate table keyed by `race_id` (`LiveResultRow` today); a
  certified results adapter adds rows with a different `source_ids` and a
  certification flag rather than changing race files.
- OpenStates (public domain bulk data, key required for the API) is
  registered as `not_used` and is the planned source for state legislative
  races.
- Turnout analysis can join certified results with the ACS table on
  `(state_po, district, boundary_vintage)`.
