# Customer Account Adobe ↔ SAP (RabbitMQ) Orbital POC

Status: Phase 1 core implemented end to end; acceptance hardening remains; FWT is not started

Last verified: 2026-07-29

Target repository: `orbital-poc`

Reference implementation: `../bip`

## Implementation checkpoint

This is the authoritative continuation point. The design sections below still describe the intended complete POC, while this section records the code and evidence that exist now.

| Area | Implemented and verified | Still required |
|---|---|---|
| Taxi project | Reusable customer-account taxonomy and enums; independent Adobe JSON and SAP XML contracts; HTTP services; `from-adobe` and `from-sap` saved queries; config and Nebula additional sources. Orbital generation 21 loaded with both routes and no schema errors. | Add explicit reverse-route `KTOKD=1` handling and independently assert that `MSGFN`, action metadata, and the enabled update-only behavior agree. |
| RabbitMQ | Durable topic exchange, two directional queues, DLX, two DLQs, positive bindings, `poc` vhost, definitions import, and persistent storage. Topology creation, route isolation, DLQ routing, and restart persistence were exercised. | FWT queue/binding/DLQ are Phase 2. Retry queues and replay tooling are not designed. |
| `rabbit-bridge` | HTTP publisher with mandatory routing and publisher confirms; AMQP consumer with `prefetch=1`, metadata validation, manual acknowledgement, and reject-without-requeue on failure; health endpoint and reconnect state. | Add a durable idempotency store and a deliberate retry policy only after the semantic POC. |
| Adobe → SAP | The Adobe fixture invokes Orbital, Taxi projects the semantic facts, the bridge publishes persistent `application/xml`, and the queued `ZBUPA_CBO` body matches `expected-sap-update.xml` semantically. Routing key and lineage/type/schema metadata were checked. | Automate the live fixture assertion and complete the missing-ID and wrong-origin acceptance cases. |
| SAP → Adobe | A persistent SAP XML event published as `customer-account.sap.updated` is consumed by the bridge, projected by Orbital, sent as a `PUT` to the Nebula Adobe stub, and acknowledged. The captured body matches the expected address and custom-attribute structure, including leading zeroes in `00010001`. | Add the non-individual-account skip policy and live malformed-XML/Adobe-500 DLQ evidence. |
| Verification | `25` bridge tests pass; Python byte-compilation and Ruff pass; both Compose models validate; Orbital, RabbitMQ, Nebula, Postgres, and the bridge are running; bridge consumer health is connected. | Add automated end-to-end tests for every status/preference permutation, optional second address line, title/date behavior, and a stored round-trip comparison report. |
| FWT | Nothing implemented. | Start Phase 2 only after the remaining Phase 1 gate items pass. |

The core update path works in both directions, but the complete Phase 1 exit gate has **not** passed because the business guards and negative/failure acceptance cases above remain.

### Resume the isolated POC stack

The POC uses a separate Compose project and non-conflicting host ports, so it does not replace the unrelated `orbital-*` stack:

```powershell
Set-Location C:\dev\bbnr\orbital
docker compose -p orbital-poc -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.poc.yml up -d --build --wait postgres rabbitmq nebula orbital rabbit-bridge
```

At the end of the 2026-07-29 implementation pass this isolated stack was intentionally left running. Both directional main queues and both DLQs were empty after the fixture messages were inspected or acknowledged.

| Service | Host endpoint |
|---|---|
| Orbital | `http://localhost:19022` |
| Rabbit bridge | `http://localhost:18080/health` |
| RabbitMQ AMQP | `localhost:25672` |
| RabbitMQ management | `http://localhost:25673` |
| Nebula control service | `http://localhost:18099` |
| Postgres | `localhost:35432` |
| Prometheus, when started | `http://localhost:19090` |

The local RabbitMQ demo credentials are `orbital` / `orbital-poc` on vhost `poc`. They are intentionally fixed in the Compose override and definitions file; they are not production credentials.

Useful continuation commands:

```powershell
Set-Location C:\dev\bbnr\orbital
docker compose -p orbital-poc -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.poc.yml ps
docker compose -p orbital-poc -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.poc.yml logs -f orbital rabbit-bridge nebula rabbitmq
```

Run the bridge checks from `C:\dev\bbnr\orbital-poc\rabbit-bridge`:

```powershell
python -m pytest -q
python -m compileall -q app tests
python -m ruff check app tests
```

There is no Taxi CLI installed on this machine. The current Taxi validation evidence is Orbital's clean source reload plus successful execution of both saved-query routes. When stopping the POC, omit `-v` to retain the Rabbit volume:

```powershell
Set-Location C:\dev\bbnr\orbital
docker compose -p orbital-poc -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.poc.yml down
```

### Continue Phase 1 in this order

1. Implement and test a visible `KTOKD != 1` handled-skip outcome on SAP ingress. Decide whether inconsistent `MSGFN=004`/action metadata is rejected by the bridge or by the query, then test it.
2. Turn the manual fixture runs into repeatable assertions, including exact target path/body, AMQP properties, acknowledgement, queue counts, and zero echo deliveries.
3. Complete A2/A3, S2/S3, Q1/Q2, R1, and R3 in the acceptance table. The current consumer has no retry stage: invalid metadata or any downstream non-2xx is immediately rejected without requeue and dead-lettered.
4. Exercise all status/contact-preference mappings, absent optional line 2/mobile/region, title/date behavior, and leading-zero IDs in both projections.
5. Capture a concise automated semantic round-trip report. Then declare the Phase 1 gate passed and begin the FWT contract, queue, consumer, saved query, and stub.

## Decision

Replicate the BIP customer-account integration as two controlled Orbital flows, with RabbitMQ acting as the SAP boundary:

1. Adobe customer JSON → Taxi transformation → SAP `ZBUPA_CBO` XML IDoc → RabbitMQ SAP inbox.
2. SAP `ZBUPA_CBO` XML IDoc published to RabbitMQ → Taxi transformation → Adobe customer JSON.

Start with an update-only, individual-customer slice. Once both directions and the loop guards pass, add FWT as a one-way projection from the SAP-confirmed event.

This is a strong Taxi POC because the system contracts are different, while the underlying business facts—customer number, name, email, address, status, preferences, and balances—can share semantic types. It also demonstrates JSON/XML conversion, enum/reference-data translation, and asynchronous topic/subscription routing without requiring a real SAP or Azure Service Bus environment.

The disposable `src/users.taxi` example has been removed and replaced by the customer-account project described here.

## Outcome

The completed POC will prove that Orbital can:

- accept an Adobe-shaped customer update and publish the corresponding SAP IDoc to a RabbitMQ queue representing the SAP inbox;
- consume a SAP customer IDoc from a RabbitMQ subscription and write the corresponding Adobe request;
- reuse the same Taxi semantic types in independent Adobe, SAP, and later FWT models;
- preserve source-specific wire contracts rather than introducing one shared physical model;
- translate action and status codes explicitly;
- prevent a message from being routed back to its origin through positive RabbitMQ bindings and metadata validation;
- prove RabbitMQ fan-out by adding FWT as a second SAP-origin subscription without changing the Adobe consumer;
- add FWT later without remodelling the Adobe and SAP contracts.

It will prove semantic round-trip equivalence for the selected fields. It will not claim byte-for-byte round-trip equivalence because each system has fields and representations that the other does not preserve.

## Scope

### Phase 1: Adobe ↔ SAP core

Included:

- update only: Adobe update ↔ SAP `MSGFN=004`;
- individual customer accounts only: SAP `KTOKD=1`;
- synthetic fixtures with no personal or bank data;
- core identity, name, contact, address, date-of-birth, status, and contact-preference fields;
- Adobe JSON and SAP XML wire formats;
- a local RabbitMQ topic exchange, durable subscription queues, and dead-letter queues;
- a thin HTTP/AMQP bridge with no business transformations;
- an Adobe HTTP stub with captured requests;
- a message ID, origin, and action on every POC invocation;
- explicit route guards and deterministic assertions.

Deferred from the first working slice:

- account creation (`POST` / SAP `MSGFN=009`);
- real Adobe, SAP, Azure Service Bus, or Azure Table connections;
- automated retry queues, production ordering guarantees, durable idempotency, and production authentication;
- the complete financial, bank, partner, and custom-attribute model;
- Creatio and prospective-customer routes;
- FWT writes.

### Phase 2: FWT core

After the Phase 1 exit gate passes, add one independent RabbitMQ subscription and outbound flow:

```text
SAP-confirmed customer change
  → poc.customer-account.sap-to-fwt queue
  → Orbital Taxi projection
  → FWT POST /customer-accounts
```

FWT is not a return leg. BIP contains a FWT customer-account off-ramp but no corresponding FWT customer-account on-ramp.

For the POC, FWT should receive only the SAP-confirmed event by binding its queue to `customer-account.sap.*`. This is intentionally narrower than the current BIP subscription, which accepts both Adobe- and SAP-origin messages. Waiting for SAP confirmation avoids a premature or duplicate FWT `POST`, particularly when SAP has not yet assigned `KUNNR` during account creation.

In this POC, “SAP-confirmed” means a separate IDoc fixture explicitly published with routing key `customer-account.sap.updated`, a new message ID, and correlation/causation metadata linking it to the Adobe-origin event. Arrival in the fake SAP inbox alone is not confirmation.

## Production flow being replicated

### Adobe → SAP

```text
Adobe HTTP customer payload
  → la-bip-adobe-customeraccount
  → adobeCustomerAccount function
  → customeraccount topic (SystemOrigin=adobe)
  → customeraccountsapSubscription
  → customerAccountSap function
  → SAP connector POST /SendIDoc/v2
```

The Adobe on-ramp accepts the Adobe contract, derives create/update from the original HTTP verb, maps it into an IDoc-shaped message, and publishes it with `SystemOrigin=adobe`. The SAP subscription excludes SAP-origin messages. The off-ramp serializes the message as `ZBUPA_CBO` XML and invokes SAP.

The BIP path currently performs Adobe JSON → XML → rootless JSON → XML. This POC models Adobe JSON and SAP XML directly and keeps the business mapping in Taxi. One local runtime limitation affects only outbound serialization: Orbital 0.38 can read the SAP `@Xml` model, but its HTTP request factory cannot serialize that model. Taxi therefore sends an equivalent structured JSON envelope to the bridge, whose narrow serializer emits `ZBUPA_CBO` XML without changing business values.

### SAP → Adobe

```text
SAP ZBUPA_CBO IDoc
  → SAP gateway
  → ZBUPA_CBO queue
  → la-bip-sap-customeraccount
  → customeraccount topic (SystemOrigin=sap)
  → customeraccountadobeSubscription
  → customerAccountAdobe function
  → Adobe POST or PUT /rest/V1/customers
```

SAP XML is converted to an IDoc-shaped JSON message and published with `SystemOrigin=sap`. The Adobe subscription excludes Adobe-origin messages. Only `KTOKD=1` is sent to Adobe. `MSGFN=004` selects `PUT`; every other message function currently selects `POST`.

### FWT off-ramp

```text
customeraccount topic
  → customeraccountfwtSubscription
  → customerAccountFwt function
  → FWT POST /customer-accounts
```

The current subscription filter excludes `fwt` and `adobeprospect`, but accepts both `adobe` and `sap`. The POC will initially use the safer SAP-confirmed-only policy and record this as an intentional difference.

## POC transport substitution

The production BIP flow above remains the behavioral reference. In the POC, RabbitMQ replaces both the real SAP endpoint and the Azure messaging plumbing around it:

| Production boundary | POC replacement |
|---|---|
| Azure Service Bus `customeraccount` topic | RabbitMQ topic exchange `poc.customer-account.events` |
| Service Bus topic subscription | A dedicated durable RabbitMQ queue plus binding |
| SAP `/SendIDoc/v2` connector | Queue `poc.customer-account.adobe-to-sap` |
| SAP gateway/on-ramp | Test publisher plus queue `poc.customer-account.sap-to-adobe` |
| Logic App transport code | Thin `rabbit-bridge` sidecar |

RabbitMQ publishers publish to exchanges and subscribers consume from queues. Each destination therefore gets its own queue; sharing one queue between Adobe and FWT would load-balance messages instead of providing each destination a copy.

## POC architecture

```mermaid
flowchart LR
    AdobeIn[Adobe fixture<br/>JSON update] --> AdobeQuery[Saved query<br/>from-adobe]
    AdobeQuery --> Semantic[Reusable Taxi<br/>semantic types]
    Semantic --> SapModel[SAP-owned<br/>IDoc XML model]
    SapModel --> PublishBridge[rabbit-bridge<br/>HTTP publish endpoint]
    PublishBridge --> Exchange[(RabbitMQ topic exchange<br/>poc.customer-account.events)]
    Exchange -->|customer-account.adobe.*| SapInbox[[SAP inbox queue<br/>adobe-to-sap]]

    SapPublisher[SAP XML fixture<br/>test publisher] --> Exchange
    Exchange -->|customer-account.sap.*| AdobeQueue[[Subscription queue<br/>sap-to-adobe]]
    AdobeQueue --> ConsumeBridge[rabbit-bridge<br/>AMQP consumer]
    ConsumeBridge --> SapQuery[Saved query<br/>from-sap]
    SapQuery --> Semantic
    Semantic --> AdobeModel[Adobe-owned<br/>customer model]
    AdobeModel --> AdobeStub[Adobe HTTP stub<br/>captures JSON]

    Exchange -. customer-account.sap.*<br/>phase 2 .-> FwtQueue[[Subscription queue<br/>sap-to-fwt]]
    FwtQueue -. rabbit-bridge .-> FwtQuery[Saved query<br/>sap-to-fwt]
    FwtQuery -. Taxi projection .-> FwtStub[FWT HTTP stub<br/>POST /customer-accounts]
```

The two directions remain separate. A message placed in the SAP inbox is not automatically echoed as a SAP-origin event. The round-trip test inspects the outbound XML, then publishes a paired SAP fixture with a new message ID and the same correlation ID. This makes routing observable and prevents an accidental infinite cycle.

## Taxi modelling strategy

Taxi types are the reusable vocabulary; models remain owned by the system whose wire contract they describe. Do not build one giant enterprise customer model and make all systems depend on its structure.

### Core reusable types

| Area | Taxi types | Notes |
|---|---|---|
| Lineage | `CustomerAccountMessageId`, `CustomerAccountCorrelationId`, `CustomerAccountCausationId`, `CustomerAccountOrigin`, `CustomerAccountAction` | Required transport facts; they are not customer payload fields. |
| Identity | `AdobeCustomerId`, `SapCustomerNumber` | Distinct concepts. Both inherit `String`; neither is an alias of the other. |
| Person | `CustomerFirstName`, `CustomerLastName`, `CustomerTitle`, `CustomerDateOfBirth` | Title display text and SAP title code remain separate representations. |
| Contact | `CustomerEmailAddress`, `TelephoneNumber`, `MobileNumber` | Shared meanings across all three contracts. |
| Address | `AddressLine1`, `AddressLine2`, `Town`, `Postcode`, `CountryCode`, `RegionCode` | Do not give Adobe numeric `region_id` the `RegionCode` type. |
| Account | `CustomerAccountStatus`, `CustomerContactPreference`, `SalesDistrictCode` | Wire codes are mapped using enums or explicit lookup operations. |
| Money, later | `CustomerBalanceAmount`, `CreditLimitAmount`, `MonthlyPaymentAmount`, `CurrencyCode` | Add after the core round trip. |
| Bank, later | `BankAccountNumber`, `AccountHolderName`, `Iban`, `Bic`, `BankCountryCode`, `BankValidFrom`, `BankValidTo` | Add as one parity slice, not field by field. |

`SapCustomerNumber` must remain a string. The existing SAP → Adobe mapper parses it as an integer for Adobe's root `id`, which can remove leading zeroes. The semantic type must preserve the original value even if a particular target representation does not.

### System-owned models

Define independent models composed from the shared types:

- `adobe.AdobeCustomerAccount`
- `adobe.AdobeAddress`
- `adobe.AdobeCustomAttribute`
- `adobe.AdobeCustomerWriteRequest` for `{ "customer": ... }`
- `sap.ZbupaCustomerAccountIdoc`
- `sap.ZbupaCustomerCoreSegment`
- `sap.ZbupaCustomerSecondarySegment`
- `fwt.FwtCustomerAccount` in Phase 2

Keep routing metadata as typed saved-query parameters, so each request body remains the real system wire format:

```text
Adobe ingress
  X-Message-Id        : CustomerAccountMessageId
  X-Correlation-Id    : CustomerAccountCorrelationId
  X-System-Origin     : CustomerAccountOrigin
  X-Account-Action    : CustomerAccountAction
  request body        : adobe.AdobeCustomerAccount JSON

SAP ingress, called by rabbit-bridge
  X-Message-Id        : CustomerAccountMessageId
  X-Correlation-Id    : CustomerAccountCorrelationId
  X-Causation-Id      : CustomerAccountCausationId?
  X-System-Origin     : CustomerAccountOrigin
  X-Adobe-Customer-Id : AdobeCustomerId
  request body        : sap.ZbupaCustomerAccountIdoc XML
```

`X-Adobe-Customer-Id` is an explicit Phase 1 substitute for the unresolved production identity cross-reference. It prevents the taxonomy from pretending that `KUNNR` and Adobe's root `id` are the same concept. The paired synthetic fixture may give them the same text while retaining their distinct Taxi types. SAP action is derived from `MSGFN`; the Adobe ingress receives it explicitly because BIP derives it from the original HTTP verb.

### Semantic enums and lookups

Represent business meanings independently from source codes:

| Meaning | Adobe representation | SAP representation |
|---|---|---|
| Update | ingress action `UPDATE` | `MSGFN=004` |
| Create, later | ingress action `CREATE` | `MSGFN=009` in the current mapper |
| Active | `ACTIVE` | `AC` |
| Blocked | `BLOCKED` | `BL` |
| Deactivated | `DEACTIVE` | `DC` |
| Declined | `DECLINED` | `DE` |
| In process | `INPROCESS` | `IN` |
| On hold | `ONHOLD` | `OH` |
| Email only | email=true, post=false | `EML` |
| Post only | email=false, post=true | `PST` |
| Email and post | email=true, post=true | `PEM` |
| Neither | email=false, post=false | `NON` |

Use Taxi enum synonyms where the mapping is closed and genuinely bidirectional. Use an explicit lookup source for reference data such as title and sales district, where BIP currently reads Azure Table `refData`. The first slice can use a small deterministic local lookup fixture.

Do not reproduce these BIP asymmetries silently:

- SAP → Adobe emits contact flags as the strings `"true"`/`"false"`, while Adobe → SAP currently checks `"1"`/`"0"`. Model booleans semantically and translate each wire form.
- SAP → Adobe exposes raw `ANRED` in one Adobe custom attribute, while Adobe → SAP expects a display title for its lookup. Keep `SapTitleCode` and `CustomerTitle` separate.
- SAP `REGIO` is a region code; Adobe's `region_id` is numeric. They are not the same type.
- Adobe root `id` and custom attribute `sap_unique_id` are not interchangeable identities.

## Phase 1 field contract

| Semantic fact | Adobe source/target | SAP source/target | First-slice rule |
|---|---|---|---|
| Adobe identity | root `id` | none | Keep as `AdobeCustomerId`; required for Adobe update target. |
| SAP identity | custom `sap_unique_id` | `KUNNR` | Keep as `SapCustomerNumber`; required for SAP update. |
| Action | ingress `UPDATE` | `MSGFN=004` | Update only. Reject other actions in Phase 1. |
| Customer type | Adobe customer | `KTOKD` | Write and accept only `1` (individual). |
| First name | `firstname` | `NAME1` | Direct semantic mapping. |
| Last name | `lastname` | `NAME2` | Direct semantic mapping. |
| Email | `email` | `KNURL` | Direct semantic mapping. |
| Date of birth | `dob` | `RGDATE` | Define and test one normalized date representation. |
| Street line 1 | default billing `street[0]` | `STRAS` | Require a default billing address in the fixture. |
| Street line 2 | default billing `street[1]` | `PSOO4` | Optional. |
| Town | address `city` | `ORT01` | Direct semantic mapping. |
| Postcode | address `postcode` | `PSTLZ` | Direct semantic mapping. |
| Country | address `country_id` | `LAND1` | Country code, not a country description. |
| Region | address `region.region_code` | `REGIO` | Region code only; do not use `region_id`. |
| Telephone | address `telephone` | `TELF1` | Direct semantic mapping. |
| Mobile | address alternate telephone | `MOB_NUMBER` | Confirm the chosen Adobe field in the fixture. |
| Status | custom `cellar_plan_status` | `KATR5` | Use the explicit status enum mapping. |
| Contact preference | two Adobe booleans | `KATR10` | Normalize to one semantic preference enum. |

The first fixture may deliberately use equal textual Adobe and SAP IDs to exercise the current BIP update path, but the Taxi types must remain distinct. Before using non-synthetic data, select an authoritative identity cross-reference. Do not solve this by aliasing the two ID types.

## RabbitMQ topology

RabbitMQ uses an exchange plus bound queues rather than Azure-style topic/subscription objects. Use one durable topic exchange and one durable queue per directional integration route:

| Object | Binding or route | Phase | Purpose |
|---|---|---|---|
| Exchange `poc.customer-account.events` | Type `topic` | 1 | The customer-account event bus. |
| Queue `poc.customer-account.adobe-to-sap` | `customer-account.adobe.*` | 1 | Fake SAP inbox; contains mapped `ZBUPA_CBO` XML. |
| Queue `poc.customer-account.sap-to-adobe` | `customer-account.sap.*` | 1 | Subscription consumed by `rabbit-bridge` and forwarded to the SAP → Adobe query. |
| Queue `poc.customer-account.sap-to-fwt` | `customer-account.sap.*` | 2 | Independent FWT subscription consumed by `rabbit-bridge`. |
| Exchange `poc.customer-account.dlx` | Type `topic` | 1 | Dead-letter exchange for failed route deliveries. |
| One `.dlq` per main queue | Explicit dead-letter routing key | 1/2 | Failure inspection and manual replay. |

Use routing keys that state the source and action:

```text
customer-account.adobe.updated
customer-account.adobe.created      # later
customer-account.sap.updated
customer-account.sap.created        # later
```

Do not bind a consumer queue to `customer-account.#`. Explicit positive bindings are the first loop-prevention control and make the allowed directions reviewable.

### Rabbit message contract

The Rabbit body is the native SAP `ZBUPA_CBO` XML contract with `content_type=application/xml`. Transport facts are AMQP properties or headers, not XML elements:

| AMQP property/header | Meaning |
|---|---|
| `message_id` | Stable UUID for this event and its delivery retries. |
| `correlation_id` | Stable across the paired Adobe → SAP → Adobe POC flow. |
| `type` | Versioned event name, initially `customer-account.updated.v1`. |
| `content_type` | `application/xml`. |
| `delivery_mode` | `2` so an unconsumed message survives a broker restart with durable topology. |
| `x-origin` | `adobe`, `sap`, or later `fwt`. |
| `x-action` | `UPDATE`, or later `CREATE`. |
| `x-schema` | Initially `sap.zbupa-cbo.v1`. |
| `x-causation-id` | The inbound message ID that caused a deliberately new event. |
| `x-adobe-customer-id` | POC-only reverse-route identity; carried as metadata and never inserted into the SAP IDoc. |
| `x-integration-write` | Marks a target write that must not be re-emitted as a new source event. |

The routing key is authoritative for routing. The bridge must validate that `x-origin` and `x-action` agree with it before calling Orbital.

## Orbital endpoints, bridge, and HTTP stubs

Expose these saved-query ingress operations:

| Operation | POC endpoint | Caller and input | Side effect |
|---|---|---|---|
| Adobe → SAP | `POST /api/q/customer-account/from-adobe` | Test client; Adobe JSON body plus typed lineage/action headers | Projects to SAP XML and calls the bridge publish operation. |
| SAP → Adobe | `POST /api/q/customer-account/from-sap` | `rabbit-bridge`; raw SAP XML plus AMQP metadata mapped to typed headers | Projects to Adobe JSON and calls the Adobe stub. |
| SAP → FWT | `POST /api/q/customer-account/sap-to-fwt` | `rabbit-bridge`, Phase 2; raw SAP XML plus typed headers | Projects to FWT JSON and calls the FWT stub. |

Using `POST` for POC ingress keeps transport separate from the business action. These are orchestration endpoints, not replicas of Adobe's or SAP's public APIs.

Define these downstream HTTP write operations in Taxi:

- Rabbit bridge publish: accepts `sap.ZbupaCustomerAccountPublishRequest` JSON plus typed HTTP lineage headers; the bridge structurally serializes the object to `ZBUPA_CBO` XML, maps the headers to AMQP metadata, and publishes it with routing key `customer-account.adobe.updated`. The endpoint also accepts already-serialized XML for transport smoke tests.
- Adobe stub: `PUT /rest/V1/customers/{adobeCustomerId}` with an `adobe.AdobeCustomerWriteRequest` JSON body.
- FWT stub, Phase 2: `POST /customer-accounts` with an unwrapped `fwt.FwtCustomerAccount` JSON body.

The thin `rabbit-bridge` is required because the Orbital image used by this workspace does not expose a documented RabbitMQ/AMQP Taxi connector. It has two transport-only responsibilities:

1. Expose an HTTP endpoint that accepts Orbital's structured SAP JSON envelope (or raw XML), performs only SAP XML wire serialization when needed, publishes it to `poc.customer-account.events` over AMQP, and returns success only after a publisher confirm and confirmation that the message was routed.
2. Consume the SAP-origin queues and post each raw XML body to the corresponding Orbital saved query.

The bridge does not derive or map customer values. It acknowledges a Rabbit delivery only after Orbital returns success. Invalid metadata, malformed input that Orbital rejects, or any downstream non-2xx is rejected without requeue so RabbitMQ dead-letters it immediately. The current consumer uses `prefetch=1`; it has no retry stage. Ordering and retry queues are later hardening work.

Use Orbital HTTP service URL overrides in `orbital/config/services.conf`, so Taxi service contracts refer to stable service names such as `rabbit-bridge` and `adobe-stub` rather than local ports. Nebula remains suitable for the Adobe and FWT HTTP stubs; it is not the RabbitMQ transport.

RabbitMQ's management HTTP publish and queue `get` endpoints are not the integration path. They are useful for manual fixture publishing and inspection, but RabbitMQ documents them as inefficient or development/troubleshooting operations. The bridge uses AMQP for continuous transport.

## Docker Compose and workspace setup

The runtime setup is implemented in the sibling `../orbital` support folder:

- `docker-compose.yml` remains the generated base stack.
- `docker-compose.override.yml` mounts this POC read-only, adds RabbitMQ 4.1.8, persists broker data, builds the bridge, and supplies its broker/route/Orbital settings.
- `docker-compose.poc.yml` overrides host ports for the isolated `orbital-poc` project.
- `workspace/workspace.conf` loads `/opt/service/projects/orbital-poc` with polling.
- `rabbitmq/rabbitmq.conf` and `rabbitmq/definitions.json` import the vhost, user, permissions, exchanges, queues, bindings, and dead-letter topology.

`../orbital/rabbitmq/rabbitmq.conf` imports the topology deterministically:

```properties
definitions.import_backend = local_filesystem
definitions.local.path = /etc/rabbitmq/definitions.json
definitions.skip_if_unchanged = true
```

`../orbital/rabbitmq/definitions.json` declares the `poc` topology and includes the hash for the fixed local demo user. Definitions import owns that user, so the Compose values intentionally match `orbital` / `orbital-poc`; changing only environment variables will not replace the imported credentials.

The base Compose configuration points Orbital at `/opt/service/workspace/workspace.conf`. The implemented file contains:

```hocon
file {
  projects = [{
    isEditable = false
    path = "/opt/service/projects/orbital-poc"
  }]
  changeDetectionMethod = POLL
  incrementVersionOnChange = false
  pollFrequency = PT3S
  recompilationFrequencyMillis = PT3S
}
```

The base stack owns the `./workspace` mount; the override adds only the read-only POC project mount. The earlier runtime-collision decision is resolved: always combine `docker-compose.poc.yml` with project name `orbital-poc` as shown in the checkpoint commands. This keeps the unrelated `orbital-*` stack untouched.

## Routing, acknowledgement, and loop prevention

Apply these route policies:

| Published route | Bound POC queue(s) | Must not receive it |
|---|---|---|
| `customer-account.adobe.*` | `poc.customer-account.adobe-to-sap` | Adobe and FWT |
| `customer-account.sap.*` | `poc.customer-account.sap-to-adobe`; later `poc.customer-account.sap-to-fwt` | SAP |
| `customer-account.fwt.*`, if ever enabled | Only explicitly approved directional queues | FWT |

Current safeguards and remaining work are:

1. **Implemented:** directional positive bindings prevent routing an event to its source queue.
2. **Implemented:** the bridge rejects inconsistent routing-key/header combinations.
3. **Partially implemented:** `x-integration-write=true` is carried to the Adobe write and the local stub never emits events, but no generic adapter enforcement exists yet.
4. **Not implemented:** correlation and causation IDs are preserved, but there is no hop-count guard or durable idempotency store.

Origin filtering alone does not prevent Adobe → SAP → Adobe → SAP ping-pong if every applied write is re-emitted. In Phase 1 the SAP inbox has no automatic echo consumer: the return event is a separate, explicit SAP fixture.

The POC does not claim exactly-once delivery. It currently proves one target effect for one valid delivery and acknowledges only after success. There are no retries yet. A future retry must preserve the same `message_id`, and production idempotency needs a durable store keyed by `route + message_id`; deduplication cannot be global because the same SAP event will legitimately feed both Adobe and FWT.

## Current and planned repository layout

```text
orbital-poc/
├── README.md
├── taxi.conf
├── src/
│   ├── taxonomy/
│   │   ├── customer-account-types.taxi
│   │   └── customer-account-enums.taxi
│   ├── contracts/
│   │   ├── adobe-customer-account.taxi
│   │   ├── sap-customer-account.taxi
│   │   └── fwt-customer-account.taxi          # Phase 2, not present
│   ├── services/
│   │   ├── adobe-customer-service.taxi
│   │   ├── rabbit-bridge-service.taxi
│   │   └── fwt-customer-service.taxi          # Phase 2, not present
│   └── queries/
│       ├── adobe-to-sap.taxi
│       ├── sap-to-adobe.taxi
│       └── sap-to-fwt.taxi                    # Phase 2, not present
├── rabbit-bridge/
│   ├── app/                                   # publisher, consumer, metadata, XML serializer
│   ├── tests/                                 # 25 unit/component tests
│   └── Dockerfile
├── orbital/                                     # Taxi additionalSources, not the sibling stack
│   ├── config/services.conf
│   └── nebula/customer-account.nebula.kts
└── test-data/
    ├── adobe-update.json
    ├── expected-sap-update.xml
    ├── sap-update.xml
    ├── expected-adobe-update.json
    ├── rabbit-message-metadata.json
    └── expected-fwt-update.json               # Phase 2, not present

../orbital/
├── docker-compose.yml                         # Generated; do not customize
├── docker-compose.override.yml                # RabbitMQ, bridge, POC mount
├── docker-compose.poc.yml                     # Isolated host-port overrides
├── rabbitmq/
│   ├── rabbitmq.conf
│   └── definitions.json
└── workspace/workspace.conf
```

`taxi.conf` already includes `@orbital/config` and `@orbital/nebula`. Nebula remains local/test-only. Entries marked Phase 2 are the planned FWT additions; all other listed paths are implemented.

## Implementation sequence

### 1. Reset and build the taxonomy

Status: **complete for the Phase 1 field slice**.

- Delete `src/users.taxi`.
- Add the core semantic types and strict business enums.
- Add distinct Adobe and SAP IDs.
- Add typed saved-query inputs for message, correlation, causation, origin, action, and the temporary Adobe identity parameter.
- Add synthetic paired fixtures with stable values and no PII.
- Validate through Orbital's source loader until the project reloads with no schema errors; install a Taxi CLI later if a standalone build is required.

Exit: the taxonomy builds, and no contract field that participates in the core mapping is typed as a bare `String`, `Int`, or `Boolean` when a business meaning is known.

### 2. Add RabbitMQ and the transport bridge

Status: **complete for Phase 1**.

- Add RabbitMQ to `../orbital/docker-compose.override.yml` on `nebula_network`.
- Mount this Taxi project into the Orbital container and add it to `workspace.conf`.
- Declare the exchange, directional queues, bindings, DLX, and DLQs in `definitions.json`.
- Implement the bridge HTTP publish endpoint and the SAP-origin AMQP consumer.
- Preserve AMQP metadata when forwarding to Orbital.
- Acknowledge after Orbital success; reject without requeue on terminal failure.
- Validate the effective Compose model with `docker compose config` before starting it.

Exit evidence: RabbitMQ is healthy, its isolated management UI is reachable at `http://localhost:25673`, all Phase 1 topology exists, Orbital loads this Taxi project, and raw SAP XML traverses the consumer without customer transformation inside the bridge.

### 3. Implement Adobe → SAP update

Status: **core flow complete and live-verified**.

- Describe the required Adobe JSON subset.
- Describe the required `ZBUPA_CBO` XML subset.
- Implement `UPDATE → MSGFN=004` and `KTOKD=1`.
- Map the Phase 1 fields and the local title/status/contact-preference lookups.
- Add the bridge publish HTTP write operation using the SAP publish model. The current Orbital 0.38 workaround sends structured JSON and lets the transport bridge perform XML wire serialization.
- Publish the `from-adobe` saved query.

Exit: the Adobe fixture produces one message in `poc.customer-account.adobe-to-sap`; its body is the expected SAP XML and its routing key, content type, message ID, correlation ID, origin, action, and schema metadata are correct.

### 4. Implement SAP → Adobe update

Status: **core flow complete and live-verified; the `KTOKD != 1` handled-skip guard remains**.

- Parse the SAP XML model directly with Orbital's XML format.
- Reject or visibly skip `KTOKD != 1`.
- Implement `MSGFN=004 → UPDATE`.
- Receive `AdobeCustomerId` through the documented POC-only header; replace it with the authoritative cross-reference before production connectivity.
- Map the Phase 1 fields and wrap them as `{ "customer": ... }`.
- Add the Adobe `PUT` write operation and capture stub.
- Publish the `from-sap` saved query.
- Configure the bridge to consume `poc.customer-account.sap-to-adobe` and forward the XML plus metadata to that query.

Exit: publishing the SAP XML fixture with routing key `customer-account.sap.updated` results in one captured Adobe `PUT` at the expected path and the Rabbit delivery is acknowledged.

### 5. Prove the controlled round trip

Status: **partial**. The valid forward and reverse fixtures, topology isolation, acknowledgement path, leading-zero ID, and core `ACTIVE`/email-and-post mapping are proven. The remaining bullets and Phase 1 gate items below are not all complete.

- Compare the selected semantic facts after Adobe → SAP → Adobe fixture projection.
- Assert the Adobe and SAP ID types never substitute for one another implicitly.
- Inspect the SAP-inbox message, then publish a separate paired SAP event with a new message ID, the same correlation ID, and the first message as its causation ID.
- Assert topic bindings do not deliver an event to its source-system queue.
- Assert inconsistent routing keys and `x-origin` headers are rejected.
- Test status, contact preference, title, date, optional second street line, and leading-zero SAP ID cases.
- Force malformed XML and an Adobe HTTP failure and verify the failed delivery reaches the route DLQ with its metadata intact.
- Record transformation/query traces from Orbital as POC evidence.

Phase 1 exit gate:

- [x] Orbital compiles and loads the Taxi project without schema errors.
- [x] RabbitMQ, the bridge, Orbital, Nebula, and the Adobe stub are healthy.
- [x] Both ingress routes succeed for valid update fixtures.
- [x] Adobe → SAP creates exactly one persistent message in the SAP inbox queue for one invocation.
- [x] SAP → Adobe creates exactly one Adobe target call and acknowledges the queue delivery.
- [x] Directional bindings make zero echo deliveries.
- [ ] `KTOKD != 1` is visibly skipped.
- [ ] Malformed XML and a live Adobe `500` are observable in the expected DLQ with metadata intact. Basic invalid-metadata DLQ routing is already proven.
- [ ] All Phase 1 fields and enum permutations are recorded as semantically equivalent in an automated paired round-trip report. The core fixture values are already proven in each direction.
- [x] No test depends on production credentials or personal data.

### 6. Add FWT after the gate passes

Status: **not started**.

- Add the FWT-owned contract using the existing core semantic types.
- Add `POST /customer-accounts` to the FWT stub.
- Add `poc.customer-account.sap-to-fwt` with binding `customer-account.sap.*` and its own DLQ.
- Configure a separate bridge consumer to forward that queue to the `sap-to-fwt` saved query.
- Start with identity, action, name, email, date of birth, address, telephone, and mobile.
- Assert one FWT call with `SapCustomerNumber` as the unmodified string ID.
- Add reference-data descriptions, money, bank accounts, flags, and preferences in later parity slices.

Phase 2 exit gate:

- Existing Adobe ↔ SAP tests remain unchanged and green.
- One SAP-confirmed event is copied to the independent Adobe and FWT queues and creates exactly one call to each target.
- Adobe- and FWT-origin events create no FWT queue delivery.
- FWT's `actionCode` represents update while the HTTP method remains `POST`.
- Missing dates do not silently become the current time.
- A balance currency never falls back to a country code.

### 7. Harden only after the semantic POC

Status: **not started**, except that publisher confirms and basic health/logging already exist in the bridge.

- Add create behavior and decide how the SAP-assigned customer number is correlated back to Adobe.
- Replace local reference fixtures with an authoritative source.
- Add the remaining money, bank, partner, and custom-attribute fields.
- Add a durable idempotency store keyed by `route + message_id`.
- Design retry queues, ordering rules, replay tooling, publisher confirms, and observability.
- Evaluate replacing the bridge if a supported RabbitMQ connector is supplied for the deployed Orbital edition.
- Re-evaluate whether FWT should accept both Adobe- and SAP-origin events.

## Acceptance scenarios

| ID | Scenario | Expected result | Status and evidence at 2026-07-29 |
|---|---|---|---|
| T1 | Start from an empty RabbitMQ data volume | Definitions import creates the durable exchange, queues, bindings, DLX, and DLQs. | **Passed.** Exercised with an isolated validation broker. |
| T2 | Restart RabbitMQ after publishing a persistent test message | Durable topology and the unconsumed persistent message remain available. | **Passed.** Persistent message and topology survived restart. |
| T3 | Publish Adobe-, SAP-, and unapproved-origin routes | Each positive binding receives only its approved origin; an unbound route reaches no main queue. | **Passed.** Directional and unapproved routing were inspected on the validation broker. |
| A1 | Valid Adobe individual update | One SAP-inbox message; XML has `MSGFN=004`, `KTOKD=1`, and expected core fields. | **Passed.** Live body matched `expected-sap-update.xml` semantically; persistent AMQP properties and headers matched the fixture contract. |
| A2 | Adobe request missing `sap_unique_id` | Validation failure; no Rabbit message is published. | **Pending live acceptance test.** |
| A3 | Adobe request marked `origin=sap` | `INVALID_ROUTE_METADATA`; no Rabbit message is published. | **Partial.** Bridge metadata behavior has unit coverage; add a live saved-query assertion. |
| S1 | Valid SAP individual update published as `customer-account.sap.updated` | One Adobe `PUT`; expected path/body; Rabbit delivery acknowledged. | **Passed.** Rabbit recorded one publish and one acknowledgement; Nebula captured the expected path and full nested JSON body. |
| S2 | SAP `KTOKD` is not `1` | Visible skip; no Adobe call; Rabbit delivery acknowledged as handled. | **Pending implementation and test.** Current reverse query does not guard this field. |
| S3 | SAP route and `x-origin` disagree | `INVALID_ROUTE_METADATA`; no Orbital target call; delivery dead-lettered. | **Passed at bridge/topology level.** Unit coverage plus live validation-broker DLQ check; preserve this in an automated stack test. |
| Q1 | Malformed SAP XML | No target call; delivery appears in `sap-to-adobe.dlq` with IDs intact. | **Pending live acceptance test.** |
| Q2 | Adobe target returns HTTP 500 | Delivery is rejected without requeue and reaches `sap-to-adobe.dlq`. | **Partial.** Consumer non-2xx rejection has unit coverage; live Adobe-500/DLQ evidence remains. |
| R1 | Paired Adobe/SAP update fixtures | Selected semantic fields compare equal after both projections. | **Partial.** Both valid projections match their expected fixtures; add one automated paired semantic report with lineage assertions. |
| R2 | SAP number has leading zeroes | Original `SapCustomerNumber` is preserved. | **Passed** for `00010001` in both live projections. |
| R3 | Each status and preference value | Expected code/boolean mapping in both directions. | **Partial.** `ACTIVE` and email-and-post are live-proven; all remaining permutations are pending. |
| F1 | SAP-confirmed update after Phase 2 | One message in each SAP-origin subscription; exactly one Adobe call and one FWT `POST`. | **Not started.** |
| F2 | Adobe-origin update after Phase 2 | No FWT queue delivery under the POC routing policy. | **Not started.** |

## Decisions needed before production connectivity

1. Identity cross-reference: what authoritative source maps `SapCustomerNumber` to `AdobeCustomerId`? The current reverse BIP path uses `KUNNR` in the Adobe URL, while the forward path obtains `KUNNR` from Adobe's `sap_unique_id` custom attribute.
2. Create correlation: how is a SAP-assigned `KUNNR` returned and associated with the Adobe account after `MSGFN=009`?
3. Reference data: should title, sales district, customer group, region, and other code translations remain in Azure Table storage, move into taxonomy enums, or be exposed as a lookup service?
4. FWT routing: should production preserve the current broad subscription or adopt the SAP-confirmed-only policy?
5. Bridge ownership: which runtime and team own the HTTP/AMQP adapter, and is a supported native Orbital RabbitMQ connector available in the target edition?
6. Delivery guarantees: where should `route + message_id` idempotency be persisted, and which failures are retried before dead-lettering?
7. Runtime placement: which deployed environment should host Orbital, RabbitMQ, and the bridge? Local replacement is no longer an open question; the POC runs as isolated project `orbital-poc` on non-conflicting ports.

## Known BIP behavior to preserve or correct deliberately

- Adobe create maps to SAP `MSGFN=009`; update maps to `004`.
- Adobe supports only individual accounts in this path; SAP → Adobe skips other `KTOKD` values.
- Adobe → SAP selects the first default billing address.
- Adobe `created_at` is parsed as `yyyy-MM-dd HH:mm:ss` before populating SAP date/time fields.
- Status and contact preferences use explicit code tables.
- BIP's contact flag representations are asymmetric; the POC normalizes them.
- Some fields are one-way only. In particular, credit limit, sales block, and account-manager employee ID are mapped SAP → Adobe, while currency is read Adobe → SAP but is not mapped back.
- CPA consent, default card, and monthly payment are present in local mapping code but are omitted by a later canonical-to-IDoc pass-through; they are not Phase 1 proven fields.
- FWT always uses `POST`; create/update intent is carried in `actionCode`.
- Existing FWT date fallbacks and country-as-currency fallback are not to be copied silently.

## Intentional POC transport differences

- Production BIP uses Azure Service Bus and a SAP managed connector; the POC uses RabbitMQ and raw SAP XML.
- RabbitMQ positive topic bindings replace Service Bus SQL expressions with negative `SystemOrigin` filters.
- A thin bridge adapts HTTP to AMQP because the current local Orbital stack has no configured supported RabbitMQ connector; it is not a business-mapping service.
- The fake SAP inbox does not automatically emit a SAP response. The paired return fixture is published explicitly.
- FWT initially binds only to SAP-origin events rather than reproducing BIP's broader Adobe-and-SAP subscription.
- Basic DLQs are in scope, but automated retries, replay tooling, high availability, and production idempotency are not.

## BIP evidence

| Concern | Authoritative source |
|---|---|
| Adobe on-ramp, metadata and publish | [`la-bip-adobe-customeraccount/LogicApp.json`](../bip/la-bip-adobe-customeraccount/LogicApp.json) |
| Adobe contract | [`AccountCreation.cs`](../bip/bbr.bip.Schema/AccountCreation.cs) |
| Adobe → SAP business mapping | [`MapCreateAccountToIdoc.cs`](../bip/bbr.bip.Mapping/MapCreateAccountToIdoc.cs) |
| Topic subscriptions and origin filters | [`AddMessageTypes.ps1`](../bip/bbr.bip.deploy/AddMessageTypes.ps1) |
| SAP off-ramp and connector call | [`la-bip-customeraccount-sap/LogicApp.json`](../bip/la-bip-customeraccount-sap/LogicApp.json) |
| SAP gateway | [`la-bip-sap-gateway-customeraccount/LogicApp.json`](../bip/la-bip-sap-gateway-customeraccount/LogicApp.json) |
| SAP on-ramp | [`la-bip-sap-customeraccount/LogicApp.json`](../bip/la-bip-sap-customeraccount/LogicApp.json) |
| SAP XML contract | [`ZBUPA_CBO.XSD`](../bip/bbr.bip.Schema/ZBUPA_CBO.XSD) |
| SAP → Adobe mapping and filter | [`ZBUPA_CBOService.cs`](../bip/bbr.bip.productservices/ZBUPA_CBOService.cs) |
| Adobe HTTP target calls | [`AdobeDataService.cs`](../bip/bbr.bip.productservices/AdobeDataService.cs) |
| FWT off-ramp | [`la-bip-customeraccount-fwt/LogicApp.json`](../bip/la-bip-customeraccount-fwt/LogicApp.json) |
| FWT contract | [`AccountCreationFWT.cs`](../bip/bbr.bip.Schema/AccountCreationFWT.cs) |
| SAP → FWT mapping | [`ZBUPA_CBOServiceFwt.cs`](../bip/bbr.bip.productservices/ZBUPA_CBOServiceFwt.cs) |
| FWT HTTP target call | [`FineWineDataServices.cs`](../bip/bbr.bip.productservices/FineWineDataServices.cs) |

## Orbital and Taxi references

- [Taxi models and model modifiers](https://taxilang.org/docs/language/models)
- [Describing HTTP services in Taxi](https://orbitalhq.com/docs/describing-data-sources/http)
- [Performing write mutations](https://orbitalhq.com/docs/querying/mutations)
- [Publishing saved queries as HTTP endpoints](https://orbitalhq.com/docs/querying/queries-as-endpoints)
- [Reading and writing XML](https://orbitalhq.com/docs/data-formats/xml)
- [Overriding service URLs](https://orbitalhq.com/docs/describing-data-sources/configuring-connections)
- [Stubbing services with Nebula](https://orbitalhq.com/docs/testing/stubbing-services)
- [Installing and running Taxi/Orbital](https://orbitalhq.com/docs/guides/installing)
- [Orbital local-disk workspace configuration](https://orbitalhq.com/docs/workspace/connecting-a-disk-repo)
- [RabbitMQ exchanges, topic routing, and bindings](https://www.rabbitmq.com/docs/exchanges)
- [RabbitMQ consumer acknowledgements](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ dead-letter exchanges](https://www.rabbitmq.com/docs/dlx)
- [RabbitMQ definition import](https://www.rabbitmq.com/docs/definitions)
- [RabbitMQ HTTP API limitations](https://www.rabbitmq.com/docs/next/http-api-reference)
- [Official RabbitMQ management image](https://hub.docker.com/_/rabbitmq)
- [Orbital connector source tree](https://github.com/orbitalapi/orbital/tree/develop/connectors)
- [Orbital plugin API warning](https://github.com/orbitalapi/orbital/blob/develop/plugin-api/README.md)
