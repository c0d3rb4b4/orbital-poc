<!-- COVER -->

# Orbital Customer Account Integration POC

## A case study in semantic integration with Taxi

Adobe, SAP and FWT customer-account updates using Orbital, Taxi, RabbitMQ and a narrow Python transport bridge

**Prepared:** 30 July 2026<br/>
**Document status:** Implementation case study<br/>
**Scope:** Selected-slice POC; not production-ready

> **Recommendation**
>
> Pilot the Taxi model with production-grade connectivity. Do not replace Azure transport based on this POC; decide broker migration separately.

<!-- PAGE BREAK -->

## Contents

1. Summary
2. Requirement and scope
3. Solution
4. Implementation lessons
5. Evidence
6. POC compared with the current Azure BIP
7. Recommendation
8. Technical reference
9. Source traceability

## Scope note

This document compares the POC with the customer-account implementation in the local `bip` repository. It does not compare every Orbital or Azure capability. Evidence comes from code, fixtures, tests, package health and local smoke tests—not production load, security or cost studies.

<!-- CONTINUE PAGE -->

# 1. Summary

## Bottom line

- **Semantic reuse worked.** Shared Taxi facts drove a selected update slice across Adobe, SAP and FWT without forcing one physical customer DTO.
- **The POC is not production-ready.** Real endpoints, full field parity, retries, idempotency, HA, security and operational ownership were not proven.
- **Keep the Taxi model; test transport separately.** The next test should combine Orbital projections with existing Azure connectivity or a supported native connector.

## POC snapshot

| Question | Answer |
|---|---|
| Fixture routes exercised | Adobe→SAP, Adobe→FWT, SAP→Adobe, SAP→FWT |
| Semantic model | 11 healthy Taxi sources; 0 warnings; 0 errors |
| Messaging | 4 business queues, 4 DLQs, 8 explicit bindings |
| Transport adapter | 1 Python image in 3 configured roles |
| Automated checks | 41 bridge tests plus Ruff and byte compilation |
| Production systems | None; SAP is a queue/fixture and Adobe/FWT are stubs |
| Strongest result | Reusable Taxi semantics across three wire contracts |
| Largest gap | No production connector, resilience, security or ownership proof |

# 2. Requirement and scope

## Requirement

The POC had to:

1. project Adobe customer updates into SAP IDoc shape;
2. project SAP updates back into Adobe shape;
3. simulate the SAP boundary and Azure Service Bus fan-out with RabbitMQ;
4. add FWT as an outbound target for both origins; and
5. reuse Taxi business definitions while preserving system-owned contracts.

## Azure baseline

| Area | Current BIP implementation | POC substitute |
|---|---|---|
| Orchestration | Logic Apps and Azure Functions | Orbital saved queries |
| Messaging | Azure Service Bus topic/subscriptions | RabbitMQ topic exchange and queues |
| Mapping | C# DTOs, mappers and reference-data services | Taxi facts, contracts and projections |
| SAP boundary | SAP connector and gateway | Retained queue plus XML fixture |
| Adobe/FWT targets | Authenticated HTTP clients | Nebula capture endpoints |
| Operations | Azure workflow, archive and notification patterns | Local health, logs, ACK/DLQ and runbook |

## POC scope

| Included | Simulated | Not tested |
|---|---|---|
| Selected Adobe, SAP and FWT update fields | SAP target and SAP-origin producer | Create flows and full contract parity |
| Taxi types, enums, projections and services | Adobe and FWT HTTP endpoints | Real credentials, gateways and reference data |
| Persistent routing, confirms, ACK and DLQ | Local Docker deployment | Retry/replay, idempotency, ordering and HA |
| Synthetic fixtures and expected payloads | Manual smoke-test injection | TLS, least privilege, DR, load and TCO |

# 3. Solution

## Architecture

![Architecture showing Adobe and SAP inputs flowing through reusable Taxi projections, the transport-only bridge and RabbitMQ layer, and independent SAP, Adobe and FWT outcomes](assets/case-study-architecture.png)

**Figure 1 — POC architecture.** Taxi owns business meaning and projection. The bridge and RabbitMQ own transport. Green nodes are sources or simulated outcomes.

## Routes

Queue names below omit the common `poc.customer-account.` prefix.

| Origin | Routing key → queue | Consumer | Outcome |
|---|---|---|---|
| Adobe | `customer-account.adobe.updated`<br/>→ `adobe-to-sap` | None | Retained simulated SAP inbox copy |
| Adobe | `customer-account.adobe.updated`<br/>→ `adobe-to-fwt` | FWT worker | FWT POST capture |
| SAP | `customer-account.sap.updated`<br/>→ `sap-to-adobe` | Main bridge worker | Adobe PUT capture |
| SAP | `customer-account.sap.updated`<br/>→ `sap-to-fwt` | FWT worker | FWT POST capture |

Bindings route only those four source-to-target paths. No FWT-origin route exists. This is topology-level loop prevention only; production idempotency and source suppression remain open.

The retained Adobe→SAP copy does not emit a SAP return; SAP-origin tests are injected separately. This reproduces local fan-out behaviour, not BIP topology or wire-format parity—RabbitMQ carries SAP XML.

## Semantic reuse

Taxi keeps each wire contract independent and maps equivalent business concepts through narrow types and enum synonyms.

| Business fact | Adobe | SAP | FWT | Rule |
|---|---|---|---|---|
| SAP identity | `sap_unique_id` custom attribute | `KUNNR` | `id` | Preserve as a string, including leading zeroes |
| Adobe identity | Adobe `id` | Not equivalent to `KUNNR` | Not required | Supply an explicit cross-reference for SAP→Adobe |
| Status | Adobe status string | `KATR5` code | FWT status string | Link with shared enum meaning |
| Contact preference | Email/post flags | `KATR10` code | Email/post booleans | Combine once; expand per target |
| Date of birth | `yyyyMMdd` | `RGDATE` | `yyyy-MM-dd` | Apply deterministic formatting |
| Name/address | Nested JSON | IDoc segments | Nested JSON | Keep target ownership and field meaning |

Shared fixture values can hide the Adobe-ID/SAP-`KUNNR` distinction. The POC therefore preserves SAP leading zeroes and requires an explicit Adobe cross-reference.

## Component roles

| Component | Owns | Does not own |
|---|---|---|
| Taxi | Facts, code equivalence, derivations and target shapes | Broker lifecycle |
| Orbital | Taxi compilation, saved queries and HTTP service calls | AMQP transport in this stack |
| Python bridge | Metadata validation, XML/JSON adaptation, publish/consume and ACK | Customer mapping rules |
| RabbitMQ | Durable route copies, confirms, delivery and DLQ routing | Semantic transformation |
| Nebula | Observable Adobe/FWT test responses | Persistence or production behaviour |

The bridge exists because this deployed workspace has HTTP connectivity but no configured supported AMQP Taxi connector. A supported native connector can replace it without changing the Taxi mappings.

## Delivery lifecycle

![Sequence showing separate Adobe and SAP ingress paths, confirmed RabbitMQ publication, independent route delivery, acknowledgement after success, and route-specific dead-lettering after failure](assets/case-study-sequence.png)

**Figure 2 — Publish and route delivery.** Each consumed route copy uses `prefetch=1`, is acknowledged only after its Orbital saved query returns 2xx following the target call, and is dead-lettered independently on failure. Ingress success confirms publication—not every subscriber. Adobe→SAP remains unconsumed as the simulated target.

# 4. Implementation lessons

## Implementation path

![Three-stage implementation journey from the core Adobe and SAP routes through a typed FWT extension to local verification](assets/case-study-journey.png)

**Figure 3 — Implementation path.** Core routes came first, the shared model was extended to FWT, then local verification was added.

## Challenges

The XML findings below apply to the tested Orbital 0.38 version and configuration; they are not product-wide claims.

| Issue | Response | Lesson |
|---|---|---|
| Primitive-heavy Taxi model produced warnings | Added narrow facts, distinct identities and enum synonyms | Reuse meaning, not `String` compatibility |
| No configured AMQP connector | Added a transport-only FastAPI/Pika bridge | Keep adapters small and replaceable |
| Orbital 0.38 could not serialize outbound `@Xml` model on this path | Taxi builds a plain parameter model; bridge emits XML | Separate projection from wire serialization |
| Concurrent XML parsing raised `FWK005` | FWT workers adapt XML to equivalent JSON | Test fan-out concurrently |
| SAP number could be mistaken for Adobe ID | Required explicit Adobe cross-reference metadata | Resolve identities explicitly; do not treat one system ID as another |
| Active queues appeared empty | Correlated queue, worker, DLQ and target-capture evidence | An empty queue does not prove failure |
| Idle publish connection could return 503 | Close failed connection; reconnect on next call | Do not retry uncertain publishes without idempotency |
| Source and runtime topology deploy separately | Coordinated Git, Compose and Rabbit definitions | Treat them as one release |
| Adobe and later SAP confirmation can both reach FWT | Left duplicate policy explicit and unresolved | Fan-out can duplicate effects without forming a loop |

# 5. Evidence

## Results

| Claim | Evidence | Status |
|---|---|---|
| Shared semantics span three contracts | Taxi facts/enums drive Adobe, SAP and FWT shapes | Proven for selected fields |
| Adobe reaches simulated SAP | Expected XML reaches retained SAP queue | Proven with fixture |
| Adobe reaches FWT independently | FWT route ACK plus expected capture | Proven with fixture |
| SAP reaches Adobe and FWT independently | Two ACKs plus both expected captures | Proven with fixture |
| Delivery mechanics are explicit | Persistent publish, confirms, ACK and route DLQ | Component pattern proven |
| Taxi package is clean | 11 sources; healthy; 0 warnings; 0 errors | Proven in tested workspace |
| Bridge component is tested | 41 tests plus Ruff and byte compilation | Proven at component level |
| Production replacement readiness | Real systems, parity, resilience and security untested | Not proven |

## Evidence limits

- Fixtures prove a selected update slice, not complete BIP or FWT behaviour.
- Unsupported FWT fields were deliberately excluded until authoritative, deterministic sources are available.
- The bridge tests use fakes and HTTP mocks; full broker-to-Orbital assertions are still partly manual.
- Nebula captures requests but is not a contract-testing or system-of-record service; concurrent matching is unsafe until captures record lineage/correlation IDs.
- A `202` proves a confirmed routable publish, not all downstream completion.
- Persistent messages do not imply exactly-once delivery, HA or zero loss.
- No load, failover, security, cost or production comparison test was run.

# 6. POC compared with the current Azure BIP

## Comparison

| Dimension | Orbital/Taxi POC | Current Azure BIP |
|---|---|---|
| Semantic modelling | Typed facts, enum synonyms and compiler feedback make intent explicit | Broader production mapping exists, but intent is spread across C#, schemas and workflows |
| Adding a target | FWT reused existing facts and one shared projection | Established Function/Logic App patterns and larger connector ecosystem |
| Transport | Explicit per-edge queues, ACK and DLQ state | Managed Service Bus and real SAP gateway/connector path |
| Reliability | Confirms, persistence and manual ACK demonstrated | Inspected Function actions disable retry; deployed Service Bus settlement, max-delivery and connector policies were not verified |
| Local development | Fast Docker, RabbitMQ, fixtures and Nebula loop | Production telemetry exists, but isolated end-to-end local testing is harder |
| Security | Safe synthetic environment only | Existing OAuth/connector resources; the POC did not test equivalent controls |
| Coverage/maturity | Update-only selected slice; runtime workarounds and custom bridge | Create/update and much broader SAP/FWT mapping |
| Cost/performance | Unknown | Unknown; no benchmark or TCO comparison was performed |

## Open decisions

| Issue | Why it matters | Decision needed |
|---|---|---|
| SAP-shaped broker event | Adobe→FWT passes through SAP IDoc shape, so FWT-only facts may be lost | Keep SAP coupling, publish a neutral event, or project directly per source |
| Broker replacement | Taxi's value does not depend on RabbitMQ | Test Azure transport/native connector before changing broker |
| Adobe/SAP identity | POC preserves leading zeroes and requires an Adobe cross-reference; inspected BIP uses SAP `KUNNR` and integer conversion in parts of the Adobe path | Define authoritative cross-reference and leading-zero policy |
| Duplicate FWT effects | Adobe update and later SAP confirmation may represent one business change | Define business key, version and deduplication policy |
| Response semantics | POC waits for broker confirmation; current Adobe Logic App can respond earlier | Choose the external API contract explicitly |
| Bridge ownership | Workarounds add a deployable service that must be operated | Replace with native connector or assign owner, SLO and upgrade policy |

# 7. Recommendation

> **Next step**
>
> Pilot Taxi/Orbital mapping with existing Azure transport. Decide on broker replacement separately.

## Options

| Option | Value | Risk | Position |
|---|---|---|---|
| Keep Azure unchanged | Lowest migration risk | Semantic improvement is lost | Baseline |
| Taxi/Orbital semantics with Azure transport | Tests Taxi reuse while keeping existing connectivity | Requires a supported connector boundary | **Recommended next test** |
| Full Orbital/RabbitMQ replacement | Maximum platform change | Reliability, security, skills and migration case unproven | Not recommended yet |

## Pilot plan

1. **Verify parity.** Create a route/field matrix and automate golden-master comparisons against representative BIP payloads.
2. **Prove connectivity.** Test Azure Service Bus or a supported native AMQP connector on a pinned Orbital version.
3. **Add delivery controls.** Add idempotency, retry/backoff, replay, poison handling, lineage and restart tests.
4. **Shadow then canary.** Run with side effects suppressed, reconcile results, then pilot one reversible route with rollback.

## Before production

| Gate | Minimum evidence |
|---|---|
| Business and identity | Complete field/rule parity, authoritative cross-reference, duplicate policy, domain sign-off |
| Delivery and resilience | At-least-once contract, idempotency, retry/replay, ordering, HA and DR tests |
| Security and operations | TLS, managed secrets, least privilege, PII controls, dashboards, alerts, runbooks and owner |
| Scale and migration | Throughput/latency targets, peak/soak tests, shadow reconciliation, canary and rollback |
| Commercial and support | Three-year TCO, skills/on-call plan, vendor support and accountable team |

<!-- PAGE BREAK -->

# 8. Technical reference

## Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/q/customer-account/from-adobe` | Adobe facts → SAP publish model → bridge |
| `POST /api/q/customer-account/from-sap` | SAP XML + Adobe cross-reference → Adobe write |
| `POST /api/q/customer-account/to-fwt` | IDoc facts → FWT write |

## Runtime inventory

| Item | Count / role |
|---|---|
| Taxi | 11 sources and 3 saved queries |
| Bridge | 1 image in 3 service roles |
| RabbitMQ | 1 event exchange, 1 DLX, 4 main queues, 4 DLQs, 8 bindings |
| Nebula | Adobe PUT and FWT POST capture endpoints |
| Fixtures | Adobe input, SAP input, expected SAP/Adobe/FWT outputs and AMQP metadata |

## Known gaps

- Update-only; no Adobe create flow or SAP `MSGFN=009`.
- No handled skip for `KTOKD != 1`.
- Header-based Adobe cross-reference.
- Partial FWT field coverage.
- No real SAP, Adobe, FWT, Azure Service Bus or reference-data connection.
- No automated retry, replay, idempotency, ordering, HA or DR.
- No production TLS, authentication, secrets, observability or SLO.
- Exact end-to-end fixture comparison is not fully automated.

<!-- CONTINUE PAGE -->

# 9. Source traceability

The detailed implementation and runbook remain in `orbital-poc/README.md`. BIP examples inspected:

- **Adobe ingress:** `la-bip-adobe-customeraccount/LogicApp.json`, `AccountCreation.cs`, `func-bip-AdobeCustomerAccount.cs`.
- **SAP mapping/gateway:** `MapCreateAccountToIdoc.cs`, `func-bip-CustomerAccountSap.cs`, `MapCanonicalCustomerAccount.cs`, both SAP customer-account Logic Apps, `ZBUPA_CBO.XSD`.
- **Adobe/FWT delivery:** the Adobe/FWT customer-account Logic Apps, `ZBUPA_CBOService.cs`, `ZBUPA_CBOServiceFwt.cs`, `AdobeDataService.cs`, `FineWineDataServices.cs`.
- **Shared services:** `AddMessageTypes.ps1`, `ReferenceData.cs`, `LogHelper.cs`.

Repository paths above are relative to `bip/`. This review used source evidence, not live Azure configuration.
