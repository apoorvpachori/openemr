# OpenEMR Audit — Clinical Co-Pilot Integration

## Executive Summary (~500 words)

This audit covers OpenEMR as the foundation for a Clinical Co-Pilot AI agent. Five areas were examined: security, performance, architecture, data quality, and compliance. The findings below represent the most impactful risks and constraints that must be addressed before the AI layer is production-trustworthy.

**The most critical finding is a data governance gap at the LLM boundary.** Every patient query the agent processes sends PHI to an external LLM provider (Anthropic/Claude). HIPAA requires a signed Business Associate Agreement (BAA) before any PHI touches a third-party processor. For this project, we operate under Gauntlet's stated assumption that a BAA is in place and that no data will be used for training. In a real deployment, this BAA must be formally executed before go-live — it is a legal prerequisite, not a technical one.

**The second most critical finding is that the development environment exposes PHI pathways with default credentials.** The dev Docker setup exposes MySQL directly on port 8320 and phpMyAdmin on port 8310 with default credentials (`openemr`/`openemr`). On a public-facing server, any patient data loaded into the dev environment is reachable without authentication over the open internet. For this project we use only synthetic demo data, which mitigates the legal risk — but the exposure pattern must not carry into any environment with real patient records.

**The third critical finding is that AI query activity is not yet audit-logged.** HIPAA's audit control requirement (§164.312(b)) requires that all access to PHI be logged. OpenEMR has a mature `EventAuditLogger` that tracks every page view and data access. The AI agent, however, bypasses this when it queries patient data on behalf of a physician. Every agent query — the question asked, the patient record accessed, and the response returned — must be appended to the audit log before this system can be considered compliant.

**On performance**, the primary constraint is the combination of a 1vCPU/2GB server and synchronous PHP execution. A physician needs a response in under 5 seconds. Each agent tool call (medications, labs, encounters, problems) triggers a separate DB query or API round-trip. With 4–6 tool calls per query, latency compounds quickly. The `lists` table — which serves medications, problems, and allergies through a single multipurpose schema — adds query overhead. Direct MySQL access from the Python service (rather than chaining through the REST API) is the correct choice for MVP to keep latency manageable.

**On data quality**, the most agent-relevant risk is that lab results are stored as VARCHAR strings in `procedure_result.result`, requiring numeric parsing before the agent can reason about values or ranges. Encounter reason fields and SOAP notes are free text with no enforced structure, meaning agent synthesis quality is directly dependent on how well physicians documented. Synthea-generated patients have realistic but sometimes incomplete data — missing fields become agent failure modes where the system must explicitly surface "no data available" rather than hallucinate.

**The architecture is genuinely well-suited for this integration.** The Symfony EventDispatcher module system allows clean UI injection with no core modifications. The existing REST API and FHIR R4 endpoints cover all data the agent needs. The session-based auth model provides a clear security boundary: the PHP bridge validates identity and ACL before the Python service is ever called.

---

## 1. Security Audit

### Authentication

OpenEMR uses session-based authentication implemented in `src/Common/Auth/AuthUtils.php` and `library/auth.inc.php`.

**Strengths:**
- Passwords stored as bcrypt hashes via `AuthHash::passwordVerify()`
- Timing attack prevention via `preventTimingAttack()` in `AuthUtils`
- IP-based login failure tracking (`setupIpLoginFailedCounter()`)
- Session expiration enforced via `SessionTracker::isSessionExpired()`
- CSRF tokens required on all form submissions and AJAX requests via `CsrfUtils::verifyCsrfToken()`

**Risks:**
- **Default credentials in docker-compose**: `OE_USER: admin`, `OE_PASS: pass` are hardcoded in `docker/development-easy/docker-compose.yml`. On a publicly deployed dev server, anyone who finds the URL gets admin access.
- **No visible rate limiting on the login endpoint**: The IP failure counter exists but there is no lockout or CAPTCHA visible in the codebase. A determined attacker can brute-force credentials.
- **Session tokens in URL**: Some internal redirects pass session tokens as URL parameters (e.g., `?token_main=...` in `main.php`). URL parameters appear in server logs and browser history.
- **Self-signed SSL certificate in dev**: The development Docker environment generates a self-signed cert. Browsers warn users and connections are not verified by a CA. Any production deployment must use a legitimate certificate (Let's Encrypt or equivalent).

### Authorization

Authorization uses GACL (Generic Access Control List) implemented in `src/Common/Acl/AclMain.php`.

**Strengths:**
- Fine-grained section/value/permission model: `patients/demo`, `patients/med`, `encounters/notes`, etc.
- Superuser bypass is explicit and auditable
- PID (patient ID) is always forced through `intval()` in `PatientSessionUtil::setPid()` before being stored in session
- ACL is checked at both the page level and API endpoint level

**Risks:**
- **GACL complexity creates misconfiguration risk**: The ACL system has 20+ permission sections. A misconfigured role could grant a nurse access to records outside their scope. No automated test coverage validates that specific role combinations enforce the right boundaries.
- **Multi-user environments not tested in dev setup**: The dev environment has one user (admin). The access control model for a physician who should only see their own panel's patients is not validated in this setup.
- **AI agent inherits session permissions without granular scoping**: The agent, acting on behalf of a logged-in physician, can query any patient the physician has access to. If a physician has broad access, the agent inherits it. There is no additional constraint that limits the agent to the patient currently open in the chart.

### Data Exposure Vectors

- **MySQL exposed on port 8320**: The dev docker-compose maps MySQL port 3306 to host port 8320. On a public server, this allows direct DB connections from the internet with credentials `openemr`/`openemr`.
- **phpMyAdmin exposed on port 8310**: Full database browser accessible with the same credentials. This is a complete PHI exposure vector on a public server.
- **PHP error messages**: Legacy PHP code may surface stack traces or SQL errors to the browser if `display_errors` is enabled. The dev environment enables Xdebug which can expose additional internals.
- **Log files**: Apache and PHP logs in `/var/log` inside the container may contain query strings, patient IDs, or session tokens depending on log level configuration.

### PHI Handling in the AI Layer

The most significant new exposure vector introduced by the Clinical Co-Pilot:

- **PHI leaves the OpenEMR perimeter to reach the LLM**: Patient names, diagnoses, medications, and lab results are included in LLM prompts. This is PHI under HIPAA regardless of how it is structured.
- **LangSmith traces contain query context**: If LangSmith is used for observability, full agent traces (including tool call results containing patient data) are sent to LangChain's servers. This is a BAA-required data transfer.
- **Agent response caching risk**: If responses are cached (e.g., for performance), cached content containing PHI must be subject to the same access controls and retention policies as the source record.

### Prompt Injection Risk

- Patient-controlled data (names, notes, reason for visit) flows into LLM context. A patient could theoretically craft a name or note field containing instruction text designed to manipulate agent behavior.
- Mitigation: the agent prompt must clearly separate system instructions from patient data. Tool results must be presented as data, not as instructions.

---

## 2. Performance Audit

### Server Constraints

The deployment target is a DigitalOcean Droplet (1vCPU, 2GB RAM) running Docker. This is the primary performance constraint for the MVP.

- **1vCPU**: PHP is synchronous. Each web request occupies the CPU until complete. Under concurrent load (multiple physicians), requests queue.
- **2GB RAM**: Shared across OpenEMR (PHP/Apache), MySQL, and the Python AI service. Memory pressure can cause MySQL to flush caches and slow queries significantly.
- **Docker overhead**: Each container adds a small but non-zero resource cost.

**Practical implication**: The agent cannot run multiple simultaneous queries from different physicians without degrading response time on the 1vCPU droplet. This is acceptable for an MVP demonstrating single-user usage.

### Database Query Patterns

The tables relevant to the Clinical Co-Pilot and their query characteristics:

| Table | Query type | Risk |
|---|---|---|
| `patient_data` | Single-row lookup by `id` | Low — primary key lookup |
| `form_encounter` | Range query by `pid`, ordered by `date DESC` | Medium — needs index on `(pid, date)` |
| `lists` | Filtered by `pid` AND `type` | Medium — compound filter on a high-volume table |
| `lists_medication` | Join to `lists` | Low if `lists` query is fast |
| `procedure_order` | Filtered by `pid` | Medium |
| `procedure_result` | Join through `procedure_report` to `procedure_order` | High — 3-table join chain |
| `form_soap` | Filtered by `pid` and `encounter` | Low — bounded by encounter |

**Key bottleneck: the `lists` table** serves medications, problems, and allergies in a single table differentiated by a `type` column. A patient with a long history generates many rows. Querying all three types in parallel (three separate queries, not one) is preferable to a single query with an OR condition.

**Key bottleneck: lab results** require joining `procedure_order` → `procedure_report` → `procedure_result`. For a patient with extensive lab history, this join can return hundreds of rows. The agent should query only the most recent N results per test, not the full history.

### REST API vs Direct MySQL

The existing REST API (`/apis/default/api/`) is fully functional but adds overhead per tool call:
- Each REST call goes through: HTTP request → OAuth2 validation → PHP routing → DB query → JSON serialization → HTTP response
- For 5 tool calls per agent query, this is 5 full HTTP round-trips through the PHP stack

**Decision: use direct MySQL from the Python service for MVP**, with the PHP bridge handling auth. This eliminates the HTTP overhead and OAuth2 validation per tool call. The REST API is the correct production path once latency budgets are validated.

### Response Latency Budget

Target: agent response in <5 seconds (physician has 90-second window between rooms).

Estimated breakdown for a typical query:
```
PHP bridge validation:          ~50ms
Python service routing:         ~10ms
Tool calls (5x DB queries):     ~200ms (40ms avg each)
LLM inference (Claude):         ~2-4s  (dominant factor)
Verification pass:              ~200ms
Response serialization:         ~50ms
Total estimate:                 ~3-5s
```

The LLM inference time is the dominant variable. Streaming responses (showing text as it generates) is the correct UX choice — the physician sees the beginning of the answer while the rest generates.

---

## 3. Architecture Audit

### System Overview

OpenEMR is a hybrid legacy-modern PHP application backed by MySQL/MariaDB, running inside Docker containers.

```
Browser (Physician)
    ↓ HTTP/HTTPS
Apache Web Server (inside Docker)
    ↓
public/index.php  →  FallbackRouter  →  interface/globals.php (auth check)
    ↓
/interface/**/*.php     →  HTML response (server-rendered)
/apis/default/api/*    →  JSON (REST API, OAuth2)
/apis/default/fhir/*   →  JSON (FHIR R4, OAuth2)
    ↓
MySQL/MariaDB (separate container)
```

### Code Organization

| Path | Purpose |
|---|---|
| `/src` | Modern PSR-4 code (`OpenEMR\` namespace) — services, REST controllers, FHIR, events |
| `/library` | Legacy procedural PHP — utility functions, ADODB database layer |
| `/interface` | Web UI pages — one PHP file per feature area |
| `/interface/modules/custom_modules/` | Plugin system — where AI module goes |
| `/apis` | REST API route definitions |
| `/sql` | Database schema and migration scripts |

### Integration Points for the AI Layer

**1. UI Injection — `RenderEvent::EVENT_BODY_RENDER_POST`**
Located in `src/Events/Main/Tabs/RenderEvent.php`. Fires in `interface/main/tabs/main.php` after the page body renders. Modules listening to this event can append HTML — the correct injection point for the chat panel sidebar.

**2. Module Bootstrap — `openemr.bootstrap.php`**
Every file in `/interface/modules/custom_modules/*/openemr.bootstrap.php` is auto-loaded at startup. This is where event listeners are registered. Reference implementations: `oe-module-faxsms` and `oe-module-dorn`.

**3. Patient Context — Session**
The current patient ID is stored in `$session->get('pid')` after being validated by `PatientSessionUtil::setPid()` (which forces `intval()` and logs an audit event). This is available to the PHP bridge without additional queries.

**4. REST API — `/apis/default/api/`**
Fully documented in `swagger/openemr-api.yaml`. All agent-relevant data is reachable via existing endpoints. OAuth2 client credentials grant is the auth mechanism for backend services.

**5. Direct DB — MySQL on port 8320 (dev) / internal Docker network (prod)**
For MVP, the Python service connects to MySQL using credentials from the compose environment. In production, access is over the internal Docker network only — MySQL is not exposed publicly.

### Auth Flow for Agent Requests

```
Physician opens patient chart (main.php)
    ↓ RenderEvent fires → chat panel injected
Physician submits question → ai-chat.js fetch() to chat.php (inside module)
    ↓
chat.php:
  1. SessionWrapperFactory → validate authUser session
  2. AclMain::aclCheckCore('patients', 'demo') → verify access
  3. intval($pid) → sanitize patient ID
  4. CsrfUtils::verifyCsrfToken() → validate request origin
    ↓
HTTP POST to Python FastAPI service (internal Docker network)
  payload: { pid, authUser, message }
    ↓
LangGraph agent → MySQL queries → LLM → verify → respond
    ↓
JSON response → physician sees answer in chat panel
```

---

## 4. Data Quality Audit

### Demo Data (from devtools `dev-reset-install-demodata`)

The OpenEMR demo dataset includes pre-configured patients with structured records: demographics, encounters, medications, problems, and some lab results. Data completeness is high for core fields. This is the most reliable data in the system for agent testing.

### Synthea-Generated Patients (from `import-random-patients`)

Synthea generates FHIR R4-compliant synthetic patients and imports them via the CCDA importer. Key data quality observations:

**Strengths:**
- Realistic multi-year encounter histories
- ICD-10 coded conditions
- Medication lists with dosages and start dates
- Lab results with reference ranges

**Weaknesses and agent failure modes:**

| Issue | Table | Impact on agent |
|---|---|---|
| Lab results stored as VARCHAR | `procedure_result.result` | Agent cannot do numeric comparison without parsing; must handle non-numeric values gracefully |
| `abnormal` flag is text (`"high"`, `"low"`, `"yes"`, `"no"`, `""`) | `procedure_result.abnormal` | Inconsistent flag values; agent must normalize before reasoning |
| Encounter reasons are free text | `form_encounter.reason` | No structured parsing; agent synthesis depends on documentation quality |
| SOAP notes are unstructured | `form_soap` | Agent cannot reliably extract structured clinical facts from free-text notes |
| Many nullable fields in `patient_data` | `patient_data` | Missing DOB, sex, contact info; agent must handle nulls explicitly |
| `lists.enddate` often null for active records | `lists` | Agent cannot reliably distinguish "active" from "historical" medication without checking `activity` flag |
| Procedure result dates come from the lab, not OpenEMR | `procedure_result.date` | Dates may be missing or in unexpected formats for some lab imports |
| Duplicate problem entries possible | `lists` (type=medical_problem) | Same diagnosis can appear multiple times from different encounters; agent must deduplicate |

### Data Completeness by Category

| Data type | Completeness in demo data | Completeness in Synthea patients |
|---|---|---|
| Patient demographics | High | High |
| Encounter history | High | High |
| Medication list | High | Medium (some missing dosages) |
| Problem list | High | High |
| Allergies | Medium | Low (often empty) |
| Lab results | Low | Medium |
| SOAP notes | Low | Low (minimal text) |
| Vital signs | Medium | Medium |

### Agent Failure Mode Inventory

The following conditions must be handled explicitly rather than allowing the agent to infer or hallucinate:

1. **No medications on file** → respond "No active medications recorded"
2. **No recent labs** → respond "No lab results in the past N months"
3. **Lab result is non-numeric** → do not attempt range comparison
4. **Encounter reason is blank** → do not fabricate a reason
5. **Patient has no encounters** → surface this explicitly
6. **Allergy list is empty** → distinguish "no known allergies" from "not documented"

---

## 5. Compliance & Regulatory Audit

### HIPAA Technical Safeguards (45 CFR §164.312)

| Requirement | Safeguard | OpenEMR Status | AI Layer Status |
|---|---|---|---|
| Access control (§164.312(a)(1)) | Unique user IDs, role-based access | Implemented via GACL | Inherited via PHP bridge |
| Audit controls (§164.312(b)) | Hardware/software activity logs | Implemented via `EventAuditLogger` | **Not yet implemented for agent queries** |
| Integrity (§164.312(c)(1)) | PHI not improperly altered | DB transactions, no direct write from agent | Agent is read-only — acceptable |
| Transmission security (§164.312(e)(2)) | Encryption in transit | SSL/TLS (self-signed in dev) | LLM calls are HTTPS — acceptable |

### Audit Logging Gap (Critical)

Every access to PHI must be logged under HIPAA §164.312(b). OpenEMR's `EventAuditLogger` handles this for all native page views and API calls:

```php
EventAuditLogger::getInstance()->newEvent(
    "view", $authUser, $authProvider, 1, '', $pid
);
```

The AI agent currently bypasses this. Required additions:
- Log every agent query: who asked, which patient, timestamp
- Log every tool call that accesses PHI
- Log the category of response returned (not the full response — avoid logging PHI in the audit trail itself)

### Business Associate Agreements (BAA)

HIPAA requires a BAA with every vendor who processes PHI on your behalf.

| Vendor | PHI exposure | BAA required | Status |
|---|---|---|---|
| Anthropic (Claude API) | Full patient context in prompts | Yes | Enterprise BAA available; assumed signed per Gauntlet guidelines |
| LangChain (LangSmith) | Full agent traces including tool results | Yes | Available but requires enterprise plan; **use demo data only** |
| DigitalOcean | PHI stored on Droplet disk | Yes | DigitalOcean offers HIPAA-eligible infrastructure with BAA |

**For production with real patients**: All three BAAs must be executed before go-live. The Anthropic and DigitalOcean BAAs are the highest priority.

### PHI in Observability (LangSmith Risk)

LangSmith traces include the full content of every tool call result — which contains patient names, diagnoses, medications, and labs. Sending this to LangChain's servers without a BAA is a HIPAA violation.

**Mitigation for MVP**: Use demo/synthetic data only. No real patient data enters the system.

**Production mitigation**: Replace LangSmith with self-hosted Langfuse. PHI traces stay within the DigitalOcean infrastructure covered by the BAA.

### Data Retention

HIPAA requires covered entities to retain:
- Medical records: state law governs (typically 7–10 years); minimum 6 years for HIPAA documentation itself
- Audit logs: 6 years
- PHI in backups: subject to the same retention and destruction policies as primary records

**Current state**: Docker volumes hold database data. There is no automated backup, no retention policy enforcement, and no documented destruction procedure. For production, a backup strategy (volume snapshots, encrypted off-site) and documented retention policy are required.

### Breach Notification (§164.400–414)

Under the HIPAA Breach Notification Rule:
- Covered entities must notify affected individuals within 60 days of discovering a breach
- HHS must be notified; breaches affecting 500+ individuals require media notification
- Business associates must notify the covered entity within 60 days

**Current exposure**: The dev Docker setup with exposed MySQL and phpMyAdmin ports on a public server constitutes a potential breach vector if real PHI were present. For demo data, the legal risk is low but the pattern is dangerous.

### Recommended Compliance Actions Before Production

1. Close MySQL (8320) and phpMyAdmin (8310) ports — not needed on a production server
2. Implement audit logging for all agent queries via `EventAuditLogger`
3. Execute BAAs with Anthropic, LangChain (or migrate to self-hosted Langfuse), and DigitalOcean
4. Migrate to real SSL certificate (Let's Encrypt via Certbot)
5. Implement automated database backups with documented retention policy
6. Change all default credentials before any real patient data enters the system
7. Document the data flow from physician query → LLM → response for BAA evidence
