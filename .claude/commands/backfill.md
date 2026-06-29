Run the full data backfill script.

Computes ATS + Pursuit scores for all unscored jobs.

```bash
docker-compose exec backend python -c "
import asyncio
from app.scripts.backfill_all import run_full_backfill
asyncio.run(run_full_backfill())
"
```

Report:
- Jobs scored
- Average ATS and Pursuit scores
- Total cost in ₹
- Any errors
