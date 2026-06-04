# Daily ePrint Automation

GitHub Actions is the unattended scheduler for `/daily-eprint`. It should run
the same pipeline as a manual slash skill pass; it should not define the
feature's user-facing purpose.

## Source of Truth

- `config/daily-eprint.yml`: durable non-secret preferences.
- `tools/daily_eprint.py`: deterministic config, feed, evidence, and digest
  helpers.
- `/daily-eprint`: LLM judgment, setup/status UX, and optional `/ingest`
  orchestration.
- `.github/workflows/daily-eprint.yml`: scheduled executor.

If `config/daily-eprint.yml` is absent, manual runs continue with inferred
defaults. `/daily-eprint setup` may copy `config/daily-eprint.yml.example`.

## Workflow Behavior

- Scheduled run: `17 0 * * *` UTC by default.
- Manual dispatch may override mode, hours, categories, caps, and e-mail.
- Inform mode prepares context, then uses the first available recommender:
  Claude Code Action with `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`;
  otherwise an OpenAI-compatible LLM via `LLM_API_KEY` / `LLM_BASE_URL` /
  `LLM_MODEL`; otherwise a tool-ranked fallback digest.
- Auto-ingest mode fails closed unless Claude Code Action auth is present.
- Auto-ingest commits only staged `wiki/` and `raw/discovered/` changes
  produced by `/ingest`.

## Secrets

Recommendation/ingest:

- `ANTHROPIC_API_KEY` — direct Anthropic API auth for Claude Code Action.
- `CLAUDE_CODE_OAUTH_TOKEN` — Claude Code OAuth auth for Pro/Max users; generate
  locally with `claude setup-token`. This is an alternative to
  `ANTHROPIC_API_KEY` for Claude Code Action.
- `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` — optional OpenAI-compatible LLM
  for `inform` recommendation when Claude Code is not available.
- `LLM_FALLBACK_MODEL` — optional fallback for the OpenAI-compatible LLM.
- `SEMANTIC_SCHOLAR_API_KEY` — required for daily-cadence runs. Anonymous-tier S2 rate limits time the prepare step out against ~1000 candidates.
- `DEEPXIV_TOKEN` — required for daily-cadence runs to enable DeepXiv enrichment without anonymous-tier throttling.

These two API keys must also be exposed as workflow env vars (see *Workflow Env Exposures* below). Storing them as repo secrets is necessary but not sufficient.

SMTP delivery:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `DAILY_ARXIV_EMAIL_TO`

Do not store secrets in `config/daily-eprint.yml`.

## Workflow Env Exposures

`.github/workflows/daily-eprint.yml` must reference S2/DeepXiv secrets in the
job-level `env:` block; otherwise the runner's process environment never
receives them and the Python prepare step silently drops to anonymous mode:

```yaml
jobs:
  daily-eprint:
    env:
      SEMANTIC_SCHOLAR_API_KEY: ${{ secrets.SEMANTIC_SCHOLAR_API_KEY }}
      DEEPXIV_TOKEN:            ${{ secrets.DEEPXIV_TOKEN }}
```

`/daily-eprint setup` auto-patches the workflow to add either line if
missing — users should not have to hand-edit YAML for this. A `gh secret
set` paired with a missing exposure is the most common reason the daily
run rate-limits out (the tester sees their secrets configured and
assumes the workflow can read them), so `setup` eliminates the gap
rather than just reporting it.

## Artifacts

Each workflow run uploads:

- `resolved-config.json`
- `feed.json`
- `recommendation-context.json`
- `llm-decisions.json` when Claude ran
- `digest.md`
- `digest.json`

The Markdown digest is also appended to the GitHub Actions job summary.

## Status Checks

`/daily-eprint status` should inspect:

- config presence and resolved mode/caps/categories
- workflow file presence and schedule
- whether `schedule.enabled` is false
- availability of local env vars or CI secrets when visible
- last local `.daily-eprint/` digest if present

## Failure Behavior

- arXiv fetch failure: fail before recommendation/finalization.
- Missing SMTP secrets: fail only when e-mail is enabled.
- Empty feed or all duplicates: produce valid empty artifacts.
- External API failures: continue with degraded notes.
- Auto-ingest failures: preserve per-paper error and continue to final digest.
