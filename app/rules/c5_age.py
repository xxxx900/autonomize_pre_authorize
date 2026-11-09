"""C5: the member is an adult on the request date."""

from datetime import date

from app.domain.enums import CriterionId, Status
from app.domain.packet import CriterionResult
from app.domain.policy import Policy
from app.domain.record import PatientRecord
from app.domain.request_form import RequestForm
from app.rules.result import criterion_result

CID = CriterionId.C5


def age_on(born: date, on: date) -> int:
    """Whole years from birth to the given date."""
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def c5_age(record: PatientRecord, form: RequestForm, policy: Policy) -> CriterionResult:
    """Met at or above the minimum age on the request date; missing without a birth date."""
    if record.birth_date is None:
        return criterion_result(
            policy,
            CID,
            Status.MISSING,
            "No birth date in the record",
            missing_document="Member date of birth",
        )
    on = form.request_date
    age = age_on(record.birth_date, on)
    status = Status.MET if age >= policy.min_adult_age else Status.NOT_MET
    return criterion_result(
        policy,
        CID,
        status,
        f"Age {age} on {on}; minimum {policy.min_adult_age}",
        [record.patient_ref],
    )
