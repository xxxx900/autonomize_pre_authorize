"""The prompt the summary model receives. Bump PROMPT_VERSION whenever its text changes."""

from app.domain.packet import EvidencePacket
from app.summary.safety import evidence_text

PROMPT_VERSION = "summary-v4"

SYSTEM_RULE = (
    "You write a two-sentence factual summary of a prior-authorization evidence packet for a "
    "nurse. Use only the facts between the <evidence> tags. Describe what the evidence shows: "
    "which criteria are met and which are not met, missing or conflicting, and what documents "
    "are outstanding. Name every criterion that is not met by its id, such as C2, and use the "
    "status exactly as given in the evidence; never describe a met criterion as unmet. Each of "
    "the two strings must be exactly one sentence. Never recommend, approve, deny, or say "
    "whether the request should or should not proceed. Never state a number or date that is "
    "not in the evidence. Reply as JSON with a sentences array holding exactly two strings of "
    "plain prose with no brackets. The first string states which criteria have status met. "
    "The second string states each remaining criterion with its exact status word (not_met, "
    "missing or conflicting) and the document or value still outstanding."
)


def build_prompt(packet: EvidencePacket) -> list[dict[str, str]]:
    """The chat messages: the fixed system rule, then the packet's evidence text."""
    return [
        {"role": "system", "content": SYSTEM_RULE},
        {"role": "user", "content": f"<evidence>\n{evidence_text(packet)}\n</evidence>"},
    ]
