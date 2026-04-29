# User Profiles — Clinical Co-Pilot

## Primary User: Dr. Sarah Chen, Primary Care Physician

### Profile

| Attribute | Detail |
|-----------|--------|
| **Role** | Primary Care Physician (Family Medicine) |
| **Practice size** | Solo practice, 1 support staff |
| **Patient volume** | 18–22 patients/day, back-to-back 15-minute appointments |
| **EHR experience** | 6 years on OpenEMR; faster than average at navigation |
| **Technology comfort** | High — uses keyboard shortcuts, hates clicking through tabs |
| **Biggest pain point** | "I have 90 seconds between rooms. The chart takes 45 of them." |

### Why This User

Dr. Chen is the sharpest version of the target audience. She is already fast — and still frustrated. If the agent saves her meaningful time, it will save every slower physician even more. She is not a power user who needs maximum control; she is a competent physician who needs maximum *speed*. If the agent fails her, she will stop using it. This constraint forces the agent to be genuinely useful, not just present.

---

## Moment-by-Moment Workflow

### Full Day Overview

```
7:30 AM  — Arrive. Review today's schedule (18 patients). Flag anything unusual.
7:55 AM  — First patient called back.

[Repeat 18 times until ~5:00 PM]
  :00     — Previous patient exits. Nurse calls next patient to exam room.
  :00–:01 — Walk from exam room A to exam room B (90 seconds).
  :02     — Enter room. Patient is seated.
  :02–:15 — Appointment (15 minutes).

5:00 PM  — Last patient done.
5:00–6:30 — After-hours chart review: sign off on labs, write referral letters,
             respond to patient messages, complete encounter notes.
```

### The 90-Second Window (The Primary Use Case)

This is where the Clinical Co-Pilot lives. It is the hardest 90 seconds in the physician's day.

```
:00  Patient exits. Nurse says "Room 2, Marcus Webb, here for diabetes follow-up."
:05  Dr. Chen pulls up Marcus Webb's chart in OpenEMR.
:10  Chart loads. She is looking at a wall of tabs: Summary, Encounters,
     Medications, Labs, Problems, Orders, Documents...
:15  She clicks Encounters → scrolls to find the last visit → opens it.
:30  She reads the last SOAP note. Scans for what she ordered last time.
:45  She switches to Labs → filters → finds the HbA1c from 3 weeks ago.
:60  She switches to Medications → scans for Metformin dose.
:75  She has enough. She walks to room 2.
:90  "Good morning Marcus, how are you feeling?" — she is already behind.
```

**With the Clinical Co-Pilot:**

```
:00  Patient exits. Nurse says "Room 2, Marcus Webb, diabetes follow-up."
:05  Dr. Chen opens Marcus Webb's chart. The chat panel is already visible.
:08  She types: "What changed since his last visit?"
:12  Agent responds:
     - HbA1c improved: 8.4 → 7.9 (drawn 3 weeks ago) [Lab #4821]
     - Metformin increased to 1000mg BID at last visit [Encounter 2/14]
     - BP at last visit: 138/88 — slightly elevated, no med change made [Encounter 2/14]
     - Pending: lipid panel ordered 2/14, not yet resulted
:13  She asks: "Any medication changes in the last 6 months?"
:16  Agent responds: "Metformin 500mg → 1000mg BID (2/14). No other changes."
:17  She walks to room 2, already knowing what to address.
:90  "Good morning Marcus — your A1c came down, that's real progress."
```

Time saved: ~60 seconds. Cognitive load eliminated: tab-switching, manual scanning, mental state reconstruction.

---

## Use Cases

### Use Case 1: Between-Room Patient Prep ("What changed?")

**Trigger:** Physician is about to enter exam room for a returning patient.

**Question asked:** "What changed since [patient's] last visit?" or "Catch me up on [patient]."

**Agent behavior:**
1. Fetch last encounter note + date
2. Fetch current med list, compare to list as of last encounter
3. Fetch labs ordered at last encounter + results status
4. Fetch any new problems added since last visit
5. Synthesize: changes only, with source citations (encounter ID, lab ID, date)

**Why conversational agent beats a dashboard:**

A dashboard for "what changed" requires the physician to define change thresholds up front (what counts as significant?), maintain them as the patient's condition evolves, and still read through a structured display before walking into the room. The agent answers in plain English tailored to the specific question being asked. The physician does not configure anything — she asks the question she already has in her head and gets a direct answer. A dashboard cannot answer "what changed" for 18 different patients with 18 different conditions without becoming 18 different dashboards.

---

### Use Case 2: Lab Review ("What labs are back?")

**Trigger:** Physician has a few minutes between patients or during after-hours review. She ordered labs 1–3 weeks ago and wants to know what came back and whether anything is abnormal.

**Question asked:** "What labs are back for [patient]? Anything abnormal?"

**Agent behavior:**
1. Fetch `procedure_result` rows for the patient, ordered by result date descending
2. Filter for `result_status = 'final'`
3. Check `abnormal` flag on each result
4. Return: result name, value, unit, reference range, abnormal flag, date
5. If a result is abnormal, surface it first with the specific value and range

**Why conversational agent beats a dashboard:**

Lab result dashboards exist. OpenEMR already has a lab results view. The problem is not display — it is triage. With 18 patients and 40+ pending results, the physician needs to know which ones need action today. An agent can say "The only abnormal result is Marcus Webb's creatinine at 1.8 (ref: 0.7–1.3) — drawn yesterday." A dashboard shows all 40 results with colored flags and requires the physician to scan. The agent answers the question: *what do I need to act on?*

---

### Use Case 3: Medication Safety Check ("Is it safe to add X?")

**Trigger:** During an appointment, physician is considering adding a new medication and wants a quick interaction check against the current med list.

**Question asked:** "What is [patient] currently on? Any concerns if I add lisinopril?"

**Agent behavior:**
1. Fetch active medication list (`lists` table, `type='medication'`, `activity=1`)
2. List current meds with dosages
3. Flag any known interaction pattern between listed meds and lisinopril (basic: potassium-sparing diuretics + ACE inhibitor → hyperkalemia risk)
4. Return list + any flags, clearly citing which meds triggered the flag

**Limitations stated explicitly:** Agent is not a clinical decision support system. It surfaces known patterns from its training; it does not replace pharmacist review for complex cases. Responses include: "Always verify with a pharmacist for complex interactions."

**Why conversational agent beats a dashboard:**

A medication list is already visible in OpenEMR. The physician does not need a dashboard to see it — she needs to ask a question *about* it in the moment, while standing in the exam room. "Any concerns if I add lisinopril?" is not a query a static dashboard supports. It requires reasoning over the current state in response to a dynamic clinical question. This is precisely what a conversational agent is designed to do.

---

### Use Case 4: Schedule Prep ("What do I need to know before clinic?")

**Trigger:** 7:30 AM, before the first patient. Physician opens the day's schedule and wants to know if anyone on the list has something flagged that she should be aware of before walking in.

**Question asked:** "I have 18 patients today. Anyone I should know about before I start?"

**Agent behavior:**
1. Read today's scheduled patient list (from `openemr_postcalendar_events`)
2. For each patient, check: pending abnormal labs, upcoming preventive care gaps, active medication alerts
3. Surface only the patients who have something actionable — not a report on all 18
4. Format: brief bullet per patient, one line each

**Why conversational agent beats a dashboard:**

This use case cannot be served by a per-patient dashboard at all — it requires cross-patient aggregation that a static view does not provide. The physician would have to open 18 charts. The agent reads across all 18 and returns only the ones that matter. It is the difference between "here is your morning briefing" and "here are 18 charts, good luck."

---

### Use Case 5: After-Hours Note Completion ("What did I order?")

**Trigger:** 5:30 PM, physician is completing encounter notes for the day. She remembers ordering something for a patient but cannot recall what.

**Question asked:** "What did I order for [patient] at today's visit?"

**Agent behavior:**
1. Fetch `procedure_order` rows for the patient with today's date
2. Return: order names, ordered time, order status
3. Also fetch the encounter note if started, show what is drafted vs. signed

**Why conversational agent beats a dashboard:**

The physician already has the chart open. The orders tab is one click away. This use case is marginal — the agent is mildly more convenient than clicking. It is included because the cost is zero (same tools, same data access) and because it establishes the agent as a reliable reference for anything in the record, not just between-room use. If the agent proves useful here, it builds the habit of reaching for it first.

---

## Non-Goals (Explicit Scope Limits)

| What the agent does NOT do | Why |
|---|---|
| Prescribe or recommend medication doses | Clinical decision support is a regulated activity; the agent is a co-pilot, not a prescriber |
| Access patient data the physician cannot see | Agent inherits OpenEMR session ACL — scoped to the logged-in provider's patient list |
| Operate autonomously (take actions in the chart) | Read-only at MVP — no orders placed, no notes written |
| Replace a clinical decision support system (CDSS) | Drug interaction checking is a CDSS function; agent provides context, not clinical decisions |
| Answer questions about patients not in OpenEMR | Agent queries only the local OpenEMR MySQL instance — no external data sources |
| Retain conversation history across sessions | Each session is stateless at MVP — context resets when the chart is closed |

---

## Secondary User: Nurse / Medical Assistant (Future Scope)

Not in MVP scope, documented for completeness.

The nurse calls patients back, records vitals, and does medication reconciliation. Their questions are different: "What medications did this patient report taking at their last visit?" or "Were these vitals recorded correctly?" The agent's tools support these questions but the auth model (physician-scoped ACL) and the UI injection point (patient chart page, physician context) are designed for the physician. A nurse-facing version would require different ACL checks and a different entry point. Deferred to post-MVP.

---

## Success Criteria

The Clinical Co-Pilot is working when:

1. **Between-room prep takes under 20 seconds** — physician gets a usable summary before walking into the room, without opening any additional tabs
2. **Zero hallucinated facts in 100 consecutive queries** — every claim in the response is traceable to a specific record in OpenEMR
3. **Physician trusts it enough to use it unprompted** — adoption is the real metric; if she reaches for it before opening the chart manually, it has earned its place
4. **No patient data is surfaced to the wrong provider** — ACL enforcement is verified adversarially in the eval suite
