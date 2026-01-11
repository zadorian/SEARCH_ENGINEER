# COMPLETE END-TO-END FLOW CHAINS

## THE DESIGNED FLOW (Your Vision)
```
TEMPLATE → WATCHERS → QUERY ON SUBJECT → RESULTS → GRID ROTATION
→ K-U INTENT (ENRICH/DISCOVER) → FILL HEADER SECTIONS BY WATCHERS
→ IDENTIFY GAPS → CRAFT NEW QUERY → RUN NEW SEARCH → LOOP
→ ACTIVE SECTIONS DEFINE GROUNDING, CONTEXT, AND AIM
```

---

## WHAT EXISTS TODAY (Building Blocks)

| Component | Status | Location | Notes |
|-----------|--------|----------|-------|
| Template Routing | ✅ COMPLETE | `edith-templates/scripts/route.py` | Deterministic jurisdiction+genre detection |
| Template Composition | ✅ COMPLETE | `edith-templates/scripts/compose.py` | Returns `allowed_actions`, `dd_sections` |
| 24 ALLOWED_ACTIONS | ✅ COMPLETE | `resilience.py` | SEARCH_REGISTRY, SEARCH_OFFICERS, etc. |
| Watcher Creation | ✅ COMPLETE | `bridges.py` (15 tRPC procs) | create(), createEvent(), createTopic(), createEntity() |
| Slot System | ✅ COMPLETE | `contracts.py:860-1167` | Binary states: EMPTY, FILLED, CONTESTED, VOID |
| Slot Feed Callbacks | ✅ COMPLETE | `execution_orchestrator.py:365-392` | `on_slot_fed()`, `on_collision()` |
| K-U Matrix | ✅ COMPLETE | `cognitive_engine.py:144-149` | VERIFY, TRACE, EXTRACT, DISCOVER |
| Chain Dependencies | ✅ COMPLETE | `investigation_planner.py:411-440` | `depends_on`, `feeds_slots` |
| Fallback Chains | ✅ COMPLETE | `resilience.py:106-200` | Primary → Archive → Cache → Manual |
| Sufficiency Check | ✅ COMPLETE | `sufficiency.py:33-399` | 5 binary constraints + semantic check |
| Grid 4-Mode Rotation | ✅ COMPLETE | `grid/assessor.py` | NARRATIVE, SUBJECT, LOCATION, NEXUS |
| Parallel Execution | ⚠️ PARTIAL | `grid/assessor.py` | Only grid assessment uses asyncio.gather |

---

## WHAT'S MISSING (BARRIERS TO END-TO-END)

### BARRIER 1: No Template Auto-Trigger
**Gap:** Template loads but doesn't AUTO-spawn watchers or AUTO-run queries
**Exists:** Template returns `allowed_actions` and `dd_sections`
**Missing:** Operator to LOAD template and trigger cascade

### BARRIER 2: Watchers Don't Spawn Watchers
**Gap:** When watcher fires, it routes findings but doesn't create new watchers
**Exists:** `on_slot_fed()` callback when slot fills
**Missing:** Cascade trigger: "slot fills → spawn watcher for new entity"

### BARRIER 3: No Operator-Level IF/THEN/ELSE
**Gap:** Orchestrator has phase branching, but no operator syntax for conditionals
**Exists:** Sufficiency checks, K-U quadrant checks
**Missing:** `IF sufficient? THEN write_section ELSE continue_search`

### BARRIER 4: Parallel Syntax Is Sequential
**Gap:** `{ !a, !b }` syntax parses but executes in loop, not `asyncio.gather()`
**Exists:** Parallel parsing in `macros.py`
**Missing:** True concurrent execution

### BARRIER 5: No "Loop Until Sufficient" Control
**Gap:** 7-phase pipeline runs once, no automatic re-loop
**Exists:** `resume_investigation()` placeholder
**Missing:** `WHILE unfilled? DO search_next`

### BARRIER 6: No Slot→Section Binding
**Gap:** Slots fill but don't auto-populate template sections
**Exists:** Slots with `feeds_slots` declaration
**Missing:** `=> section:{section_id}` routing

---

## FULL COMPANY DD OPERATOR CHAIN

### Prerequisites
- Entity: Company name (e.g., "Acme Corp")
- Jurisdiction: Detected or specified (e.g., ":UK")

### PHASE 1: TEMPLATE LOAD (Auto-Trigger)
```
template:COMPANY_DD:UK :#AcmeCorp
```
**What should happen:**
1. Load UK jurisdiction template
2. Load COMPANY_DD genre template
3. Stack templates → get 13 `dd_sections`
4. For each section, create watcher automatically
5. Return `allowed_actions` list

### PHASE 2: CORE LOOKUP (Parallel)
```
{ cuk: Acme Corp, reguk: Acme Corp } => +#registry_data
```
**Operators used:** `cuk:`, `reguk:`, `{ }` parallel, `=>` tag
**Returns:** Company #, status, SIC codes, registered address

### PHASE 3: EXTRACT OFFICERS (Depends on Phase 2)
```
p? :#registry_data @PERSON => +#officers
```
**Operators used:** `p?` (person extraction), `@PERSON` filter, `=>` tag
**Returns:** Officer names, positions, appointment dates

### PHASE 4: OFFICER ENRICHMENT (Parallel foreach)
```
foreach #officers => { p: [NAME], puk: [NAME] } => +#officer_profiles
```
**Operators used:** `foreach` (loop), `p:`, `puk:`, parallel `{ }`
**Returns:** Each officer's background, other directorships

### PHASE 5: OWNERSHIP EXTRACTION
```
c? :#registry_data @COMPANY ##shareholder => +#shareholders
```
**Operators used:** `c?` (company extraction), `@COMPANY`, `##shareholder`
**Returns:** Shareholder list with ownership %

### PHASE 6: BENEFICIAL OWNER TRACE (IF needed)
```
IF NOT filled? :#section_ubo THEN
    foreach #shareholders => c: [COMPANY] => +#ubo_chain
```
**Operators used:** `IF/THEN`, `filled?`, `foreach`, `c:`
**Returns:** Ultimate beneficial owner chain

### PHASE 7: REGULATORY & SANCTIONS (Parallel)
```
{
    OFAC: Acme Corp,
    sanctions?: [OFFICERS],
    reguk: Acme Corp ##regulatory
} => +#compliance_data
```
**Operators used:** `OFAC:`, `sanctions?`, `reguk:`, parallel `{ }`
**Returns:** Sanctions hits, FCA status, regulatory authorizations

### PHASE 8: LITIGATION SEARCH
```
lituk: Acme Corp => +#litigation
lituk: [OFFICERS] => +#officer_litigation
```
**Operators used:** `lituk:`
**Returns:** Court cases, judgments, enforcement actions

### PHASE 9: FINANCIAL EXTRACTION
```
docuk: [COMPANY_NUMBER] ##accounts => +#financials
```
**Operators used:** `docuk:`, `##accounts`
**Returns:** Filed accounts, turnover, assets

### PHASE 10: ADVERSE MEDIA (Parallel)
```
{
    newsuk: "Acme Corp",
    newsuk: "[CEO_NAME]",
    newsuk: "[CFO_NAME]"
} => +#media
```
**Operators used:** `newsuk:`, parallel, exact phrase `""`
**Returns:** News mentions, controversies

### PHASE 11: SUFFICIENCY CHECK
```
sufficient? @section:all
```
**Returns:** `{sufficient: bool, unfilled_sections: [...], score: 0.85}`

### PHASE 12: GAP FILL LOOP
```
WHILE NOT sufficient? DO
    gaps? => intent? => query_from_intent => search => +#gap_fill
```
**Operators used:** `WHILE/DO`, `gaps?`, `intent?`, auto-query generation

### PHASE 13: SECTION WRITING
```
foreach #dd_sections => write_section:[SECTION_ID]
```
**Operators used:** `foreach`, `write_section:`
**Returns:** Populated narrative paragraphs

### PHASE 14: VALIDATION
```
validate: :#document ##DD
```
**Operators used:** `validate:`
**Returns:** QC report, compliance status

---

## FULL ASSET TRACE OPERATOR CHAIN

### Prerequisites
- Subject: Person or Company name
- Jurisdiction: Starting point (may expand)

### PHASE 1: TEMPLATE LOAD
```
template:ASSET_TRACE:UK :#JohnSmith
```

### PHASE 2: SUBJECT IDENTIFICATION (Must verify first)
```
p: John Smith DOB:1975-03-15 => +#subject
verify? :#subject ##identity
```
**Returns:** Confirmed identity, aliases

### PHASE 3: DIRECTORSHIPS SEARCH (Foundation for assets)
```
puk: [SUBJECT] => +#directorships
```
**Returns:** All company directorships, company numbers

### PHASE 4: SHAREHOLDINGS (Parallel foreach)
```
foreach #directorships => cuk: [COMPANY] => c? @SHAREHOLDER => +#shareholdings
```
**Returns:** Ownership % in each company, share classes

### PHASE 5: REAL PROPERTY
```
{
    propuk: [SUBJECT_NAME],
    propuk: [EACH_COMPANY_NAME],
    Land Registry: [ADDRESS_HISTORY]
} => +#real_property
```
**Returns:** Title numbers, property values, charges/mortgages

### PHASE 6: VEHICLES/AIRCRAFT/VESSELS (Parallel)
```
{
    FAA: [SUBJECT], FAA: [COMPANIES],
    CAA: [SUBJECT], CAA: [COMPANIES],
    Lloyd's: [SUBJECT], Lloyd's: [COMPANIES]
} => +#vehicles
```
**Returns:** Registered vehicles, aircraft, yachts

### PHASE 7: INTELLECTUAL PROPERTY
```
{
    USPTO: [SUBJECT], USPTO: [COMPANIES],
    EPO: [SUBJECT], EPO: [COMPANIES],
    WIPO: [SUBJECT]
} => +#ip_assets
```
**Returns:** Patents, trademarks, copyrights

### PHASE 8: FINANCIAL INTERESTS (Limited - opaque)
```
bl? :#subject_domains ##financial => +#financial_signals
newsuk: "[SUBJECT] investment" => +#investment_mentions
```
**Returns:** Signals only (bank accounts not publicly accessible)

### PHASE 9: CONCEALMENT DETECTION
```
Gazette: [SUBJECT] ##transfer => +#transfers
newsuk: "[SUBJECT] trust" OR "asset protection" => +#concealment_signals
court?: [SUBJECT] ##freezing_order => +#legal_flags
```
**Returns:** Recent transfers, trust mentions, freezing orders

### PHASE 10: ASSET SUMMARY TABLE
```
aggregate: #real_property #shareholdings #vehicles #ip_assets => table_section:asset_summary
```
**Returns:** Formatted asset table with values

### PHASE 11: SUFFICIENCY & GAPS
```
sufficient? @template:ASSET_TRACE
gaps? => +#unfilled_slots
```

### PHASE 12: LOOP FOR GAPS
```
WHILE gaps? DO
    intent? :#next_gap => query_from_intent => execute => fill_slot
```

### PHASE 13: METHODOLOGY DOCUMENTATION
```
write_section:research_methodology :#trace_log
write_section:research_limitations :#unfilled_slots
```

---

## OPERATOR CHAIN SYNTAX RULES

| Pattern | Meaning | Example |
|---------|---------|---------|
| `{ a, b, c }` | Parallel execution | `{ cuk: X, puk: Y }` |
| `=> +#tag` | Tag results | `cuk: X => +#registry` |
| `@CLASS` | Filter by class | `@PERSON`, `@COMPANY` |
| `##dimension` | Filter by dimension | `##shareholder`, `##regulatory` |
| `:#tag` | Target tagged nodes | `p? :#officers` |
| `foreach #tag =>` | Loop over tagged | `foreach #officers => p:` |
| `IF cond THEN a ELSE b` | Conditional | `IF filled? THEN skip` |
| `WHILE cond DO` | Loop until | `WHILE NOT sufficient? DO` |
| `filled? :#section` | Check if slot filled | Binary: true/false |
| `sufficient?` | Check sufficiency | Returns score + gaps |
| `gaps?` | Get unfilled sections | Returns list |
| `intent? :#gap` | Get K-U quadrant | VERIFY/TRACE/EXTRACT/DISCOVER |
| `template:genre:jurisdiction` | Load template | `template:COMPANY_DD:UK` |
| `write_section:id` | Generate prose | `write_section:officers` |

---

## CASCADING WATCHER PATTERN

When template loads, watchers should auto-spawn:
```
template:COMPANY_DD:UK :#AcmeCorp
  └─ AUTO: +#w:section:corporate_overview
  └─ AUTO: +#w:section:officers =>spawn:#w:entity:[OFFICER_NAME]
  └─ AUTO: +#w:section:ownership =>spawn:#w:company:[SHAREHOLDER]
  └─ AUTO: +#w:section:litigation =>spawn:#w:event:lawsuit
  └─ AUTO: +#w:section:sanctions =>spawn:#w:topic:sanctions
```

When officer watcher finds "John Smith", it spawns:
```
+#w:entity:John_Smith =>section:officers
```

This cascade is the **missing piece** for full automation.

---

## EXAMPLE: HUNGARIAN COMPANY DD (End-to-End)

```
# 1. Load template (auto-creates watchers)
template:COMPANY_DD:HU :#SzaboKft

# 2. Registry lookup (parallel)
{ chu: Szabo Kft, reghu: Szabo Kft } => +#hu_registry

# 3. Extract officers
p? :#hu_registry @PERSON => +#officers

# 4. Officer enrichment (parallel foreach)
foreach #officers => { p: [NAME], phu: [NAME] } => +#officer_data

# 5. Ownership
c? :#hu_registry @SHAREHOLDER => +#shareholders

# 6. UBO trace (conditional)
IF NOT filled? :#section_ubo THEN
    foreach #shareholders WHERE @COMPANY => c: [NAME] :HU => +#ubo_chain

# 7. Regulatory (HU specific)
reghu: Szabo Kft ##NAV => +#tax_status
reghu: Szabo Kft ##MNB => +#financial_regulator

# 8. Litigation
lithu: Szabo Kft => +#litigation
Gazette: Szabo Kft :HU => +#gazette_mentions

# 9. Sanctions (EU focus)
{ OFAC: Szabo Kft, EU_sanctions: Szabo Kft, EU_sanctions: [OFFICERS] } => +#sanctions

# 10. Media (Hungarian + international)
{ newshu: "Szabo Kft", newsuk: "Szabo Kft" } => +#media

# 11. Loop until sufficient
WHILE NOT sufficient? :#template DO
    gaps? => intent? => query_for_intent => execute => +#gap_fill

# 12. Write all sections
foreach #dd_sections => write_section:[ID] :#filled_slots

# 13. Validate
validate: :#document => +#validation_report
```

---

## NEXT: See PROPOSED_OPERATORS.json for new operators needed
