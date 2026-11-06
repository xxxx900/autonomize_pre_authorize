# FDE Assignment v2 data pack (synthetic)

All data is synthetic and invented for interview use. Load every bundle in bundles/ into any FHIR R4 server that accepts transaction bundles (HAPI FHIR in Docker is the easiest; entries use PUT with fixed ids, so loading is idempotent), alongside any Synthea sample. Request forms are in requests/. The policy is policy_MP-SYN-021.json. Request date is in each form.

Notes: HAPI accepts the PUT entries as-is (ids preserved; a reload returns 200 and keeps version 1). Synthea patient bundles use POST, so a naive reload duplicates them; make your loader idempotent. The largest Synthea sample bundles need a 4 GB Java heap (JAVA_TOOL_OPTIONS=-Xmx4g) on HAPI. The current Synthea 'latest' sample has about 109 patients, few with type 2 diabetes; any Synthea sample is fine for the audit.

Files:
- requests/PA-001.json  ->  bundles/PA-001.json  (patient 1805a90b-326d-5089-845f-185dae4679fd)
- requests/PA-002.json  ->  bundles/PA-002.json  (patient 6c1c6863-68ff-5463-9265-82ff32b83ab1)
- requests/PA-003.json  ->  bundles/PA-003.json  (patient db62ce62-d28b-5506-9913-fb2e6bbde087)
- requests/PA-004.json  ->  bundles/PA-004.json  (patient cbe7cb0a-bbe9-5590-b325-609a9467084b)
- requests/PA-005.json  ->  bundles/PA-005.json  (patient 9ad895eb-7cc3-5e8f-a557-c0e33552f250)
- requests/PA-006.json  ->  bundles/PA-006.json  (patient bfa29189-5f0f-58c3-a1ed-5592f838790f)
- requests/PA-007.json  ->  bundles/PA-007.json  (patient 5b2b65b1-e350-56fd-95a0-512da5b8e5a5)
