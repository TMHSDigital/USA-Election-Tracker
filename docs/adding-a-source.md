# Adding a source

New external sources need maintainer approval before any code is written.
Open a "Source request" issue first.

## 1. Verify

Before writing an adapter:

1. Confirm the source is live: fetch the exact URL you will use and record the
   HTTP status. Several well-known sources shut down in 2025.
2. Read its license and terms of service. If the terms forbid redistribution,
   scraping, or automated access, do not use it. Quote the relevant sentence
   in the registry notes.
3. Note rate limits, authentication, and anything unusual (bot protection,
   guestbooks, encodings).

## 2. Register

Add an entry to `sources/registry.yaml`:

```yaml
- source_id: example_source        # lowercase, stable forever
  name: Human readable name
  publisher: Who publishes it
  url: https://...
  license: License name
  license_url: https://...
  terms_url: https://...
  status: live                     # live | partial | dead | rejected | not_used
  verified_at: 2026-10-18
  redistribution: allowed          # allowed | restricted | unknown
  rate_limits: ...
  notes: ...
```

The ingest code refuses to cite a source whose status is not `live` or
`partial`, or whose redistribution is `restricted`.

## 3. Write the adapter

Create `ingest/src/ingest/adapters/<name>.py` with a class that subclasses
`Adapter` and implements:

- `fetch()`: get raw data through `self.ctx.http` (never `httpx` directly, so
  tests can substitute fixtures).
- `validate(raw)`: raise `ValidationFailed` if the data does not look right:
  missing columns, implausible row counts, changed headers.
- `normalize(raw)`: return a `Dataset` of Pydantic rows. Every row needs
  `source_ids`, and every id must be in `Dataset.sources`.
- `emit` is inherited.

Register it in `ingest/src/ingest/adapters/__init__.py`. Set `max_age` to how
long data may go without a successful update before the site marks it out of
date. Set `experimental = True` if it should only run when named explicitly.

## 4. Test

- Save a small, trimmed fixture in `ingest/tests/fixtures/` (see
  `tests/make_fixtures.py`), route its URL in `tests/conftest.py`, and add
  tests for the happy path, a format change, and the failure path (last good
  data kept).
- Run `uv run pytest -q`.

## 5. Use it on the site

Join it in `ingest/src/ingest/compose.py`, render it in an Astro page, and
wrap every figure in an element with `data-figure` containing
`<Cite ids={...} />`. `npm run build` fails if a figure has no citation.

## Curated seeds

For data with no API (official candidate lists, election office URLs), edit
the seed files in `data/seeds/`. Every row needs the official `source_url` and
`retrieved_at`. Use only official government sources. Changes go through pull
requests and must pass `uv run ingest check-seeds`.
