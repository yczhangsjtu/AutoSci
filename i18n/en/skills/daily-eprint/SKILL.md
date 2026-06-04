---
description: Run or manage the daily ePrint recommendation feed. Use for one-off fresh-paper recommendations, scheduled GitHub Actions setup/status/disable, email digests, and explicit high-confidence auto-ingest through /ingest.
argument-hint: "[setup|status|disable] [--mode inform|auto-ingest] [--hours 24] [--categories <cat...>] [--max-recommendations 10] [--max-auto-ingest 1] [--send-email true|false]"
---

# /daily-eprint

> Run or manage the daily paper recommendation feed. Bare `/daily-eprint` means "run today's recommendation pass now"; GitHub Actions is only the unattended scheduler for the same pipeline.

Load references only when needed:

- `references/recommendation-and-ingest-policy.md` — evidence, LLM decision schema, confidence gate, and auto-ingest guardrails
- `references/automation-scaffold.md` — GitHub Actions setup/status behavior, secrets, artifacts, and failure modes

## Commands

- `/daily-eprint`: run a one-off recommendation pass now. If `config/daily-eprint.yml` is missing, infer defaults from the wiki and continue.
- `/daily-eprint setup`: create or repair `config/daily-eprint.yml` from `config/daily-eprint.yml.example`; ensure `.github/workflows/daily-eprint.yml` exists and that its `daily-eprint:` job's `env:` block exposes both `SEMANTIC_SCHOLAR_API_KEY` and `DEEPXIV_TOKEN` — **add the missing lines automatically** rather than asking the user to hand-edit YAML (without these exposures the prepare step rate-limits out, identical symptom to never setting the secrets); and explain required secrets. See *Setup Workflow* below for the exact patch procedure.
- `/daily-eprint status`: inspect config, workflow presence, schedule, mode, API/e-mail secret availability, and recent artifacts when available.
- `/daily-eprint disable`: set `schedule.enabled: false` in config or tell the user what to change; manual `/daily-eprint` must still work.

> When running `setup` or `status`, treat S2/DeepXiv repo secrets as required (not optional) for any daily-cadence pipeline, and point the user at [`docs/daily-eprint-deployment.md`](../../../docs/daily-eprint-deployment.md) for the full setup checklist and symptom-keyed troubleshooting.

## Inputs

- `--mode inform|auto-ingest`: default `inform`. Never infer `auto-ingest` from repo state.
- `--hours N`: pull papers from the last N hours; config/default is 24.
- `--categories <cat...>`: override configured arXiv categories.
- `--max-recommendations N`: maximum papers shown in the digest; config/default is 10.
- `--max-auto-ingest N`: cap for high-confidence auto-ingest; config/default is 1.
- `--send-email true|false`: workflow/setup preference for SMTP delivery.

## Setup Workflow

Triggered by `/daily-eprint setup`. Idempotent — re-running on a healthy repo is a no-op.

1. **Config**: if `config/daily-eprint.yml` is missing, copy from `config/daily-eprint.yml.example`. If present, leave it alone (the user's preferences are durable).

2. **Workflow file**: confirm `.github/workflows/daily-eprint.yml` exists. If absent, point the user at `docs/daily-eprint-deployment.md` and stop — re-creating the workflow from scratch is out of scope for setup.

3. **Workflow env exposures (auto-patch)**: in `.github/workflows/daily-eprint.yml`, locate the `daily-eprint:` job's `env:` block. Use the Edit tool to ensure both lines are present as siblings of `HAS_CLAUDE_CODE_AUTH`:

   ```yaml
   SEMANTIC_SCHOLAR_API_KEY: ${{ secrets.SEMANTIC_SCHOLAR_API_KEY }}
   DEEPXIV_TOKEN:            ${{ secrets.DEEPXIV_TOKEN }}
   ```

   - If both lines already exist, do nothing.
   - If only one is missing, append the missing line.
   - If the `env:` block doesn't exist at all (older workflow), insert it under the job with both lines plus the existing `HAS_CLAUDE_CODE_AUTH` / `HAS_REVIEW_LLM` flags. Do not touch any other step.
   - After any patch, tell the user what was changed and remind them to commit.

4. **Secrets check**: list which of `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`, `SEMANTIC_SCHOLAR_API_KEY`, `DEEPXIV_TOKEN`, and the optional SMTP secrets the user has configured. Use `gh secret list` when available; otherwise instruct the user to run it. Surface any missing-but-required secrets with the exact `gh secret set` command they need.

5. **Summary**: report what was created, patched, and what the user still needs to do (install the GitHub App, set missing secrets, verify with one `gh workflow run daily-eprint.yml`).

## Run Workflow

1. Resolve the Python interpreter and run the deterministic preparation:

   ```bash
   python3 tools/daily_eprint.py prepare --wiki-root wiki --out .daily-eprint/run/recommendation-context.json --out-feed .daily-eprint/run/feed.json
   ```

2. Read `.daily-eprint/run/recommendation-context.json`. Judge candidates with an LLM using the provided arXiv, wiki, Semantic Scholar, and DeepXiv evidence. Write `.daily-eprint/run/llm-decisions.json` with `decision`, `confidence`, `score`, `rationale`, `wiki_connections`, and `signals_used`. In CI inform mode, an OpenAI-compatible review LLM may do this via:

   ```bash
   python3 tools/daily_eprint.py recommend-llm --context .daily-eprint/run/recommendation-context.json --out .daily-eprint/run/llm-decisions.json
   ```

3. If mode is `auto-ingest`, use Claude Code runtime only: choose `decision: ingest` + `confidence: high`, obey `max_auto_ingest`, and invoke `/ingest <arxiv-url>` sequentially. Do not hand-write wiki or graph files. Third-party LLMs are recommendation-only and must not auto-ingest.

4. Finalize the digest:

   ```bash
   python3 tools/daily_eprint.py finalize --context .daily-eprint/run/recommendation-context.json --decisions .daily-eprint/run/llm-decisions.json --out-md .daily-eprint/run/digest.md --out-json .daily-eprint/run/digest.json
   ```

5. Report strong recommendations, maybe-interesting papers, skipped duplicates, degraded signals, auto-ingest outcomes, and setup/status hints.

## Wiki Interaction

Reads `wiki/index.md`, `wiki/papers/`, `wiki/topics/`, `wiki/concepts/`, `wiki/methods/`, `wiki/ideas/`, and `wiki/log.md` to build the interest profile and dedupe candidates.

Writes only scratch files under `.daily-eprint/` during inform runs. In `auto-ingest`, all durable wiki/raw mutations must come from `/ingest`.

## Relationships

- `/discover` answers deliberate next-read requests from anchors, topics, or wiki state; it never ingests.
- `/daily-eprint` watches the fresh arXiv stream and can notify daily or manually.
- `/ingest` is the only paper incorporation path. `/daily-eprint` may call it only in explicit `auto-ingest` mode.
