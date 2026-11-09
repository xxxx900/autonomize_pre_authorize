"""JSON responses indented for people: an engineer reading curl output or a browser tab."""

import json
from typing import Any

from fastapi.responses import JSONResponse


class PrettyJSONResponse(JSONResponse):
    """JSONResponse with two-space indentation. The bytes cost is negligible at this scale."""

    def render(self, content: Any) -> bytes:
        """Serialize with indentation, keeping non-ASCII text readable."""
        return json.dumps(content, indent=2, ensure_ascii=False).encode("utf-8")
