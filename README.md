# USA Election Tracker

A free, neutral, static website with data on the November 3, 2026 elections for
U.S. House, U.S. Senate, and governor. Every figure links to its source.

---

Site: https://tmhsdigital.github.io/USA-Election-Tracker/

A TM Hospitality Strategies project.

## What it includes

- A page for every race that opens with its map beside the title: the 2026
  district map for House races (neighboring districts on it link to their
  own races) or a national locator for Senate and governor races. Then
  candidates as listed by state election officials, FEC fundraising totals
  for federal candidates (as a table and as bars in ballot order, every bar
  the same fill), past results for the seat with total votes cast by
  election, and citations.
- A page for every state that opens with the map of its congressional
  districts beside the title (each district a link to its race, with the
  candidate count shown on hover or focus), then its races as a grid of
  numbered tiles and official election office links.
- A home page that opens with the national map, where every state is a link
  and shows the offices on its ballot when hovered or focused, followed by a
  plate for each office with its seat count and a plate for every state with
  its race count. Each office (U.S. House, U.S. Senate, governor) has an index
  page; the Senate and governor indexes open with the same map showing only
  the states that vote for that office in 2026.
- A ballot lookup that finds your congressional district in your browser,
  with the national map as a state picker.
- Site search that runs in the browser (Pagefind), with no query sent anywhere,
  with filters by office, state and page type and one result per page. The search box in the header
  opens the search page with your query, and the slash key focuses it.
- A light or dark theme control in the header. The choice is stored only in
  your browser.
- Links to official voting information and official results for every state.
- Every dataset, downloadable as CSV and JSON.

It does not include forecasts, polling averages, race ratings, commentary, or
race calls.

## Data sources

| Data | Source | License |
|---|---|---|
| Candidates (all offices) | Official state certified candidate lists, curated in `data/seeds/` | Government publications, cited per row |
| Federal campaign finance | FEC bulk files `cn26`, `weball26` | Public domain |
| Incumbents | unitedstates/congress-legislators | CC0 1.0 |
| District boundaries | Census TIGER/Line 2026 (`cd120`), Missouri `cd119` | Not copyrighted; Census acknowledgement |
| Past Senate results | MIT Election Data and Science Lab | CC0 1.0 |
| Past House and governor results | Cha, Kuriwaki, Snyder, "Candidates in American General Elections" | CC0 1.0 |
| Demographics | Census ACS 5-year 2020-2024 API | Public; Census API notice required |
| State election office links | Curated in `data/seeds/state-election-offices.yaml` | Links only |

The full list, including sources we checked and rejected, is in
[`sources/registry.yaml`](sources/registry.yaml).

## Licenses

- Code: MIT ([LICENSE](LICENSE)).
- Our compiled data: CC BY 4.0 ([LICENSE-DATA.md](LICENSE-DATA.md)).
  Underlying sources keep their own licenses.

## Run locally (Windows PowerShell)

Requirements: Node.js 22.22 or newer, and [uv](https://docs.astral.sh/uv/).

```powershell
# 1. Python ingestion
cd ingest
uv sync
uv run pytest -q                      # tests use saved fixtures, no network

# Fetch real data into ..\.data\raw (ACS needs a free Census key)
$env:CENSUS_API_KEY = "your-key"      # optional
uv run ingest run

# Or start from the published last good data instead of fetching:
#   cd ..; git fetch origin data; git worktree add .data/raw FETCH_HEAD; cd ingest

uv run ingest compose                 # writes ..\.data\site

# 2. Site
cd ..\site
npm ci
npm run dev                           # http://localhost:4321/USA-Election-Tracker/
npm run build                         # full build plus citation and neutrality checks
```

Other commands:

```powershell
cd ingest
uv run ingest check-seeds             # validate curated seed files
uv run ingest run fec legislators     # run selected adapters
uv run ingest run --offline           # simulate every source failing
uv run ingest link-check              # check official URLs
cd ..
node scripts/check-copy.mjs           # no em dashes or emoji anywhere
```

## Adding or correcting data

- Candidate or office corrections: edit the seed file in `data/seeds/` with
  the official `source_url` and `retrieved_at`, and commit it to `main`.
- Log every published correction in `data/corrections.yaml`.
- New sources: see [docs/adding-a-source.md](docs/adding-a-source.md). New
  external sources need maintainer approval before any code is written.

## Documentation

- [docs/architecture.md](docs/architecture.md): design, verified platform
  limits, and deviations from the original brief.
- [docs/adding-a-source.md](docs/adding-a-source.md)
- [docs/runbook-election-night.md](docs/runbook-election-night.md)
- Methodology is published on the site at `/methodology/`.

## Report an error

Open an issue with the "Data error" template.
