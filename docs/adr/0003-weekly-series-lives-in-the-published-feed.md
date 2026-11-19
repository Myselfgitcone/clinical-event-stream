# ADR 0003: the weekly series lives in the published feed, not in the runner

**Status:** accepted, 2026-11-18

## Context

The portfolio board wants a series over time. GitHub Actions runners are
stateless, Pages hosts static files, and committing parquet from a workflow
grows the repository every week. The full lakehouse history belongs in ADLS
Gen2 when the Azure target is on, but the page has to work without Azure.

## Decision

Each weekly run generates one fresh cohort seeded by the ISO week (so a re-run
in the same week is a no-op), runs the whole pipeline on it, fetches the
currently published `weekly.json`, upserts this week's point by `week_start`,
and publishes the merged list. `summary.json` describes the latest build;
`weekly.json` carries the history.

## Consequences

* The published series survives runner restarts and needs no repository
  commits. Its single point of failure is the Pages deployment itself; if a
  deploy is lost, the series loses that week, and the next run continues.
* The warehouse in CI holds the latest cohort only. With `CES_TARGET=azure`
  every cohort's bronze, silver and gold also land in ADLS, which is where the
  multi-cohort history and the SCD2 patient dimension become meaningful.
* `--no-extend` runs the pipeline without reading the published feed, which is
  what local runs and the CI gate use.
