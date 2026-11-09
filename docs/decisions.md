# Interpretation decisions

The policy (`resources/policy_MP-SYN-021.json`) leaves some cases open. This page records each call the rules engine makes where a careful reader could choose differently, the reasoning, and the evidence. The status meanings come from the policy's `status_semantics`:

- `met`: the record holds qualifying evidence and nothing attested contradicts it.
- `not_met`: the record holds evidence that the criterion fails.
- `missing`: the record holds no qualifying evidence either way.
- `conflicting`: a structured value on the request form disagrees with the record on a fact the criterion depends on. It takes precedence over `met` and `not_met`. Absence of a record is `missing`, never `conflicting`.

## PA-007: a resolved diagnosis is not_met

PA-007's record codes type 2 diabetes (`Condition/0327d779-72e0-5cf4-ad0b-b0da948d987f`, SNOMED 44054006) with clinical status `resolved`. The same record shows HbA1c 8.4% on 2026-09-20 and 365 days of metformin before the request date. C1 requires the diagnosis with status `active`, `recurrence`, or `relapse`.

The engine reports C1 as `not_met`, with the condition as its source. The record holds a T2DM diagnosis whose status fails the requirement, which is what `not_met` means. `missing` would claim the record has no diagnosis, and it has one. `conflicting` needs the form to disagree with the record, and the form claims the same code the record holds. Only the status differs, and status is not a field on the form.

A clinician will find the resolved status implausible next to a current HbA1c of 8.4% and active metformin. That is the point of reporting it. The packet shows the coded status and the evidence that contradicts it clinically, and the clinician decides which to believe. The engine does not "correct" the coded status, because that would be the engine making a clinical judgment.

## PA-004: a conflicting attestation outranks a met intolerance path

PA-004's form attests 6 months of metformin. The record holds one metformin prescription, `MedicationRequest/061087a3-cb71-5a24-9142-ff5c46ddfc92`, valid from 2026-02-01 to 2026-02-22: 21 days, or 0.7 months. The record also holds a metformin intolerance (`AllergyIntolerance/5343aadb-9d69-59eb-9aac-e96f129206b1`, RxNorm 6809, active), which by itself satisfies C3.

The engine reports C3 as `conflicting`. The policy says `conflicting` takes precedence over `met`, and the form's 6 months disagrees with a record that bounds the trial at 21 days. A reviewer who sees only `met` would never learn that the prescriber's statement does not match the chart, and an attestation that is wrong by a factor of eight is worth a clinician's attention even when another path would satisfy the criterion. The packet's rationale and its `conflicts` entry give both values and the prescription that supports the record's value.

## C4: no exclusion condition counts as met

C4 asks for no history of pancreatitis, medullary thyroid carcinoma, or MEN2. The engine reports `met` when the record holds none of the listed codes, and `not_met` when it holds one in any clinical status, so PA-005's resolved pancreatitis (`Condition/dd477d57-af4b-5b2d-beca-5a3c27d29b20`) is `not_met`.

The alternative is to report absence as `missing`, since a FHIR record cannot prove a negative. That reading would make C4 `missing` for nearly every member and send every request to clinician review for a reason that no document could resolve. No provider can send a document proving the absence of a disease. The engine takes absence of an exclusion as `met`, and the rationale says what it searched for. This is a design choice, not something the policy states, and plan section 5 marks it as one.

## C3: the 90-day test is clipped, the attestation check is not

C3 has two durations, and they answer different questions.

- The 90-day test asks how much metformin falls inside the 12 months before the request. The engine clips each prescription interval to that window before it adds them up.
- The attestation check asks whether the prescriber's `metformin_trial_months` matches the record. A trial is a trial whenever it happened, so the engine compares against the full, unclipped duration (days divided by 30.44).

PA-001 shows why the difference matters. Its metformin prescription (`MedicationRequest/2aa57af5-c935-5747-aa4e-aaf41415ba1b`) runs from 2025-07-15 to the request date 2026-10-01, which is about 14.6 months. Clipped to the window, it is 365 days, or 12.0 months. The form attests 14 months. Against the clipped value the attestation exceeds the record by 2 months, beyond the 1-month tolerance, and C3 would wrongly become `conflicting`. Against the unclipped value it agrees.

## Metformin prescriptions with no end date are not counted

The policy defines a prescription's duration as "from authoredOn to dispenseRequest.validityPeriod.end, or to the request date if still active." A prescription with status `stopped` and no `validityPeriod` has no defined duration. The engine leaves it out of the day count and adds to the `not_met` rationale how many prescriptions it left out.

Synthea writes chronic medication this way. It issues a new metformin request at each annual visit and marks the previous one `stopped` without an end date. SYN-005's member has 24 stopped metformin requests going back to 2004 and one active request from 2021-08-31, so the engine counts 80 days and reports C3 `not_met`. A clinician reading the same chart would likely conclude seventeen years of therapy. The engine does not infer that each request lasted until the next one. That inference is plausible for Synthea, but it is not in the policy, and in real data a stopped prescription often means the patient stopped. The packet lists every prescription as a source, so the reviewer can see the history. The right fix is better evidence, such as `MedicationDispense` fill history, not a guess in the engine.

The same gap caused the one engine bug the evaluation found. Before 9cbd356, a prescription with an unknown duration counted as zero days in the attestation check, so SYN-003's attested 12 months was reported as `conflicting` against "1.0 months". The record does not contradict 12 months. It holds metformin requests from 2018 onward with unknown durations. The attestation check now runs only when every prescription has a known end. See [the evaluation](evaluation.md#findings).

## Codes match exactly, without a terminology service

The policy says to match the listed code "or any descendant, or on the ingredient or display where a terminology service is unavailable." The MVP has no terminology service, so the engine matches:

- C1 on SNOMED 44054006 exactly. A descendant code such as "Neuropathy due to type 2 diabetes mellitus" (368581000119106) does not satisfy C1 on its own. In every Synthea record evaluated, the parent code 44054006 is also present.
- C2 on LOINC 4548-4 and the eGFR path of C3 on LOINC 33914-3 exactly.
- Metformin on RxNorm 6809 (ingredient) or 860975 (the policy's example product), or on a display that contains "metformin". The display rule is what the policy allows in place of an ingredient lookup.
- C4 on the three listed SNOMED codes exactly. A record that coded only a descendant, such as a specific form of acute pancreatitis, would pass C4 as `met`. That is the most serious gap of exact matching, because it errs toward a met exclusion criterion. A terminology service with `$subsumes`, or a curated descendant list for the three codes, closes it.
- C1's `conflicting` path on a different diabetes type, which today means type 1 (46635009) only.

## A deceased member gets an ordinary packet

SYN-007's member has `Patient.deceasedDateTime` 2016-07-21, five years before the assumed request date. The policy has no criterion about death, so the engine computes C5 from the birth date as for anyone else and reports the member as 59. The hand audit expected the same statuses, because the policy gives no other answer. The engine could add the date of death to the packet as a flagged fact without changing any status. That is a small addition for a later version.

## The Synthea request date is 2021-11-19

The supplied requests carry their own request date. The ten Synthea requests are written for this evaluation, so their date is a choice. Every request uses 2021-11-19, the day the sample was generated. Synthea simulates each life up to that day, so it is the latest date for which the records are complete, and the 90-day HbA1c window and the 12-month metformin window both fall on recent data. One shared date also means the windows were not tuned per patient to produce a status.

# Engineering decisions

These are design choices rather than readings of the policy.

## The policy is chosen by the request, not a dropdown

Each request form names its `policy_id`, and [`EvidencePipeline.load_form`](../app/api/pipeline.py) refuses a form whose policy the service does not hold (422). The policy is not a reviewer's choice. A dropdown would let a reviewer pick the policy that produces the answer they want, and the audit row would then have to explain why that policy was used.

A second policy also needs code, not just a file. The rules read thresholds and code lists from the policy JSON, but the criteria themselves are typed to MP-SYN-021 (`policy.c1` to `policy.c5` in [`app/domain/policy.py`](../app/domain/policy.py)). A new version of the same policy, such as a changed HbA1c threshold, is a new file set through `POLICY_FILE`, and its hash appears in every packet and audit row. A different policy, such as one for SGLT2 inhibitors, needs its own criteria module and a registry keyed by `policy_id`. That registry is the week-six change. A dropdown is not.

## The summary model is picked from an allow-list

`SUMMARY_MODEL` is the default and `SUMMARY_MODEL_CHOICES` lists the other models a caller may pick. The worksheet fills its "Summary model" dropdown from [`GET /catalog`](../app/api/routes/catalog.py) and sends `?summary_model=` with the evidence request. A name outside the list gets a 422, and the refusal is audited, so a caller cannot make Ollama pull or run an unvetted model. The chosen model is recorded in the packet's `trace.summary.model` and in the audit row, and every model's output goes through the same checks in [`app/summary/output.py`](../app/summary/output.py). `GET /health/details` reports any allowed model that is not pulled.

The agent's model is `AGENT_MODEL`, or `--model` for one run. It is a command-line tool, so it has no dropdown.

## The policy lookup stays a keyed tool, not RAG

The MCP tool `get_policy` returns the whole structured policy, and the rules read it by key. Retrieval-augmented generation would embed the policy text, retrieve the chunks nearest a query, and put them in the model's prompt. For this service RAG would cost more than it gains:

- **It answers a question nobody asks here.** RAG finds relevant text in a corpus too large for the prompt. MP-SYN-021 is one 5-criterion JSON file, and the request names it. There is nothing to search.
- **The model does not read the policy.** Statuses come from deterministic rules (D1). The summary model sees only the finished packet (D2). Retrieved policy text would reach only the agent's narration, which is labelled "not evidence".
- **Retrieval is non-deterministic and can be partial.** Chunking can split a criterion from its exception, such as C3's intolerance path. The packet cites the exact clause and the policy file's SHA-256, and a retrieved chunk cannot give the same guarantee.
- **It adds an injection path (LLM01) and infrastructure.** Retrieved text goes into the prompt, so the corpus becomes an instruction surface. It also brings an embedding model, a vector store inside the BAA, and retrieval metrics to evaluate.

RAG would pay off in a different job: a payer library of hundreds of free-text policy PDFs. There, retrieval helps a policy analyst find the right policy and draft its structured criteria, and a human reviews the result before it becomes a rules file. That is authoring assistance outside the request path, a candidate after week six.
