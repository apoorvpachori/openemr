# Technical Decision Log — Clinical Co-Pilot

Running record of architectural decisions, tradeoffs, and rationale.
Used as input for ARCHITECTURE.md and the Architecture Defense.

---

## Deployment

### Decision: Dev docker on server (Option B) for initial deployment

**Chosen:** Use `docker/development-easy/docker-compose.yml` on a DigitalOcean Droplet. SSH in to deploy and update.

**Alternatives considered:**
- **Option A — upstream `openemr/openemr:latest`**: Pre-built, zero setup. Rejected because it is the upstream codebase, not our fork. Our AI module code would not be present.
- **Option B — dev docker on server (chosen)**: Clone the fork onto the Droplet and run the same dev docker compose we use locally. Mount the repo into the container — code changes take effect immediately with a container restart. Requires running the build steps (composer, npm, gulp) once on setup. Simple and fast for a one-week sprint.
- **Option C — custom Dockerfile**: Bakes code and assets into the image at build time. No manual build steps on the server. Better for CI/CD and scalability but adds build time and setup overhead not worth taking on in week 1.

**Why Option B now:**
- Fastest path to a live public URL (the hard gate for every submission)
- No Dockerfile to write or maintain yet
- Code updates: `git pull` + `docker restart` — done in under a minute
- The dev docker has all the devtools we need (demo data, random patients, API testing)

**Migration path to Option C:** When the AI service is added and we need reproducible multi-container deployments, we build the Dockerfile, push to GHCR, and wire up GitHub Actions for CI/CD. The production `docker-compose.yml` scaffold is already in place.

**Tradeoff:** Manual SSH deploys. Dev docker has extra services (selenium, openldap, mailpit) running on the server that are not needed in production — minor resource waste, acceptable for now.

---

### Decision: DigitalOcean Droplet over Railway / Render / Fly.io

**Chosen:** DigitalOcean Droplet (Ubuntu 22.04, 2GB RAM, ~$12/mo)

**Alternatives considered:**
- **Railway**: Excellent DX but does not natively support Docker Compose. Each service must be deployed individually and wired via env vars. OpenEMR's multi-container setup (PHP + MySQL + volumes with first-run initialization) is fragile in Railway's model.
- **Render**: Supports Docker but requires PostgreSQL for managed DB (OpenEMR is MySQL-only). Workarounds exist but add complexity.
- **Fly.io**: Supports multi-container via `fly launch` + volumes, but config translation from Docker Compose is non-trivial and adds friction in a one-week sprint.
- **DigitalOcean Droplet (chosen)**: A bare Linux server with Docker installed. Run the exact same `docker compose` commands locally and on the server — no translation layer, no platform-specific configs. Full control over networking and volumes.

**Why this matters for two containers:**
When the Python AI service is added, it's a third entry in `docker-compose.prod.yml`. All containers share a Docker internal network — OpenEMR's PHP bridge calls the AI service by its Docker service name (`ai-service`) without exposing it publicly. On Railway/Render, internal networking between separately deployed services requires additional configuration.

**Tradeoff:** Manual server setup (Docker install, SSH key management). No auto-scaling. Acceptable for a one-week sprint and a single-clinic target.

---

## AI Layer

### Decision: Python + FastAPI for AI service

**Chosen:** Python with FastAPI as the web framework for the AI service.

**Alternatives considered:**
- **PHP (in-process)**: OpenEMR is PHP. Adding AI in PHP avoids a second runtime. Rejected because LangGraph, LangSmith, and the Anthropic SDK are Python-first. No equivalent agentic framework exists in PHP.
- **JavaScript/TypeScript**: LangGraph.js exists but is a secondary citizen — thinner docs, fewer examples, lags behind the Python version. Rejected.
- **Python + FastAPI (chosen)**: Python is the standard runtime for LLM tooling. FastAPI is async, typed, and auto-generates OpenAPI docs. The Anthropic SDK, LangGraph, LangSmith, and every major eval framework are Python-native.

**Tradeoff accepted:** Two runtimes (PHP + Python), two containers, one internal network hop per AI query (~1ms, negligible). Auth is handled by the PHP bridge before Python is called, so the Python service does not need to re-implement OpenEMR session logic.

---

### Decision: LangGraph for agentic orchestration

**Chosen:** LangGraph (Python)

**Alternatives considered:**
- **LangChain chains**: Too much abstraction. Black-box execution makes it hard to insert a verification node at a specific point in the flow.
- **CrewAI**: Multi-agent framework. Adds orchestration overhead with no benefit for a single-agent system at MVP.
- **Raw Python (no framework)**: Maximum control, but requires hand-rolling state management, tool calling, retry logic, and observability hooks. Too expensive in a one-week sprint.
- **LangGraph (chosen)**: Explicit graph nodes map directly to the agent's required flow. The verification step is a first-class node, not bolted on. Native LangSmith tracing. Stateful multi-turn conversation with typed `TypedDict` state. Each node's failure mode is isolated and testable.

**Agent graph design:**
```
user_message → router → tool_node → synthesize → verify_claims → respond
                                        ↑                ↓
                                    (retry if         (strip/flag
                                    incomplete)      unverified claims)
```

---

### Decision: Claude (Anthropic) as the LLM

**Chosen:** Claude via Anthropic SDK

**Alternatives considered:**
- **GPT-4o**: Strong function calling, well-documented. Comparable quality. 128k context window.
- **Open source (Llama, Mistral)**: Self-hosted, no PHI leaves infra. Rejected for MVP — too slow to set up, quality gap for complex clinical reasoning.
- **Claude (chosen)**: 200k context window (entire patient record fits in one call without chunking). Naturally exhibits epistemic caution — more likely to say "I don't see that in the record" than to confabulate. Anthropic's safety focus aligns with clinical risk posture.

**Note:** Both Claude and GPT-4o are defensible. Claude's context window advantage matters most for patients with long histories (10+ years of encounters, labs, notes).

---

### Decision: LangSmith for observability (MVP) → Langfuse self-hosted (production)

**MVP:** LangSmith — zero-config LangGraph integration, traces every node automatically.

**Production path:** Langfuse self-hosted — PHI never leaves our infrastructure. LangSmith sends trace data to LangChain's servers, which is a HIPAA data governance concern for real patient data.

**Minimum observable questions from logs:**
- What did the agent do, and in what order?
- How long did each step take?
- Did any tools fail, and why?
- How many tokens were consumed, and at what cost?

---

### Decision: Direct MySQL access (MVP) → OpenEMR REST API (production)

**MVP:** Python service queries MySQL directly via SQLAlchemy. Simpler — no OAuth2 setup, no network round-trips per tool call.

**Security mitigation:** The PHP bridge (inside the OpenEMR module) validates the OpenEMR session, checks ACL permissions, and sanitizes the patient ID before calling Python. Python receives a pre-validated `(pid, authUser)` pair and trusts it.

**Production path:** Python service calls OpenEMR REST API (`/apis/default/api/`) with OAuth2 client credentials. Proper auth model, FHIR-compliant, decoupled from schema changes.

**Why not REST API from day one:** OAuth2 client credentials setup adds ~1 day of work. At MVP, the PHP bridge is the auth boundary. Documented as a known limitation in AUDIT.md and ARCHITECTURE.md.

---

## Integration

### Decision: OpenEMR custom module for AI chat UI

**Chosen:** Build as a custom module at `interface/modules/custom_modules/oe-module-ai-chat/`

**Rationale:**
- Embedded in the patient chart — physician sees it in the same window they're already in
- Inherits the OpenEMR session (knows which patient is open, who is logged in) without re-implementing auth
- Uses the existing Symfony EventDispatcher (`RenderEvent::EVENT_BODY_RENDER_POST`) to inject the chat panel — no core file modifications
- Self-contained and reversible — disable by removing the module folder
- Follows the same pattern as production modules (oe-module-faxsms, oe-module-dorn)

**PHP bridge security chain:**
```
SessionWrapperFactory  → validate authUser session is active
AclMain::aclCheck      → verify physician has 'patients/demo' permission
intval($pid)           → sanitize patient ID to integer
CsrfUtils::verify      → validate CSRF token on every request
→ only then call Python service
```

---

## Known Open Questions

- **Langfuse vs LangSmith for MVP**: LangSmith is faster to set up. If reviewers ask about HIPAA, explain the production migration plan to self-hosted Langfuse.
- **REST API auth for production**: OAuth2 client credentials flow needs to be implemented before go-live with real patients.
- **UI framework**: OpenEMR uses Knockout.js + jQuery (no React). Chat panel will be vanilla JS / jQuery to stay consistent. No build step needed for the frontend module code.
- **Eval dataset source**: Synthea-generated patients imported via devtools. Ground truth Q&A pairs written manually against known patient records.
