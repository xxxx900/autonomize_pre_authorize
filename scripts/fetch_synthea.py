"""Fetch the pinned Synthea R4 sample and copy the ten evaluation patients into resources/synthea.

Runs in a container: `docker compose -p <project> --profile synthea run --rm fetch-synthea`.
The patient choice and the reason for each is data below; docs/evaluation.md explains it.
"""

import hashlib
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from app.config import REPO_ROOT

URL = (
    "https://synthetichealth.github.io/synthea-sample-data/downloads/"
    "synthea_sample_data_fhir_r4_nov2021.zip"
)
SHA256 = "6d3c5433bcae4791bc5c30469d1445b430fb4894d5c13bda15fee0584bbd7778"
TARGET = REPO_ROOT / "resources" / "synthea"

# Patient bundles reference Practitioner, Organization and Location by conditional identifier
# search; these two bundles hold those resources and must load first.
SHARED = (
    "hospitalInformation1637345232350.json",
    "practitionerInformation1637345232350.json",
)

PATIENTS = {
    "Loretta235_Bosco882_509f9a77-2a22-f98b-c539-9a44057efb51.json": (
        "T2DM active, HbA1c 7.46 four days before the request date, no metformin record"
    ),
    "Lorinda137_Rosenbaum794_d362f4e5-244f-cf80-f2d5-25bcd2c97785.json": (
        "T2DM active, HbA1c 7.49 inside the 90-day window, no metformin record"
    ),
    "Meghan514_Jacobson885_40ef2428-c142-6e65-8e0e-0ee4098dda28.json": (
        "T2DM active, HbA1c below 7, metformin renewed yearly as stopped + active requests"
    ),
    "Felton646_Pouros728_be82309d-1a8f-df82-4cd6-5f03e1060e8e.json": (
        "T2DM active, eGFR below 30 (the C3 contraindication path), no metformin record"
    ),
    "Ula130_Medhurst46_d57e867e-4896-9e07-f502-5f4f881bd80e.json": (
        "T2DM active, active metformin request just under 90 days old"
    ),
    "Benny518_Tillman293_060e72d3-912e-55cd-0c92-5faa6cb7a6db.json": (
        "T2DM active, latest HbA1c just outside the 90-day window"
    ),
    "Shonna561_Cassin499_eb7cffc3-28d2-e8b0-72bc-8e86860ed313.json": (
        "T2DM active but the member died in 2016; the policy has no deceased criterion"
    ),
    "Tomiko229_Ratke343_dba87de8-9e28-0140-47c4-9419277178f0.json": (
        "No T2DM: prediabetes with an in-window HbA1c below 7"
    ),
    "David908_Dicki44_f7130650-ec26-4a43-fc30-ac3f05cc793d.json": (
        "No T2DM, age 16 on the request date (C5 not_met)"
    ),
    "Lemuel304_Lueilwitz711_c628b9c2-31de-fd80-f913-2e9ad36393a9.json": (
        "No T2DM, adult with no diabetes-related record at all"
    ),
}


def download(url: str, dest: Path) -> str:
    """Stream a URL to a file and return the SHA-256 of what was written."""
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=120) as response, dest.open("wb") as out:
        while chunk := response.read(1 << 20):
            digest.update(chunk)
            out.write(chunk)
    return digest.hexdigest()


def main() -> int:
    """Download the pinned archive, check its hash, and copy the chosen patients."""
    TARGET.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "synthea.zip"
        actual = download(URL, archive)
        if actual != SHA256:
            print(f"sha256 mismatch: expected {SHA256}, got {actual}", file=sys.stderr)
            return 1
        with zipfile.ZipFile(archive) as z:
            for name in (*SHARED, *PATIENTS):
                (TARGET / name).write_bytes(z.read(f"fhir/{name}"))
                print(f"copied {name}: {PATIENTS.get(name, 'shared reference bundle')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
