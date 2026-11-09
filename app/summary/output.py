"""The shape the model must reply in, and the check its text must pass."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.packet import EvidencePacket
from app.summary.safety import faithfulness_problems, forbidden_words, sentence_count


class SummaryOutput(BaseModel):
    """The JSON schema sent to Ollama as the required output format."""

    model_config = ConfigDict(extra="forbid")

    sentences: list[str] = Field(min_length=2, max_length=2)

    @field_validator("sentences")
    @classmethod
    def _one_sentence_each(cls, value: list[str]) -> list[str]:
        """Reject an entry that is empty or holds more than one sentence."""
        if any(not s.strip() or sentence_count(s) > 1 for s in value):
            raise ValueError("each entry must be one non-empty sentence")
        return value

    @property
    def text(self) -> str:
        """The two sentences joined into one paragraph."""
        return " ".join(s.strip() for s in self.sentences)


class Rejected(ValueError):
    """Model output parsed but failed a safety or faithfulness check."""


def check_output(text: str, packet: EvidencePacket) -> None:
    """Raise Rejected, naming every problem, when the text is unsafe or unfaithful."""
    problems = [f"forbidden word: {w}" for w in forbidden_words(text)]
    problems += faithfulness_problems(text, packet)
    if problems:
        raise Rejected("; ".join(problems))
