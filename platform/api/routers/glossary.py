"""
Glossary router — UI-safe term dictionary.

Serves the cross-framework gamma vocabulary dict for `<TermHover>` and
HelpPage. The Python source of truth is `lib/gamma_glossary.py`; this
router is a thin transport layer.

Public surface returns canonical name + short_definition + long_definition
+ math only. The framework aliases (Stratalyst / Heatseeker /
SqueezeMetrics / SpotGamma / plain_english) live in `GAMMA_TERMS` for
INTERNAL consumption (AI prompts, engineering reference) and are
deliberately stripped by `lib.gamma_glossary.public_glossary()` before
serialization — per `docs/plans/HEATSEEKER_STYLE_GAMMA_PLAN.md` §1.7.5.
"""
import sys
from pathlib import Path

from fastapi import APIRouter, Response

# Add project root for `from lib import ...` (same pattern as other routers)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.gamma_glossary import public_glossary  # noqa: E402

router = APIRouter()


@router.get("/api/glossary/gamma")
async def get_gamma_glossary(response: Response):
    """Return the UI-safe gamma term dictionary.

    Shape:
    ```
    {
      "terms": {
        "king": {
          "canonical": "King",
          "short_definition": "...",
          "long_definition": "...",
          "math": "..."
        },
        ...
      },
      "version": "1"
    }
    ```

    Cached aggressively (1 hour client-side); the underlying dict is a
    module constant that only changes on deploy.
    """
    response.headers["Cache-Control"] = "public, max-age=3600"
    return public_glossary()
