# Data flow

The service has two front doors, the HTTP API and the MCP server, and both call the same `EvidencePipeline.run` in `app/api/pipeline.py`. This page shows the services, the request flow for one evidence packet, and where data is and is not allowed to go.

## Services and front doors

```mermaid
flowchart LR
    nurse["Nurse page or curl"] -->|"Bearer NURSE_TOKEN or ADMIN_TOKEN"| api
    agent["agent container<br/>ReAct loop, qwen2.5 3B"] -->|"Bearer MCP_TOKEN<br/>streamable HTTP"| gate

    subgraph compose["Docker Compose network"]
        api["api<br/>FastAPI :8000"]
        gate["BearerGate"] --> mcp["mcp<br/>FastMCP :8001"]
        api --> pipeline["EvidencePipeline.run<br/>shared pipeline"]
        mcp --> pipeline
        pipeline -->|"FHIR searches and GET by id"| hapi["hapi<br/>HAPI FHIR R4 :8080"]
        pipeline -->|"packet facts only"| ollama["ollama<br/>summary model :11434"]
        agent -.->|"tool-calling model"| ollama
        api --> audit[("audit.db<br/>SQLite hash chain<br/>audit-data volume")]
        gate --> audit
        mcp --> audit
        loader["loader<br/>one-shot"] -->|"PUT transaction bundles"| hapi
        pull["ollama-pull<br/>one-shot"] -->|"pull pinned tags"| ollama
    end

    bundles["resources/bundles<br/>resources/synthea"] --> loader
    forms["resources/requests<br/>eval/synthea_requests"] --> pipeline
```

The endpoint never calls the agent (D3). The agent is a client of the MCP server like any other, and the summary model inside the pipeline is a separate call from the agent's own tool-calling model.

## One evidence request

```mermaid
sequenceDiagram
    autonumber
    participant C as Caller
    participant A as api (or mcp tool)
    participant F as HAPI FHIR
    participant R as Rules engine
    participant M as Ollama
    participant L as audit.db

    C->>A: GET /requests/{id}/evidence + bearer token
    alt token missing, wrong, or wrong role
        A->>L: append actor, action, outcome unauthenticated or forbidden
        A-->>C: 401 or 403
    end
    A->>A: read request form from resources/requests or EXTRA_REQUESTS_DIR
    A->>F: GET Patient/{id}, then search Condition, Observation,<br/>MedicationRequest, AllergyIntolerance, DocumentReference
    F-->>A: FHIR JSON
    A->>A: parse structured fields into PatientRecord<br/>(free text has no field to land in)
    A->>R: evaluate(record, form, policy)
    R-->>A: EvidencePacket: C1 to C5, sources, missing documents,<br/>flagged documents, route
    A->>F: GET each cited source by id
    alt a cited source does not exist
        A->>L: append outcome error
        A-->>C: 502
    end
    A->>M: evidence_text(packet) inside evidence tags, plus the system rule
    M-->>A: two sentences as JSON
    A->>A: schema, forbidden-word, and faithfulness checks<br/>failure or timeout: template summary
    A->>L: append actor, role, action evidence.read, request id, outcome ok
    A-->>C: EvidencePacket with summary_source model or template
```

## Where data may go

| Data | Reaches the packet | Reaches the model | Reaches the audit log | Reaches the logs |
|---|---|---|---|---|
| Structured FHIR values (codes, statuses, dates, quantities) | Yes, as rationales, source references, and the `evidence` facts of each criterion | Yes, through `evidence_text` | No | No |
| The member's Patient id | Yes, as a source reference | No | Yes, as `context.subject` on evidence reads, with the resource types and count read | No |
| Free text (`Condition.note`, document attachments, form `notes`) | No | No | No | No |
| Request id and policy id | Yes | The request date only | Yes, as `resource` | No, only a per-call request id |
| Caller identity | No | No | Actor and role | No |
| Timings and summary trace | Yes, as `trace` | No | Yes, as `context.duration_ms` and `context.summary` | Only per-call `duration_ms` and the fallback reason |
| Model output | As `summary`, after the checks pass | Not applicable | No | No, only the exception type on fallback |
