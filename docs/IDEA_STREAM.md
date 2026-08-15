# The Idea Stream — what it is, and what a real one would take

## What ships today

A ranked board of 16 flavour and format concepts, each scored 0–100 and
droppable into the workspace as a formulation brief.

The **ranking** is production-grade. Scores come from versioned weights in the
corpus, computed deterministically, with no LLM involvement — the same doctrine
as the formulation gate. Change the weights and you change the ranking; change
the code and you change nothing about the numbers.

The **corpus** is a hand-curated snapshot. Its `social`, `momentum` and
`feasibility` values are analyst judgement on a 0–100 scale, informed by the
references listed against each idea rather than computed from them. There is no
collection pipeline. The references carry a name and a note but no URL and no
capture date.

Both facts are stated in the UI, in `ideas.py`, and in the corpus's own
`methodology` field. A staleness chip shows how old the snapshot is —
`current` under 30 days, `aging` to 90, `stale` beyond — because consumer
flavour trends turn over in weeks and a three-month-old ranking is a historical
document.

**Why it is built this way.** The expensive part of a trend system is not the
ingestion, it is deciding what a signal means and how signals combine. Building
the ranking first, against asserted values, means the scoring model can be
argued about and tuned before anyone pays for data. Swapping asserted signals
for measured ones requires no change to `ideas.py`.

## What it is not

- Not a stream. Nothing flows; the JSON changes when a human edits it.
- Not measured. "+450% YoY" on a source note is an assertion, not a query result.
- Not falsifiable as published. Without URLs or capture dates, a reader cannot
  check any individual claim.
- `breadth` counts corroborating references, and those references are
  themselves unverified — so a well-referenced idea outranks a sparsely
  referenced one on assertion volume, not evidence quality.

## Building the real one

### Layer 1 — ingestion

The goal is a signal that someone else could reproduce from the same query on
the same day.

| Source | Access | What it yields | Cost |
|---|---|---|---|
| **Google Trends** (`pytrends`) | Free, unofficial | Relative interest 0–100 over time, by region. Already normalised — the closest free analogue to the current `social` field | £0 |
| **Reddit** (PRAW) | Free, official API | Post and comment volume per term, per subreddit; velocity week over week | £0 |
| **YouTube Data API** | Free tier, 10k units/day | Video counts and view velocity for a search term | £0 |
| **TikTok** | No usable public API | Creator Marketplace or a vendor. This is the gap — the platform that matters most is the hardest to instrument legally | vendor pricing |
| **Retail listings** | Scrape or vendor | New SKU launches by category; the strongest lagging confirmation | varies |
| **Trade press** (Food Dive, IFT, Mintel) | RSS free, Mintel paid | Analyst framing; useful for `lifecycle`, weak for volume | £0–substantial |

Start with Google Trends plus Reddit. Two instrumented signals beat sixteen
asserted ones, and both are free.

### Layer 2 — normalisation

The hard part, and where a naive build goes wrong.

- **Per-source normalisation.** Reddit post counts and Trends indices are not
  the same unit. Normalise each source to 0–100 within its own distribution
  across the tracked term set, then combine — never average raw counts.
- **Seasonality.** Ice cream terms spike every summer. A year-over-year
  comparison or an STL decomposition separates "trending" from "it is July".
  Without this the whole board reranks every spring and means nothing.
- **Term ambiguity.** "Dubai chocolate" is clean. "Matcha" collides with
  drinks, skincare and cosmetics. Each concept needs a query definition —
  include and exclude terms — versioned alongside the corpus.
- **Momentum ≠ level.** Keep them separate, as the current schema already does.
  Something can be huge and declining.

### Layer 3 — storage and refresh

- Append-only time series per `(concept_id, source, date)`. Never overwrite: the
  history is what makes momentum computable and lets you show a sparkline.
- Weekly refresh is enough for flavour trends. Daily is noise.
- The corpus becomes a materialised view over that series, regenerated on a
  schedule, so `updated` moves on its own and the staleness chip goes green
  without anyone touching a file.

### Layer 4 — provenance

Every signal value carries the query that produced it, the source, the capture
timestamp, and the raw value before normalisation. That is the difference
between "social: 96" and a number a reader can audit — and it is the same
standard the ingredient library already meets, where every nutrient traces to
a USDA FDC record.

### What stays unchanged

`ideas.py`, the weights, the scoring model, the API shape, the UI. The
ingestion layer writes into the same schema. That is the point of having built
the ranking first.

## Honest effort estimate

| Phase | Scope | Effort |
|---|---|---|
| 1 | Trends + Reddit collectors, per-source normalisation, 16 existing concepts | 2–3 days |
| 2 | Time-series storage, weekly scheduled refresh, momentum from real history | 2 days |
| 3 | Provenance fields, sparklines, query definitions per concept | 2 days |
| 4 | Seasonality adjustment | 1–2 days |
| 5 | TikTok via vendor, if it justifies the cost | procurement-bound |

Roughly a week for phases 1–3, which is the point at which "social: 96" becomes
a number someone else can reproduce.

## The judgement call

The version that ships is honest about being a curated snapshot, and the
scoring engine underneath it is real and would not change. Shipping the
ingestion first would have meant tuning a scoring model against live data with
no stable baseline to compare against — harder to reason about, and the
expensive part would have been built before anyone agreed what a signal means.

The failure mode to avoid was never "the data is hand-curated". It was
describing hand-curated data as social listening. That wording is fixed; the
architecture was always ready for the real thing.
