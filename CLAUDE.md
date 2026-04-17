# last30days Skill

Claude Code skill for researching any topic across Reddit, X, YouTube, and web.
Python scripts with multi-source search aggregation.

## Structure
- `scripts/last30days.py` — main research engine
- `scripts/lib/` — search, enrichment, rendering modules
- `scripts/lib/vendor/bird-search/` — vendored X search client
- `skills/last30days/SKILL.md` — user-invocable skill definition (canonical Claude Code plugin path)
- `skills/last30days-v3-spec/SKILL.md` — internal v3 runtime pipeline spec (not user-invocable)

## Commands
```bash
python3 scripts/last30days.py "test query" --emit=compact  # Run research
bash scripts/sync.sh                                        # Deploy to ~/.claude, ~/.agents, ~/.codex
```

## Rules
- `lib/__init__.py` must be bare package marker (comment only, NO eager imports)
- After edits: run `bash scripts/sync.sh` to deploy
- Git remotes: origin=private, upstream=public
