# FormulaForge — Repo Readiness Review

Reviewed at `dc91a92` (tip of `main`) on branch `readiness-review`, 2026-09-30.
Phases 1–4 were read-and-run only; nothing outside this file has been changed.

## 1. Verdict

Not ready to show yet: the engineering is unusually careful, but two of the README's
headline claims do not hold — a gap in the governed data lets a diabetic formula pass
that should fail, and the Q&A path streams model-invented nutrient values, with fabricated
USDA citations, as unlabelled text. The single biggest risk if shown today is a reviewer
asking the demo a nutrient question the library cannot answer and getting a confident,
wrongly-sourced number from a product whose thesis is "no model-produced number reaches
a user."

## 2. Findings

Severity follows the brief: **Blocker** (wrong or unreproducible claims, verdict-changing
data defects, demo ≠ repo), **High** (a reviewer hits it in 10 minutes; misleading docs;
unguarded external calls), **Medium** (senior-review comments), **Low** (cosmetic).
Effort: XS < 30 min, S < 2 h, M < 1 day.

| ID | Sev | Category | Evidence | What is wrong | Proposed fix | Effort |
|---|---|---|---|---|---|---|
| B1 | Blocker | Data integrity | `backend/etl/nutrient_map.py:34-36`; `backend/domain/data/ingredients.json` rows `cream_heavy`, skim, 2 %, buttermilk, cream cheese | `sugars_g` is in `DEFAULT_ZERO_FIELDS`, so the five FDC dairy rows whose source records omit nutrient 2000 ship with **0.0 g sugars** — while the same rows' `functional.lactose_g` records 2.8–5.0 g. This is the "absent ≠ zero" defect already fixed for minerals, on the field the diabetic ruleset gates. Reproduced: skim 72 / cream 14 / sucrose 6 / polydextrose 6 / WPI 1.5 / gums 0.5 validates as **passed**, 5.23 g sugars/serving; adding the missing lactose gives ≈ 8.70 g against the 8.0 g limit. The per-serving sugars shown for a skim-based formula can be understated ~20×. | Stop zero-defaulting `sugars_g` for FDC-sourced rows (same rule as `CLINICAL_MINERAL_FIELDS`); supply the value from a curated, provenance-labelled override (lactose) or fail the build; add a dataset test asserting FDC dairy rows have `sugars_g ≥ lactose_g`; rebuild as `2026.09.1`. **Changes the dataset — needs your approval (Q2).** | M |
| B2 | Blocker | LLM / claims | `backend/graph.py:218-241`; `frontend/src/App.tsx:453-468`; `README.md:39-41, 468`; `frontend/index.html:9` | The headline "no nutritional… number is model-produced" and "Model-authored numbers reaching a user: 0" are true only of the formula path. The RAG agent streams free text; its prompt never restricts it to the retrieved rows, and the UI renders it as ordinary assistant text with no provenance label or numeric-claim flag. Live test (local API, `openai/gpt-oss-120b`): **2 of 3** nutrient questions answered with invented values attributed to USDA FDC — vitamin D / magnesium in milk (not in the library), phosphorus in oat milk (not in the library; also "30 mg = ½ % DV", actually 4.3 %). The third (potassium, heavy cream vs skim) was correctly grounded. The context label "Relevant USDA foods" (`graph.py:229, 238`) invites the false attribution — the library includes curated, non-USDA rows. | (a) Scope the README and meta-description claim to what is enforced; (b) instruct the RAG prompt to answer numbers only from the provided rows and say "not in the governed library" otherwise; (c) run `_has_numeric_claim` on RAG output and render Q&A answers as model-authored in the UI, as formula prose already is; (d) relabel the context "governed ingredient library". | M |
| B3 | Blocker | Deploy ≠ repo | `curl https://formula-forge-qye9.onrender.com/health` → `"dataset 2026.07.0, 34 ingredients"`, `"version":"1.0.0"`; repo `ingredients.json:2` = `2026.09.0` | The live demo serves an older governed library than `main`, so fixes such as `aef91ea` ("fix the egg yolk it invented" — phosphorus 0.0 on a renal-gated field) are likely not live. `APP_VERSION` is unstamped, so the deployed build cannot be matched to a commit. | Redeploy the Render service from `main`; set `APP_VERSION` to the git SHA in the Render build. (Requires your Render access — Q6.) | XS |
| H1 | High | Presentation | `README.md:14` → `docs/workspace.png`; `git log --all -- docs/workspace.png` is empty; raw GitHub URL returns 404 | The README's hero screenshot has never been committed; the first image a visitor sees is broken. | Capture the workspace and commit it at that path. | XS |
| H2 | High | Correctness (async) | `backend/main.py:419-420` and `:110-115` (reached from `:421`, `:461`) | `_stream_agent` is `async` but calls the synchronous `formula_llm.invoke` directly for iteration and for every repair re-prompt, blocking the event loop for the whole Groq round trip. Measured: `/health` 8 ms idle → **1.59 s** while one iteration request was in flight. Every concurrent request stalls, including readiness probes. | Wrap the sync calls in `await asyncio.to_thread(...)` (or use `ainvoke`); add a test that `/health` stays responsive during a slow mocked LLM call. | S |
| H3 | High | Error handling | `backend/llm.py:26-28`; `ChatGroq.model_fields` → `request_timeout=None, max_retries=2` | No timeout on the provider call. A hung Groq request holds the SSE stream open indefinitely and — combined with H2 — blocks the server. | Pass `timeout` / `max_retries` from settings (e.g. 30 s, 1 retry); surface timeout as the existing SSE `error` event; test with a mocked stall. | S |
| H4 | High | Correctness (routing) | `backend/graph.py:153-164` | `detect_iteration` matches words like "more", "add", "keep", "version" without checking whether the message is a question. Reproduced: after a renal formula, "Why does this formula use **more** cream than a standard recipe?" returned the same formula again instead of an answer. | Skip iteration when `_QUESTION_RE` matches (unless an explicit imperative such as "make it…" is present); add question-shaped follow-ups to `eval/briefs.json`. | S |
| H5 | High | Security / docs | `backend/main.py:482, 487`; `backend/budget.py:197-222`; `README.md:213` | The per-session token cap is keyed on a client-supplied `session_id`, so omitting or rotating it bypasses the cap entirely; only the global cap binds. The README says "the session cap stops one client consuming it alone," which is not true. `_session_used` also gains one entry per minted id until UTC rollover. | Key the per-client cap on the client address (as the rate limit is) or on a server-minted id; correct the README sentence. | S |
| H6 | High | Claims | `README.md:469` vs `pytest tests/` → **362 passed** | README says 231 tests. The claim is wrong (understated — but "wrong" is what a reviewer will notice). | Update the figure, or drop the count and link the CI badge. | XS |
| H7 | High | Claims / honest results | `README.md:539-545` vs `backend/eval/baseline.json` (`"mode": "live"`, 2026-09-04, 46 cases) | README says the baseline holds only an offline run and the live gate has nothing to compare against. A full live baseline exists, and "What it comes to" omits its results: first-pass gate 29/38 (76 %), repair recovery 6/7, constraint targeting 24/33 (73 %), schema-valid 37/39, **prose free of numeric claims 0/37**. | Replace the stale paragraph; add the live rates, with their Wilson intervals, to "What it comes to." Honest mid-range numbers read as more credible than a column of 100 %. | S |
| H8 | High | Retrieval quality | `backend/graph.py:191-202`; queries below (§3.2) | Keyword scoring has no stopword or role awareness: "ice cream" matches every cream row and "low" matches "low fat". "Which sweetener is best for a diabetic ice cream?" returns coconut cream, cream cheese, heavy cream and dextrose — no erythritol, allulose or sucralose. "Low-phosphorus protein source" ranks low-fat buttermilk first. | Drop stopwords and product nouns from the query, score `role` matches (e.g. "sweetener" → role `sweetener`) above name tokens, add a small synonym map; pin the five queries in a test. | S |
| H9 | High | Dependencies | `npm audit` → 15 vulns (9 high); `frontend/package.json:21` | Direct: `vite` 8.0.x (GHSA-fx2h-pf6j-xcff, GHSA-v6wh-96g9-6wx3) and `postcss`. The rest (express, hono, qs, …) arrive via the `shadcn` **CLI** listed as a runtime dependency, used only for `@import "shadcn/tailwind.css"` (`src/index.css:3`). None reach the browser bundle, but the audit output is what a reviewer sees. | `npm audit fix` for vite/postcss; move `shadcn` to `devDependencies`; re-run lint + build. | S |
| H10 | High | Error handling | `backend/graph.py` `_invoke_formula`; server log `groq.BadRequestError: 400 json_validate_failed` | *Found during Phase 5 verification.* When Groq rejects JSON-mode output server-side (400 `json_validate_failed`), the exception escaped the formula node: the user saw "encountered an error (BadRequestError)" and the one repair the design promises for a malformed proposal never ran. Plausibly the live baseline's 2/39 unparsed outputs. | Treat that specific refusal as an unparseable attempt so it takes the repair; let every other provider error raise. | S |
| M1 | Medium | Dependencies | `pip-audit -r requirements-dev.txt` | `langsmith==0.8.3` CVE-2026-59152 (runtime; fixed 0.8.18); `pytest==8.3.4` PYSEC-2026-1845 (dev; fixed 9.0.3). | Bump both; re-run the suite. | XS |
| M2 | Medium | Semantic | `backend/main.py:262` vs `:283-299` | `/api/meta` reports `settings.groq_model`; `/health` reports `_active_model()`. With a non-Groq provider they disagree — the exact drift the `_active_model` docstring says was fixed. | Return `_active_model()` from `/api/meta`. | XS |
| M3 | Medium | Config | `backend/.env.example`; `backend/llm.py:36, 46, 111`; `backend/config.py:448`; `frontend/src/App.tsx:9` | `.env.example` omits `LOG_LEVEL`, `VERIFY_MODEL_ON_STARTUP`, `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`. The frontend has no `.env.example`; without `VITE_API_URL` every request goes to `undefined/api/...` and fails silently as "Could not reach the server." | Add the missing variables with placeholders; add `frontend/.env.example`. | XS |
| M4 | Medium | Docs drift | `README.md:520`; `backend/budget.py:187-195, 224-228` | README names `allow`/`record` as the adapter interface; production admits via `reserve()`, and `allow`/`record` are used only in tests. | Describe `reserve` as the interface; delete `allow`/`record` or mark them test helpers. | XS |
| M5 | Medium | Reproducibility | `backend/requirements.txt` | Only top-level packages are pinned; transitive versions float, although the Dockerfile comment claims "requirements.txt pins every dependency". | Generate a lock/constraints file (`pip-compile` or `uv pip compile`) and install from it in CI and Docker. | S |
| M6 | Medium | Formatting | `ruff format --check .` → 39 files would be reformatted | No formatter is configured or gated, so style varies file to file. | Adopt `ruff format` in one mechanical commit and gate it — or leave as-is (Q4). | S |
| L1 | Low | Dead code | `backend/main.py:325-330` | The `unverified` branch returns exactly what the fall-through returns. | Collapse the branch. | XS |
| L2 | Low | Docs | `README.md:501-503` | "the 'deliberately not built' list **above**" — the list is below (`:509`). | "below". | XS |
| L3 | Low | Presentation | `README.md` (no License section); `LICENSE` = MIT | LICENSE exists but the README never mentions it. | Add a one-line License section. | XS |
| L4 | Low | Hygiene | `.gitignore:631` | `.env ` has a trailing space, so the pattern never matches (`.env*` on line 648 covers it). | Remove the line. | XS |
| L5 | Low | Correctness (frontend) | `frontend/src/App.tsx:444` | `if (payload === "[DONE]") break` exits only the inner `for`; the reader loop continues until the socket closes. Harmless today. | Use a labelled break or a flag. | XS |
| L6 | Low | Hygiene | `git log --all -- backend/venv` → added `a361223`, removed `22e6598`; 1,644 files | A Windows virtualenv lives in history, inflating every clone. | Leave it (recommended), or rewrite history — see Q3. | — |

Checked and clean: no real secrets in code or history (the one `gsk_` hit, `tests/test_health.py:94`, is a fabricated fixture); no `.env` ever committed; CORS is an explicit allowlist with no wildcard (a preflight from `https://evil.example` returns 400); request bodies are pydantic-validated (422 on empty message, wrong types, invalid JSON); errors return the exception class name only; the repair path is straight-line, one retry at most; ruff lint and eslint pass; the frontend builds; session stores are bounded (`TTLCache` 500 entries / 1 h) and the UI's "clear" resets to a new session.

Not verified: the Docker build (Docker is not installed on the review machine); Python 3.11 (reviewed on 3.12.10, which the README lists as working).

## 3. Claimed vs. reproduced

### 3.1 README figures

| README claim | Where | Reproduced | Match |
|---|---|---|---|
| 231 tests | `:469` | 362 passed, 0 failed (`pytest tests/`, Py 3.12.10) | ✗ (H6) |
| Golden set: 18 cases, 100 % schema-valid, 100 % compliance | `:406-408, 470` | 18 cases in `golden_formulas.json`; `test_golden_eval.py` passes | ✓ |
| Routing eval: 46 briefs, 100 % intent, 100 % ruleset activation | `:418, 471` | `eval.live_eval --offline --gate`: 46/46, 46/46, 37/37 constrained | ✓ |
| 34 ingredients, dataset `2026.09.0` | `:467` | Repo 34 / `2026.09.0`; **live demo 34 / `2026.07.0`** | ✗ live (B3) |
| "every row with a full nutrient vector" | `:467` | 5 FDC dairy rows carry a zero-defaulted `sugars_g` | ✗ (B1) |
| Model-authored numbers reaching a user: 0 | `:468` | Formula path: holds. Q&A path: 2/3 answers invented values. Live baseline: 0/37 formulas have number-free prose (flagged in the UI) | ✗ (B2) |
| At most 1 repair per request | `:472` | Confirmed by reading: `main.py:95-122` has no loop | ✓ |
| Cold start ≈ 45 s | `:19-21` | 43.2 s to first `/health` | ✓ |
| Rate limit 30/min, budgets 2 M / 50 k, CORS allowlist | `:208-228` | Defaults match `config.py:441-444`; per-session cap bypassable (H5) | partial |
| Live baseline not yet recorded | `:539-545` | Live baseline recorded 2026-09-04, 46 cases | ✗ (H7) |
| Node 20.19+ / 22.12+ | `:296` | Built clean on Node 22.22.2 | ✓ |

### 3.2 Retrieval — five realistic queries (top results, `search_foods`)

| Query | Top results | Relevant? |
|---|---|---|
| How much potassium is in whole milk? | Milk whole; Almond milk; Egg whole; Skim milk | ✓ first hit correct |
| Which sweetener is best for a diabetic ice cream? | Coconut cream; Cream cheese; Heavy cream; Dextrose | ✗ no polyol, allulose or sucralose |
| What's a good low-phosphorus protein source? | Buttermilk low fat; Micellar casein; NFDM; Soy isolate | ✗ ranks on "low", not on phosphorus |
| Compare coconut cream and heavy cream for fat content | Heavy cream; Coconut cream; Coconut oil; Cream cheese | ✓ |
| What stabilizer should I use to reduce iciness? | Carrageenan; Guar gum; Locust bean gum | ✓ |

### 3.3 Hallucination guard — three live Q&A cases

| Question | In governed data? | Answer | Grounded? |
|---|---|---|---|
| Vitamin D and magnesium in whole milk per 100 g | No (not tracked) | "~0.1 µg vitamin D, ~10 mg magnesium… from USDA FoodData Central" | ✗ invented, false citation |
| Phosphorus content of oat milk | No (not in library) | "≈ 30 mg/100 g… USDA entry 'Oat milk, unsweetened, fortified'… ½ % DV" | ✗ invented, false citation, arithmetic wrong |
| Potassium in heavy cream vs skim milk per 100 g | Yes | 97 mg and 167 mg | ✓ matches library |

## 4. Questions for you

1. **The brief you pasted describes FormulaForge as Llama 3.3 70B over a 1,000-row USDA dataset.** The repo runs `openai/gpt-oss-120b` over a 34-ingredient governed library (the Llama models were retired by Groq — `config.py:396-400`). Is the brief's description also on your résumé, LinkedIn or portfolio? If so, it contradicts the repo a reviewer will open.
2. **B1 changes the dataset.** The fix bumps it to `2026.09.1` and may change golden-set results and README figures. OK to proceed, with any changed number reported back to you?
3. **Committed venv in history (L6).** Purging it needs a force-push that rewrites every commit SHA and breaks existing clones and PR links. I recommend leaving it. Agree?
4. **Formatter (M6).** Adopt `ruff format` in one mechanical 39-file commit, or keep the current style?
5. **B2 direction.** Enforce (ground the Q&A prompt and flag numbers in the UI) *and* rescope the README claim — or rescope only?
6. **B3 redeploy.** I have no Render access. Will you redeploy from `main` once the fixes land, and set `APP_VERSION` to the commit SHA?
7. **The renal template** returned almond milk + coconut cream + MCT oil + erythritol as a "verified" renal vanilla. Is a dairy-free result the intended behaviour for a renal brief, or should renal prefer a dairy base within the limits? (Asked, not filed: it is a formulation judgement, not a code defect.)

## 5. Proposed fix order

1. **B1** sugars zero-default — after your OK on Q2 (verdict-changing, safety-relevant).
2. **B2** Q&A grounding, labelling and claim scope — per Q5.
3. **H6, H7, H1, L2, L3** — the cheap README corrections, plus the hero image; one docs commit apart from H1.
4. **H2 + H3** — non-blocking LLM calls and a provider timeout (one small, tested change).
5. **H4** — question-shaped follow-ups stop hijacking iteration.
6. **H5** — per-client budget key and README correction.
7. **H9, M1** — dependency bumps; move `shadcn` to devDependencies.
8. **H8** — retrieval stopwords and role scoring.
9. **M2–M5, L1, L4, L5** — small correctness and hygiene items.
10. **B3** — you redeploy once `main` has the above (Q6).

## 6. Fix status

Approved 2026-10-01: fix all findings, both halves of B2, leave history (L6), skip the
formatter (M6). Every commit that touched code was followed by the full suite, ruff, the
offline routing eval, and (for frontend changes) eslint and a production build.

| ID | Status | Commit | Notes |
|---|---|---|---|
| B1 | Fixed | `709ac5a` | Dataset rebuilt from the FDC CSVs as **`2026.10.0`** (planned `2026.09.1`; date-versioned to the rebuild). Only `sugars_g` and provenance changed. Golden set and routing eval still 100 %. |
| B2 | Fixed | `3a45ebd` | Grounded prompt, server-side figure check, UI label, scoped README claim. Re-run live: both out-of-library questions now answer "not in the governed library"; the in-library one is reported grounded. |
| B3 | **Open — needs you** | — | Redeploy Render from `main` after merge; set `APP_VERSION` to the commit SHA and `FORWARDED_ALLOW_IPS=*` (see H5). |
| H1 | Fixed | `1cf1e3a` | Captured from the local stack on `2026.10.0`. |
| H2 | Fixed | `0460d23` | `/health` regression test fails at 1.03 s with the inline calls restored. |
| H3 | Fixed | `0460d23` | 30 s / 1 retry, `LLM_TIMEOUT_S` / `LLM_MAX_RETRIES`. |
| H4 | Fixed | `a99ef88`, `05e658d` | The second commit fixes a second cause found while verifying in the browser: the bare-noun "formula" rule also routed questions to the formulator. Routing eval still 46/46. |
| H5 | Fixed | `5a296da` | Per-address cap `CLIENT_DAILY_TOKENS` (200 k). Needs `FORWARDED_ALLOW_IPS=*` on Render to be per-caller rather than shared. |
| H6 | Fixed | `344152a` | 408 tests. |
| H7 | Fixed | `522be2c` | Live baseline table added; note that it predates `2026.10.0` and the Q&A check. |
| H8 | Fixed | `2a3c512` | The five review queries pinned in `TestSearchRelevance`. |
| H9 | Fixed | `4271e8f` | `npm audit`: 0. Linux native bindings for the new rolldown/lightningcss are in the lockfile; Linux `npm ci` not run locally (no WSL distro) — CI will confirm. |
| H10 | Fixed | `66d5aad` | New finding; end-to-end test fails without the fix. |
| M1 | Fixed | `4271e8f` | `pip-audit`: none. pytest-asyncio 0.24 → 1.4 for pytest 9. |
| M2 | Fixed | `42e4000` | |
| M3 | Fixed | `ec80772` | Adds `frontend/.env.example`. |
| M4 | Fixed | `5a296da` | `allow`/`record` removed with H5. |
| M5 | Fixed | `c90b4e1` | `constraints.txt`, referenced from `requirements.txt`. Generated on Python 3.12; CI (3.11) will confirm. |
| M6 | Skipped | — | Your call. |
| L1 | Fixed | `42e4000` | |
| L2, L3 | Fixed | `522be2c` | |
| L4 | Fixed | `ec80772` | |
| L5 | Fixed | `734e935` | |
| L6 | Left as-is | — | Your call. |

### Numbers that changed

| Figure | Before | After |
|---|---|---|
| Dataset version | `2026.09.0` | `2026.10.0` |
| Test suite | 231 claimed / 362 actual | 408 |
| Golden set, routing eval | 100 % / 100 % | unchanged |
| `npm audit` / `pip-audit` | 15 / 3 | 0 / 0 |
| README "What it comes to" | no live figures | live baseline with intervals |

The live eval baseline (2026-09-04) was not re-run: a full run costs ~200 k tokens. It is
worth re-recording after deploy, since B1, B2, H4 and H10 all touch what it measures.
