"""The prior-authorization request form, as submitted by the prescriber."""

from datetime import date

from app.domain.base import Frozen


class Attestation(Frozen):
    """Values the prescriber attests to on the form. The rules compare them with the record."""

    metformin_trial_months: float | None = None
    hba1c_value: float | None = None
    hba1c_date: date | None = None
    notes: str = ""


class RequestForm(Frozen):
    """One request: who, what drug, which policy, and on what date."""

    request_id: str
    request_date: date
    policy_id: str
    patient_id: str
    requested_medication: str
    diagnosis_claimed: str
    attestation: Attestation
