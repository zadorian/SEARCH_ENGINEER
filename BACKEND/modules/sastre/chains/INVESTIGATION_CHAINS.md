# SASTRE INVESTIGATION CHAINS v1.0

## Philosophy: The Full Cycle

These chains embody the complete Abacus System:
- **Dual Engine**: Profile Mode (predictable enrichment) → Grid Mode (discovery)
- **K-U Matrix**: Every node (including NEXUS) has Known/Unknown state
- **Four Cognitive Modes**: Rotate through Narrative → Subject → Location → Nexus
- **Cross-Pollination**: Insights from one mode drive actions in another
- **Temporal Overlap**: Career chapters × Company events = hidden relevance
- **One-Step-Removed**: Mini-DDs on associates, past affiliations, historical periods

---

## SYNTAX GAPS IDENTIFIED

Before the chains, critical missing operators that need implementation:

| Gap | Proposed Syntax | Purpose | Priority |
|-----|-----------------|---------|----------|
| Sanctions check | `sanctions?` | Query sanctions lists | HIGH |
| PEP check | `pep?` | Politically Exposed Person | HIGH |
| Write to EDITH | `/write ##Section` | Target template section | HIGH |
| Flag section | `/flag ##Section` | Mark for review | MEDIUM |
| Temporal overlap | `overlap?` or `×t` | Career × Events detection | HIGH |
| Career extraction | `career?` | Extract employment history | HIGH |
| Event extraction | `events?` | Company events/scandals | HIGH |
| Associate extraction | `associates?` | People connected with roles | MEDIUM |
| Mini-DD spawn | `=>DD` or `/minidd` | Nested investigation | HIGH |
| NEXUS extraction | `@nexus?` or `@x?` | Relationships as nodes | HIGH |
| K-U state query | `KU?` | Check node completeness | MEDIUM |
| Period filter | `:YYYY-YYYY` | Temporal window | HIGH |
| Role filter | `##role:director` | Filter by relationship type | MEDIUM |
| Adverse media | `adverse?` | Negative news search | HIGH |
| Beneficial owner | `ubo?` | UBO chain traversal | HIGH |

---

## CHAIN 1: UK PERSON DEEP DD (Full Rotation)

**Scenario**: Full due diligence on UK individual with multiple companies, career history, 
associates, and one-step-removed investigations.

**Subject**: Person (UK)
**Goal**: Complete profile + hidden connections through temporal overlap

```
#═══════════════════════════════════════════════════════════════════════════════
# CHAIN: uk_person_deep_dd
# GENRE: due_diligence
# JURISDICTION: UK
# ENTITY_TYPE: person
# DEPTH: comprehensive
#═══════════════════════════════════════════════════════════════════════════════

#───────────────────────────────────────────────────────────────────────────────
# PHASE 1: ANCHOR (Profile Mode - Predictable Enrichment)
# K-U State: Subject=Known, Location=Known → VERIFY/ENRICH
#───────────────────────────────────────────────────────────────────────────────

# 1.1 Tag the subject
p: {PERSON_NAME} => +#SUBJECT

# 1.2 Core registry lookup - Companies House officers
:#SUBJECT :cruk! => +#CH_DATA

# 1.3 Extract current directorships
@c? :#CH_DATA => +#CURRENT_COMPANIES

# 1.4 Extract ALL officer appointments (current + resigned)
@nexus? :#CH_DATA ##role:officer => +#ALL_APPOINTMENTS
# GAP: @nexus? not implemented - need to extract relationship nodes

# 1.5 FCA regulatory check
:#SUBJECT :reguk! => +#FCA_DATA

# 1.6 Litigation check
:#SUBJECT :lituk! => +#LITIGATION

#───────────────────────────────────────────────────────────────────────────────
# PHASE 2: CAREER CHAPTERS (Temporal K-U Mapping)
# Extract tenure periods → each becomes a temporal filter
#───────────────────────────────────────────────────────────────────────────────

# 2.1 Extract career timeline from appointments
career? :#ALL_APPOINTMENTS => +#CAREER_CHAPTERS
# GAP: career? not implemented - should return [{company, role, start, end}]

# 2.2 For each career chapter, create a temporal slot
/gridX{:#CAREER_CHAPTERS} => +#TENURE_PERIODS
# Each #TENURE_PERIOD has: company_id, start_date, end_date, role

#───────────────────────────────────────────────────────────────────────────────
# PHASE 3: TEMPORAL OVERLAP DETECTION (The Hidden Value)
# Match career periods with company events/scandals
#───────────────────────────────────────────────────────────────────────────────

# 3.1 For each company in career, fetch events during tenure
/gridS{:#CURRENT_COMPANIES} => events? :TENURE_PERIOD => +#COMPANY_EVENTS
# GAP: events? not implemented - should return scandals, lawsuits, regulatory actions

# 3.2 Detect overlaps: Was subject at company during adverse event?
overlap? :#CAREER_CHAPTERS :#COMPANY_EVENTS => +#TEMPORAL_OVERLAPS
# GAP: overlap? not implemented - temporal intersection detection

# 3.3 Any overlap = investigation flag
IF filled? :#TEMPORAL_OVERLAPS THEN +#ADVERSE_FLAG

#───────────────────────────────────────────────────────────────────────────────
# PHASE 4: ASSOCIATE NETWORK (Grid Mode - Discovery)
# K-U State: Subject=Known, Location=Unknown → TRACE
#───────────────────────────────────────────────────────────────────────────────

# 4.1 Extract co-directors from current companies
/gridS{:#CURRENT_COMPANIES} => @p? ##role:officer => +#CO_OFFICERS
# GAP: ##role filter not implemented

# 4.2 Extract shareholders from current companies
/gridS{:#CURRENT_COMPANIES} => @p? ##role:shareholder => +#CO_SHAREHOLDERS

# 4.3 Combine into associate pool
:#CO_OFFICERS :#CO_SHAREHOLDERS => +#ASSOCIATES

# 4.4 Deduplicate and exclude subject
/gridS{:#ASSOCIATES} => EXCLUDE :#SUBJECT => +#UNIQUE_ASSOCIATES

# 4.5 Intersection: which associates appear in multiple companies?
/clink :#UNIQUE_ASSOCIATES => +#NETWORK_OVERLAPS
# Returns: pairs that co-occur across companies = potential network

#───────────────────────────────────────────────────────────────────────────────
# PHASE 5: ONE-STEP-REMOVED DDs (Mini-Investigations)
# Each key associate gets lightweight DD
#───────────────────────────────────────────────────────────────────────────────

# 5.1 Tag top associates for mini-DD
/gridS{:#NETWORK_OVERLAPS} => TOP(5) => +#KEY_ASSOCIATES

# 5.2 Mini-DD on each key associate
/gridS{:#KEY_ASSOCIATES} => FOREACH {
    p: $ITEM :cruk! => +#ASSOC_CH_$INDEX
    sanctions? :$ITEM => +#ASSOC_SANCTIONS_$INDEX
    pep? :$ITEM => +#ASSOC_PEP_$INDEX
    adverse? :$ITEM => +#ASSOC_ADVERSE_$INDEX
} => +#ASSOCIATE_DDS
# GAP: FOREACH not implemented, sanctions?, pep?, adverse? not confirmed

# 5.3 Any adverse findings on associates = escalate
IF filled? :#ASSOC_SANCTIONS_* OR filled? :#ASSOC_PEP_* THEN +#NETWORK_ADVERSE

#───────────────────────────────────────────────────────────────────────────────
# PHASE 6: HISTORICAL AFFILIATIONS (Temporal Discovery)
# Past companies also get mini-DD for their RELEVANT PERIOD
#───────────────────────────────────────────────────────────────────────────────

# 6.1 Extract resigned positions
/gridX{:#ALL_APPOINTMENTS ##status:resigned} => +#PAST_AFFILIATIONS

# 6.2 For each past affiliation, check company during tenure
/gridS{:#PAST_AFFILIATIONS} => FOREACH {
    # Get company status AT TIME of involvement
    c: $COMPANY :cruk! :$START-$END => +#PAST_CO_DATA_$INDEX
    # GAP: temporal filter :YYYY-YYYY not implemented
    
    # What happened to this company AFTER subject left?
    events? :$COMPANY :$END-NOW => +#POST_DEPARTURE_$INDEX
    
    # Did company fail/scandal after they left? Pattern detection
    IF #bankruptcy OR #fraud IN :#POST_DEPARTURE_$INDEX THEN +#SUSPICIOUS_EXIT
}

#───────────────────────────────────────────────────────────────────────────────
# PHASE 7: SANCTIONS & PEP (Compliance Layer)
#───────────────────────────────────────────────────────────────────────────────

# 7.1 Direct sanctions check
sanctions? :#SUBJECT => +#SANCTIONS_DIRECT

# 7.2 Direct PEP check  
pep? :#SUBJECT => +#PEP_DIRECT

# 7.3 Sanctions on current companies
/gridS{:#CURRENT_COMPANIES} => sanctions? => +#COMPANY_SANCTIONS

# 7.4 Sanctions on associates (already done in 5.2)

#───────────────────────────────────────────────────────────────────────────────
# PHASE 8: DIGITAL FOOTPRINT (Link Analysis)
# K-U State: Subject=Known, Location=Unknown → TRACE via web
#───────────────────────────────────────────────────────────────────────────────

# 8.1 Find domains associated with subject
cdom? :#SUBJECT => +#SUBJECT_DOMAINS
# cdom? = company domain finder (macro operator)

# 8.2 Add company domains
/gridS{:#CURRENT_COMPANIES} => cdom? => +#COMPANY_DOMAINS

# 8.3 All domains combined
:#SUBJECT_DOMAINS :#COMPANY_DOMAINS => +#ALL_DOMAINS

# 8.4 Backlink analysis on all domains
bl? :!:#ALL_DOMAINS => @ent? => +#BACKLINK_ENTITIES

# 8.5 Who links to them? Extract and check for adverse sources
/gridL{:#BACKLINK_ENTITIES} => IF @news THEN +#MEDIA_MENTIONS

# 8.6 Adverse media check
adverse? :#SUBJECT => +#ADVERSE_MEDIA
# GAP: adverse? not implemented

#───────────────────────────────────────────────────────────────────────────────
# PHASE 9: NEXUS K-U ASSESSMENT (Relationship Completeness)
# Treat each NEXUS (relationship) as a node with its own slots
#───────────────────────────────────────────────────────────────────────────────

# 9.1 Rotate to NEXUS view
/gridX{:#SUBJECT x [?]} => +#ALL_RELATIONSHIPS

# 9.2 Check K-U state of each relationship
/gridX{:#ALL_RELATIONSHIPS} => KU? => +#NEXUS_KU_STATE
# GAP: KU? not implemented - should return {filled_slots, empty_slots, state}

# 9.3 Identify hungry relationship slots
/gridX{:#NEXUS_KU_STATE ##state:hungry} => +#RELATIONSHIP_GAPS

# Example hungry slots on NEXUS:
# - officer_of: appointment_date=FILLED, resignation_date=EMPTY (still there?)
# - shareholder_of: percentage=EMPTY (how much do they own?)
# - beneficial_owner_of: verified=EMPTY (is this confirmed?)

# 9.4 Fill hungry NEXUS slots
/gridX{:#RELATIONSHIP_GAPS} => FOREACH {
    IF ##slot:percentage THEN :cruk! ##PSC
    IF ##slot:appointment_date THEN :cruk! ##appointments
    IF ##slot:resignation_date THEN :cruk! ##resignations
}

#───────────────────────────────────────────────────────────────────────────────
# PHASE 10: CROSS-POLLINATION CHECK (Mode Rotation)
# Insights from each mode drive actions in others
#───────────────────────────────────────────────────────────────────────────────

# 10.1 NARRATIVE → SUBJECT: Do we have enough to answer the brief?
/gridN{##template:uk_person_dd} => gaps? => +#NARRATIVE_GAPS
# GAP: gaps? not implemented - should check empty template sections

# 10.2 SUBJECT → LOCATION: Profile shows Cyprus connection → check Cyprus registry
IF "Cyprus" IN :#CH_DATA THEN {
    /gridS{:#CURRENT_COMPANIES ##jurisdiction:CY} => :ccy! => +#CYPRUS_DATA
}

# 10.3 LOCATION → NEXUS: Checked FCA → but no litigation edge extracted
IF filled? :#FCA_DATA AND NOT filled? :#LITIGATION THEN {
    :#SUBJECT :lituk! => +#LITIGATION_FOLLOWUP
}

# 10.4 NEXUS → NARRATIVE: Found network overlap → triggers new question
IF filled? :#NETWORK_OVERLAPS THEN {
    /write ##Associates "Network analysis reveals frequent co-occurrence with: {list}"
    +#watcher[Associate Network Changes]
}

#───────────────────────────────────────────────────────────────────────────────
# PHASE 11: DOCUMENT GENERATION (Write to EDITH)
#───────────────────────────────────────────────────────────────────────────────

# 11.1 Write to template sections
/write ##Executive_Summary :#SUBJECT_SUMMARY
/write ##Corporate_Affiliations :#CURRENT_COMPANIES :#PAST_AFFILIATIONS
/write ##Regulatory_Status :#FCA_DATA :#SANCTIONS_DIRECT :#PEP_DIRECT
/write ##Litigation_History :#LITIGATION
/write ##Associate_Network :#UNIQUE_ASSOCIATES :#NETWORK_OVERLAPS
/write ##Adverse_Media :#ADVERSE_MEDIA :#MEDIA_MENTIONS
/write ##Temporal_Analysis :#CAREER_CHAPTERS :#TEMPORAL_OVERLAPS
/write ##Risk_Flags :#ADVERSE_FLAG :#NETWORK_ADVERSE :#SUSPICIOUS_EXIT
# GAP: /write ##Section not implemented

# 11.2 Flag sections with adverse findings
IF filled? :#ADVERSE_FLAG THEN /flag ##Temporal_Analysis
IF filled? :#NETWORK_ADVERSE THEN /flag ##Associate_Network
IF filled? :#SUSPICIOUS_EXIT THEN /flag ##Corporate_Affiliations
# GAP: /flag ##Section not implemented

# 11.3 Set watchers for ongoing monitoring
+#watcher[New Company Filings] :#SUBJECT
+#watcher[Sanctions List Updates] :#SUBJECT :#CURRENT_COMPANIES
+#watcher[Litigation Mentions] :#SUBJECT

#═══════════════════════════════════════════════════════════════════════════════
# END CHAIN: uk_person_deep_dd
#═══════════════════════════════════════════════════════════════════════════════
```

---

## CHAIN 2: UK COMPANY DD (Full Corporate Intelligence)

**Scenario**: Deep dive on UK company including officers, shareholders, UBO chain,
related companies, and temporal event analysis.

```
#═══════════════════════════════════════════════════════════════════════════════
# CHAIN: uk_company_dd
# GENRE: due_diligence
# JURISDICTION: UK
# ENTITY_TYPE: company
# DEPTH: comprehensive
#═══════════════════════════════════════════════════════════════════════════════

#───────────────────────────────────────────────────────────────────────────────
# PHASE 1: ANCHOR (Profile Mode)
#───────────────────────────────────────────────────────────────────────────────

# 1.1 Tag subject
c: {COMPANY_NAME} => +#SUBJECT

# 1.2 Full UK company sources
:#SUBJECT :cuk! => +#COMPANY_DATA

# 1.3 Registry-only for official record
:#SUBJECT :cruk! => +#CH_OFFICIAL

# 1.4 Extract core attributes
@c? :#COMPANY_DATA => +#COMPANY_PROFILE
# Slots: name, number, status, incorporation_date, address, SIC codes

#───────────────────────────────────────────────────────────────────────────────
# PHASE 2: OFFICER EXTRACTION (Subject K-U)
#───────────────────────────────────────────────────────────────────────────────

# 2.1 Current officers
@p? :#CH_OFFICIAL ##role:officer ##status:active => +#CURRENT_OFFICERS

# 2.2 Historical officers
@p? :#CH_OFFICIAL ##role:officer ##status:resigned => +#FORMER_OFFICERS

# 2.3 For each current officer, enrich
/gridS{:#CURRENT_OFFICERS} => FOREACH {
    p: $ITEM :cruk! => +#OFFICER_PROFILE_$INDEX
    sanctions? :$ITEM => +#OFFICER_SANCTIONS_$INDEX
    pep? :$ITEM => +#OFFICER_PEP_$INDEX
}

# 2.4 Officer network: where else do these officers appear?
/gridS{:#CURRENT_OFFICERS} => :cruk! => @c? => +#OFFICER_OTHER_COMPANIES

# 2.5 Common directorships (red flag for nominee networks)
/clink :#CURRENT_OFFICERS => +#OFFICER_OVERLAPS
IF COUNT(:#OFFICER_OVERLAPS) > 3 THEN +#NOMINEE_FLAG

#───────────────────────────────────────────────────────────────────────────────
# PHASE 3: OWNERSHIP CHAIN (UBO Traversal)
#───────────────────────────────────────────────────────────────────────────────

# 3.1 Direct shareholders (PSC data)
@p? :#CH_OFFICIAL ##role:shareholder => +#DIRECT_SHAREHOLDERS_P
@c? :#CH_OFFICIAL ##role:shareholder => +#DIRECT_SHAREHOLDERS_C

# 3.2 Corporate shareholders need further lookup
/gridS{:#DIRECT_SHAREHOLDERS_C} => FOREACH {
    # Each corporate shareholder gets its own mini-DD
    c: $ITEM :cruk! => +#CORP_SHAREHOLDER_$INDEX
    @p? :#CORP_SHAREHOLDER_$INDEX ##role:shareholder => +#LAYER2_SHAREHOLDERS_$INDEX
    @c? :#CORP_SHAREHOLDER_$INDEX ##role:shareholder => +#LAYER2_CORPS_$INDEX
}

# 3.3 Recursion: if Layer 2 has corporate shareholders, continue
/gridS{:#LAYER2_CORPS_*} => FOREACH {
    c: $ITEM :cruk! => +#LAYER3_$INDEX
    # Continue until natural person or max depth
}
# GAP: Recursive UBO traversal needs implementation (ubo? operator)

# 3.4 Alternative: UBO operator (if implemented)
ubo? :#SUBJECT => +#UBO_CHAIN
# GAP: ubo? not implemented - should traverse ownership to natural persons

# 3.5 Check all UBOs
/gridS{:#UBO_CHAIN ##type:person} => FOREACH {
    sanctions? :$ITEM => +#UBO_SANCTIONS_$INDEX
    pep? :$ITEM => +#UBO_PEP_$INDEX
}

#───────────────────────────────────────────────────────────────────────────────
# PHASE 4: RELATED COMPANIES (Discovery Mode)
#───────────────────────────────────────────────────────────────────────────────

# 4.1 Companies at same address
/gridS{:#COMPANY_PROFILE ##slot:address} => :cruk! ##same_address => +#SAME_ADDRESS_COMPANIES

# 4.2 Companies with same officers
/gridS{:#CURRENT_OFFICERS} => @c? => EXCLUDE :#SUBJECT => +#SAME_OFFICER_COMPANIES

# 4.3 Companies with same shareholders
/gridS{:#DIRECT_SHAREHOLDERS_P} => @c? => EXCLUDE :#SUBJECT => +#SAME_SHAREHOLDER_COMPANIES

# 4.4 Combine into related company pool
:#SAME_ADDRESS_COMPANIES :#SAME_OFFICER_COMPANIES :#SAME_SHAREHOLDER_COMPANIES => +#RELATED_COMPANIES

# 4.5 Dedupe and count overlaps
/clink :#RELATED_COMPANIES => +#COMPANY_NETWORK

#───────────────────────────────────────────────────────────────────────────────
# PHASE 5: REGULATORY STATUS (Location K-U)
#───────────────────────────────────────────────────────────────────────────────

# 5.1 FCA Register
:#SUBJECT :reguk! => +#FCA_STATUS

# 5.2 Litigation
:#SUBJECT :lituk! => +#LITIGATION

# 5.3 Gazette notices (winding up, striking off)
:#SUBJECT gazette! => +#GAZETTE_NOTICES
# GAP: gazette! not confirmed

# 5.4 Insolvency register
:#SUBJECT insolvency! => +#INSOLVENCY_STATUS
# GAP: insolvency! not confirmed

#───────────────────────────────────────────────────────────────────────────────
# PHASE 6: SANCTIONS & ADVERSE
#───────────────────────────────────────────────────────────────────────────────

# 6.1 Direct sanctions
sanctions? :#SUBJECT => +#SANCTIONS_COMPANY

# 6.2 Adverse media
adverse? :#SUBJECT => +#ADVERSE_COMPANY

# 6.3 Sanctions on UBOs (from Phase 3)
# Already captured in #UBO_SANCTIONS_*

# 6.4 Aggregate adverse flags
IF filled? :#SANCTIONS_COMPANY OR filled? :#UBO_SANCTIONS_* THEN +#SANCTIONS_FLAG
IF filled? :#ADVERSE_COMPANY THEN +#ADVERSE_FLAG

#───────────────────────────────────────────────────────────────────────────────
# PHASE 7: DIGITAL & DOMAIN
#───────────────────────────────────────────────────────────────────────────────

# 7.1 Find company domain
cdom? :#SUBJECT => +#COMPANY_DOMAIN

# 7.2 Full domain analysis
alldom? :#COMPANY_DOMAIN => +#DOMAIN_ANALYSIS

# 7.3 WHOIS history
whois? :#COMPANY_DOMAIN => +#WHOIS_DATA

# 7.4 Backlink analysis
bl? :!:#COMPANY_DOMAIN => @ent? => +#BACKLINK_ENTITIES

# 7.5 Technology stack (reveals sophistication)
tech? :#COMPANY_DOMAIN => +#TECH_STACK
# GAP: tech? needs confirmation

#───────────────────────────────────────────────────────────────────────────────
# PHASE 8: NEXUS K-U STATE (Relationship Completeness)
#───────────────────────────────────────────────────────────────────────────────

# 8.1 All relationships involving subject
/gridX{:#SUBJECT x [?]} => +#ALL_RELATIONSHIPS

# 8.2 K-U assessment on each
/gridX{:#ALL_RELATIONSHIPS} => KU? => +#NEXUS_KU

# 8.3 Expected relationships that are VOID (suspicious absence)
# A company SHOULD have: officers, shareholders, registered address
/gridX{:#SUBJECT} => expect? ##officer ##shareholder ##address => +#EXPECTED_NEXUS
IF NOT filled? :#EXPECTED_NEXUS ##officer THEN +#NO_OFFICER_FLAG
IF NOT filled? :#EXPECTED_NEXUS ##shareholder THEN +#NO_SHAREHOLDER_FLAG
# GAP: expect? not implemented - should check for expected relationship types

#───────────────────────────────────────────────────────────────────────────────
# PHASE 9: INDUSTRY CONTEXT (Theme × Entity)
#───────────────────────────────────────────────────────────────────────────────

# 9.1 Determine industry from SIC codes
/gridS{:#COMPANY_PROFILE ##slot:sic} => industry? => +#INDUSTRY

# 9.2 Industry-specific checks
IF "financial" IN :#INDUSTRY THEN {
    :#SUBJECT :reguk! ##FCA_permissions => +#FCA_PERMISSIONS
    IF NOT filled? :#FCA_PERMISSIONS THEN +#UNREGULATED_FINANCE_FLAG
}

IF "property" IN :#INDUSTRY THEN {
    :#SUBJECT land_registry! => +#PROPERTY_HOLDINGS
    # GAP: land_registry! not confirmed
}

IF "crypto" IN :#INDUSTRY OR "blockchain" IN :#INDUSTRY THEN {
    :#SUBJECT :reguk! ##FCA_crypto => +#CRYPTO_REGISTRATION
    IF NOT filled? :#CRYPTO_REGISTRATION THEN +#UNREGISTERED_CRYPTO_FLAG
}

#───────────────────────────────────────────────────────────────────────────────
# PHASE 10: DOCUMENT GENERATION
#───────────────────────────────────────────────────────────────────────────────

/write ##Company_Profile :#COMPANY_PROFILE
/write ##Officers :#CURRENT_OFFICERS :#OFFICER_PROFILES_*
/write ##Ownership :#DIRECT_SHAREHOLDERS_P :#DIRECT_SHAREHOLDERS_C :#UBO_CHAIN
/write ##Related_Companies :#RELATED_COMPANIES :#COMPANY_NETWORK
/write ##Regulatory :#FCA_STATUS :#LITIGATION :#INSOLVENCY_STATUS
/write ##Sanctions_PEP :#SANCTIONS_COMPANY :#UBO_SANCTIONS_* :#UBO_PEP_*
/write ##Digital_Footprint :#DOMAIN_ANALYSIS :#BACKLINK_ENTITIES
/write ##Risk_Assessment :#SANCTIONS_FLAG :#ADVERSE_FLAG :#NOMINEE_FLAG

# Set watchers
+#watcher[Company Status Changes] :#SUBJECT
+#watcher[New Officers Appointed] :#SUBJECT
+#watcher[Ownership Changes] :#SUBJECT
+#watcher[Sanctions Updates] :#SUBJECT :#UBO_CHAIN

#═══════════════════════════════════════════════════════════════════════════════
# END CHAIN: uk_company_dd
#═══════════════════════════════════════════════════════════════════════════════
```

---

## CHAIN 3: ASSET TRACE (Follow the Money)

**Scenario**: Trace assets of a subject across jurisdictions, property, companies, domains.

```
#═══════════════════════════════════════════════════════════════════════════════
# CHAIN: asset_trace
# GENRE: asset_trace
# JURISDICTION: multi
# ENTITY_TYPE: person OR company
# DEPTH: comprehensive
#═══════════════════════════════════════════════════════════════════════════════

#───────────────────────────────────────────────────────────────────────────────
# PHASE 1: IDENTIFY ASSET CLASSES
#───────────────────────────────────────────────────────────────────────────────

# 1.1 Tag subject
{ENTITY} => +#SUBJECT

# 1.2 Determine entity type
IF @person :#SUBJECT THEN +#IS_PERSON
IF @company :#SUBJECT THEN +#IS_COMPANY

#───────────────────────────────────────────────────────────────────────────────
# PHASE 2: CORPORATE ASSETS (Companies owned/controlled)
#───────────────────────────────────────────────────────────────────────────────

# 2.1 If person: find their companies
IF #IS_PERSON THEN {
    p: :#SUBJECT :cruk! => @c? => +#UK_COMPANIES
    p: :#SUBJECT :cde! => @c? => +#DE_COMPANIES
    p: :#SUBJECT :ccy! => @c? => +#CY_COMPANIES
    # GAP: Need :ccy! for Cyprus
    
    # OpenCorporates global search
    p: :#SUBJECT opencorp! => @c? => +#GLOBAL_COMPANIES
    # GAP: opencorp! global company search not confirmed
}

# 2.2 If company: find subsidiaries and related entities
IF #IS_COMPANY THEN {
    c: :#SUBJECT :cruk! => @c? ##role:subsidiary => +#SUBSIDIARIES
    c: :#SUBJECT :cruk! => @c? ##role:parent => +#PARENT_COMPANIES
}

# 2.3 Combine all corporate assets
:#UK_COMPANIES :#DE_COMPANIES :#CY_COMPANIES :#GLOBAL_COMPANIES => +#ALL_CORPORATE_ASSETS

#───────────────────────────────────────────────────────────────────────────────
# PHASE 3: PROPERTY ASSETS (Real Estate)
#───────────────────────────────────────────────────────────────────────────────

# 3.1 UK Land Registry
:#SUBJECT :land_uk! => +#UK_PROPERTY
# GAP: :land_uk! not implemented

# 3.2 Overseas property (if known jurisdictions)
IF filled? :#CY_COMPANIES THEN {
    :#SUBJECT :land_cy! => +#CY_PROPERTY
}

# 3.3 Property via corporate holdings
/gridS{:#ALL_CORPORATE_ASSETS} => FOREACH {
    c: $ITEM :land_uk! => +#CORP_PROPERTY_$INDEX
}

# 3.4 Combine property assets
:#UK_PROPERTY :#CY_PROPERTY :#CORP_PROPERTY_* => +#ALL_PROPERTY_ASSETS

#───────────────────────────────────────────────────────────────────────────────
# PHASE 4: DIGITAL ASSETS (Domains)
#───────────────────────────────────────────────────────────────────────────────

# 4.1 Domains owned by subject
whois? :#SUBJECT => +#DIRECT_DOMAINS

# 4.2 Domains owned by companies
/gridS{:#ALL_CORPORATE_ASSETS} => whois? => +#CORPORATE_DOMAINS

# 4.3 Reverse WHOIS (other domains by same registrant)
/gridL{:#DIRECT_DOMAINS} => reverse_whois? => +#REVERSE_WHOIS_DOMAINS
# GAP: reverse_whois? not confirmed

# 4.4 Combine digital assets
:#DIRECT_DOMAINS :#CORPORATE_DOMAINS :#REVERSE_WHOIS_DOMAINS => +#ALL_DOMAIN_ASSETS

#───────────────────────────────────────────────────────────────────────────────
# PHASE 5: VEHICLE ASSETS (Yachts, Aircraft, Vehicles)
#───────────────────────────────────────────────────────────────────────────────

# 5.1 UK vehicle registry (DVLA - limited public access)
# Note: Most vehicle registries not publicly searchable

# 5.2 Aircraft registry
:#SUBJECT aircraft_registry! => +#AIRCRAFT
# GAP: aircraft_registry! not implemented (CAA, FAA)

# 5.3 Yacht registry
:#SUBJECT yacht_registry! => +#YACHTS
# GAP: yacht_registry! not implemented

# 5.4 Via corporate holdings
/gridS{:#ALL_CORPORATE_ASSETS} => aircraft_registry! => +#CORP_AIRCRAFT
/gridS{:#ALL_CORPORATE_ASSETS} => yacht_registry! => +#CORP_YACHTS

#───────────────────────────────────────────────────────────────────────────────
# PHASE 6: OFFSHORE DISCOVERY (Grid Mode)
#───────────────────────────────────────────────────────────────────────────────

# 6.1 Leaked databases
:#SUBJECT leaks! => +#LEAK_HITS
# leaks! = Panama Papers, Pandora Papers, Paradise Papers, etc.

# 6.2 If leak hits, extract entities
@ent? :#LEAK_HITS => +#LEAK_ENTITIES

# 6.3 Offshore jurisdictions to check
/gridS{:#LEAK_ENTITIES ##jurisdiction:offshore} => +#OFFSHORE_ENTITIES

# 6.4 Offshore company lookups
/gridS{:#OFFSHORE_ENTITIES} => FOREACH {
    IF ##jurisdiction:BVI THEN c: $ITEM :cbvi! => +#BVI_DATA_$INDEX
    IF ##jurisdiction:Cayman THEN c: $ITEM :cky! => +#CAYMAN_DATA_$INDEX
    IF ##jurisdiction:Panama THEN c: $ITEM :cpa! => +#PANAMA_DATA_$INDEX
}
# GAP: :cbvi!, :cky!, :cpa! offshore registry operators not implemented

#───────────────────────────────────────────────────────────────────────────────
# PHASE 7: NEXUS ASSET MAPPING (Ownership K-U)
#───────────────────────────────────────────────────────────────────────────────

# 7.1 All ownership relationships
/gridX{:#SUBJECT x [?] ##role:owner OR ##role:shareholder OR ##role:beneficial_owner} => +#OWNERSHIP_NEXUS

# 7.2 K-U state of ownership
/gridX{:#OWNERSHIP_NEXUS} => KU? => +#OWNERSHIP_KU

# 7.3 Hungry slots in ownership (missing percentages, missing verification)
/gridX{:#OWNERSHIP_KU ##state:hungry} => +#OWNERSHIP_GAPS

# 7.4 Fill ownership gaps
/gridX{:#OWNERSHIP_GAPS} => FOREACH {
    IF ##slot:percentage THEN :cruk! ##PSC => +#FILLED_PERCENTAGE_$INDEX
    IF ##slot:acquisition_date THEN :cruk! ##filings => +#FILLED_DATE_$INDEX
}

#───────────────────────────────────────────────────────────────────────────────
# PHASE 8: ASSET TIMELINE (Temporal K-U)
#───────────────────────────────────────────────────────────────────────────────

# 8.1 Build acquisition timeline
/gridX{:#OWNERSHIP_NEXUS ##slot:acquisition_date} => timeline? => +#ASSET_TIMELINE
# GAP: timeline? operator for building chronological view

# 8.2 Detect rapid acquisition patterns
/gridN{:#ASSET_TIMELINE} => pattern? ##rapid_acquisition => +#RAPID_ACQUISITION
# GAP: pattern? for temporal pattern detection

# 8.3 Detect pre-sanction movements
IF filled? :#SANCTIONS_SUBJECT THEN {
    /gridN{:#ASSET_TIMELINE} => filter? :BEFORE :#SANCTIONS_DATE => +#PRE_SANCTION_MOVES
}

#───────────────────────────────────────────────────────────────────────────────
# PHASE 9: DOCUMENT GENERATION
#───────────────────────────────────────────────────────────────────────────────

/write ##Asset_Summary "Total corporate: {COUNT :#ALL_CORPORATE_ASSETS}, Property: {COUNT :#ALL_PROPERTY_ASSETS}, Domains: {COUNT :#ALL_DOMAIN_ASSETS}"
/write ##Corporate_Holdings :#ALL_CORPORATE_ASSETS
/write ##Property_Holdings :#ALL_PROPERTY_ASSETS
/write ##Domain_Holdings :#ALL_DOMAIN_ASSETS
/write ##Vehicle_Holdings :#AIRCRAFT :#YACHTS :#CORP_AIRCRAFT :#CORP_YACHTS
/write ##Offshore_Entities :#OFFSHORE_ENTITIES :#LEAK_ENTITIES
/write ##Ownership_Structure :#OWNERSHIP_NEXUS
/write ##Asset_Timeline :#ASSET_TIMELINE
/write ##Red_Flags :#RAPID_ACQUISITION :#PRE_SANCTION_MOVES

#═══════════════════════════════════════════════════════════════════════════════
# END CHAIN: asset_trace
#═══════════════════════════════════════════════════════════════════════════════
```

---

## CHAIN 4: NETWORK ANALYSIS (Multi-Entity Investigation)

**Scenario**: Investigate connections between multiple entities, find hidden links.

```
#═══════════════════════════════════════════════════════════════════════════════
# CHAIN: network_analysis
# GENRE: corporate_intelligence
# JURISDICTION: multi
# ENTITY_TYPE: mixed
# DEPTH: comprehensive
#═══════════════════════════════════════════════════════════════════════════════

#───────────────────────────────────────────────────────────────────────────────
# PHASE 1: SEED ENTITIES
#───────────────────────────────────────────────────────────────────────────────

# Multiple subjects can be tagged
{ENTITY_1} => +#SEED_1
{ENTITY_2} => +#SEED_2
{ENTITY_3} => +#SEED_3
:#SEED_1 :#SEED_2 :#SEED_3 => +#SEEDS

#───────────────────────────────────────────────────────────────────────────────
# PHASE 2: EXPAND EACH SEED (Layer 1)
#───────────────────────────────────────────────────────────────────────────────

/gridS{:#SEEDS} => FOREACH {
    # Determine type and enrich accordingly
    IF @person $ITEM THEN {
        p: $ITEM :cruk! => @c? => +#LAYER1_COMPANIES_$INDEX
        p: $ITEM :cruk! => @p? ##co-director => +#LAYER1_ASSOCIATES_$INDEX
    }
    IF @company $ITEM THEN {
        c: $ITEM :cruk! => @p? => +#LAYER1_PEOPLE_$INDEX
        c: $ITEM :cruk! => @c? ##same_address => +#LAYER1_RELATED_$INDEX
    }
}

# Combine Layer 1
:#LAYER1_COMPANIES_* :#LAYER1_PEOPLE_* :#LAYER1_ASSOCIATES_* :#LAYER1_RELATED_* => +#LAYER1

#───────────────────────────────────────────────────────────────────────────────
# PHASE 3: INTERSECTION ANALYSIS (Find Overlaps)
#───────────────────────────────────────────────────────────────────────────────

# 3.1 Pairwise comparison of seeds
/clink :#SEEDS => +#SEED_OVERLAPS

# 3.2 Layer 1 intersection (what entities appear for multiple seeds?)
/gridS{:#LAYER1} => intersect? :#SEEDS => +#COMMON_ENTITIES
# GAP: intersect? with multiple reference tags

# 3.3 Common entities are high-value - tag them
/gridS{:#COMMON_ENTITIES} => +#NETWORK_HUBS

#───────────────────────────────────────────────────────────────────────────────
# PHASE 4: EXPAND HUBS (Layer 2)
#───────────────────────────────────────────────────────────────────────────────

/gridS{:#NETWORK_HUBS} => FOREACH {
    IF @person $ITEM THEN {
        p: $ITEM :cruk! => @c? => +#LAYER2_COMPANIES_$INDEX
    }
    IF @company $ITEM THEN {
        c: $ITEM :cruk! => @p? => +#LAYER2_PEOPLE_$INDEX
    }
}

:#LAYER2_COMPANIES_* :#LAYER2_PEOPLE_* => +#LAYER2

#───────────────────────────────────────────────────────────────────────────────
# PHASE 5: NEXUS ANALYSIS (Relationship K-U)
#───────────────────────────────────────────────────────────────────────────────

# 5.1 All edges between seeds
/gridX{:#SEED_1 x :#SEED_2} => +#NEXUS_1_2
/gridX{:#SEED_1 x :#SEED_3} => +#NEXUS_1_3
/gridX{:#SEED_2 x :#SEED_3} => +#NEXUS_2_3

# 5.2 Direct vs indirect connections
IF filled? :#NEXUS_1_2 THEN +#DIRECT_CONNECTION_1_2
IF NOT filled? :#NEXUS_1_2 AND filled? :#COMMON_ENTITIES THEN +#INDIRECT_CONNECTION_1_2

# 5.3 Path finding: what connects them?
/gridX{:#SEED_1 x :#SEED_2} => path? => +#PATH_1_2
# GAP: path? for finding connection path between two entities

# 5.4 K-U on all discovered nexuses
/gridX{:#NEXUS_1_2 :#NEXUS_1_3 :#NEXUS_2_3} => KU? => +#NEXUS_KU

#───────────────────────────────────────────────────────────────────────────────
# PHASE 6: TEMPORAL CORRELATION
#───────────────────────────────────────────────────────────────────────────────

# 6.1 When did entities interact?
/gridX{:#NEXUS_1_2} => @date? => +#INTERACTION_DATES_1_2
# GAP: @date? for extracting dates from relationships

# 6.2 Temporal clustering: did interactions spike at certain times?
/gridN{:#INTERACTION_DATES_*} => cluster? => +#TEMPORAL_CLUSTERS
# GAP: cluster? for temporal clustering

# 6.3 Cross-reference with events
events? :#SEEDS :#TEMPORAL_CLUSTERS => +#CORRELATED_EVENTS

#───────────────────────────────────────────────────────────────────────────────
# PHASE 7: HIDDEN LINK DISCOVERY (Discovery Mode)
#───────────────────────────────────────────────────────────────────────────────

# 7.1 Domain cross-linking
/gridS{:#SEEDS} => cdom? => +#SEED_DOMAINS
bl? :!:#SEED_DOMAINS => @ent? => +#BACKLINK_ENTITIES

# 7.2 Do backlink entities connect seeds?
/gridS{:#BACKLINK_ENTITIES} => intersect? :#SEEDS => +#HIDDEN_CONNECTORS

# 7.3 Leaked data connections
:#SEEDS leaks! => +#LEAK_CONNECTIONS

#───────────────────────────────────────────────────────────────────────────────
# PHASE 8: DOCUMENT GENERATION
#───────────────────────────────────────────────────────────────────────────────

/write ##Network_Summary "Analyzed {COUNT :#SEEDS} entities with {COUNT :#COMMON_ENTITIES} common connections"
/write ##Direct_Connections :#DIRECT_CONNECTION_*
/write ##Indirect_Connections :#INDIRECT_CONNECTION_* :#COMMON_ENTITIES
/write ##Network_Hubs :#NETWORK_HUBS
/write ##Connection_Paths :#PATH_*
/write ##Temporal_Analysis :#TEMPORAL_CLUSTERS :#CORRELATED_EVENTS
/write ##Hidden_Links :#HIDDEN_CONNECTORS :#LEAK_CONNECTIONS

#═══════════════════════════════════════════════════════════════════════════════
# END CHAIN: network_analysis
#═══════════════════════════════════════════════════════════════════════════════
```

---

## COMPREHENSIVE GAP SUMMARY

### HIGH PRIORITY (Blocking Core Functionality)

| Operator | Syntax | Purpose | Suggested Handler |
|----------|--------|---------|-------------------|
| Sanctions check | `sanctions?` | Query OFAC, EU, UN, UK sanctions | WDC + Sanctions API |
| PEP check | `pep?` | Politically Exposed Person | WDC + PEP Database |
| Adverse media | `adverse?` | Negative news search | WDC + News APIs |
| UBO traversal | `ubo?` | Ultimate Beneficial Owner chain | Recursive :cruk! |
| EDITH write | `/write ##Section` | Target template section | EDITH Bridge |
| EDITH flag | `/flag ##Section` | Mark section for review | EDITH Bridge |
| NEXUS extraction | `@nexus?` or `@x?` | Relationships as nodes | Cymonides query |
| Career extraction | `career?` | Employment history from appointments | CH API parsing |
| Events extraction | `events?` | Company events/scandals | News + Registry |
| Temporal overlap | `overlap?` | Intersection of periods | Date range logic |
| Period filter | `:YYYY-YYYY` | Temporal window filter | Query modifier |
| Role filter | `##role:XXX` | Filter by relationship type | Cymonides filter |

### MEDIUM PRIORITY (Enhanced Functionality)

| Operator | Syntax | Purpose |
|----------|--------|---------|
| K-U state query | `KU?` | Check node completeness |
| Industry mapping | `industry_map?` | SIC to industry category |
| Timeline builder | `timeline?` | Build chronological view |
| Pattern detection | `pattern?` | Temporal/structural patterns |
| Path finder | `path?` | Connection path between entities |
| Expectation check | `expect?` | Check for expected relationships |
| Intersection | `intersect?` | Multi-tag intersection |
| FOREACH loop | `FOREACH {...}` | Iterate over tagged set |
| Wildcard tags | `:#TAG_*` | Match multiple tags by pattern |
| TOP selector | `TOP(N)` | Select top N items |
| EXCLUDE | `EXCLUDE :#tag` | Remove items from set |
| COUNT | `COUNT(:#tag)` | Count items in tag |

### LOW PRIORITY (Nice to Have)

| Operator | Syntax | Purpose |
|----------|--------|---------|
| LinkedIn lookup | `linkedin?` | LinkedIn profile |
| Social profiles | `social?` | Social media profiles |
| Education extraction | `@education?` | Education history |
| Date extraction | `@date?` | Extract dates from content |
| Temporal clustering | `cluster?` | Group by time proximity |

---

## IMPLEMENTATION NOTES

### FOREACH Implementation

```python
# Input
/gridS{:#OFFICERS} => FOREACH {
    sanctions? :$ITEM => +#SANCTIONS_$INDEX
    pep? :$ITEM => +#PEP_$INDEX
}

# Expands to:
sanctions? :#OFFICERS[0] => +#SANCTIONS_0
pep? :#OFFICERS[0] => +#PEP_0
sanctions? :#OFFICERS[1] => +#SANCTIONS_1
pep? :#OFFICERS[1] => +#PEP_1
# ... etc
```

### Wildcard Tag References

```python
# :#TAG_* matches: #TAG_0, #TAG_1, #TAG_FOO, etc.
# Implementation: regex on tag names in Cymonides
```

### Nested Slot References

```python
# :#COMPANY ##jurisdiction = access jurisdiction slot value
# :#NEXUS ##appointment_date = access date from relationship
# Implementation: dot notation alternative :#COMPANY.jurisdiction
```

### NEXUS as First-Class Nodes

Each relationship should have:
```python
{
    "id": "nexus_123",
    "type": "officer_of",
    "party_a": "person_456",  # The officer
    "party_b": "company_789", # The company
    "slots": {
        "role": "Director",
        "appointment_date": "2020-01-15",
        "resignation_date": null,  # EMPTY = still active
        "share_percentage": null   # EMPTY = unknown
    },
    "state": "IDENTIFIED",  # or SOUGHT, SPECULATED
    "ku_state": {
        "filled": ["role", "appointment_date"],
        "empty": ["resignation_date", "share_percentage"],
        "state": "PARTIAL"  # COMPLETE, PARTIAL, HUNGRY
    }
}
```
