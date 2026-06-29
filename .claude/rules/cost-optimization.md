# Cost optimization — apply to ALL Claude calls

## Model selection
- Haiku: scoring, classification, extraction,
         keywords, highlights, essence
- Sonnet: tailoring, cover letters, career insights,
          domain CV generation, S3 integrity check
- Never use Opus unless explicitly requested

## RAG pipeline (scanner + gmail alerts)
- Stage 1: keyword pre-filter (free — no Claude)
- Stage 2: essence + Haiku (reject if < 50)
- Stage 3: full CV + Sonnet (borderline 50-74 only)
- Never send full CV to Claude if essence exists

## Caching rules
- CV essence: cache indefinitely (until CV changes)
- JD highlights: cache per job in jd_highlights_json
- Career analysis: cache 7 days
- Never re-score same jd_hash twice

## Token efficiency
- Always use CV essence_json if available
  not full CV markdown
- Truncate JD text to 2000 chars for scoring
- Truncate to 500 chars per JD for career batch

## Usage logging
- Every call: log model used (haiku vs sonnet)
- Category: scoring/tailoring/domain_cv/
            career/scanner/gmail/other
- This powers the API Usage tab transparency
