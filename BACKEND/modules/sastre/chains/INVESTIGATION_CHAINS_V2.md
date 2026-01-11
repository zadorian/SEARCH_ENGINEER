# SASTRE Investigation Chains V2
## Using Correct Syntax (per additin spec v5.0)

---

## Syntax Reference (CORRECT)

### The Four Classes (CAPITALISED)
| CLASS | Short | Role |
|-------|-------|------|
| @SUBJECT | @S | Entities + Concepts (who/what) |
| @LOCATION | @L | Coordinates (where/when/context) |
| @NEXUS | @X | Relationships (edges between) |
| @NARRATIVE | @N | Directing brain (questions/answers) |

### Three Operator Types
| Suffix | Type | Meaning | Examples |
|--------|------|---------|----------|
| `?` | QUERY | Search FOR / Extract | `@P?`, `bl?`, `=?` |
| `!` | FILTER | FROM source/location | `:sanctions!`, `:pep!`, `:rf!`, `pdf!`, `uk!` |
| `/` | COMMAND | DO this action | `/enrich`, `/scrape`, `/gridS` |

### Compliance Sources as LOCATION Filters
```
:sanctions!     # Sanctions lists (OFAC, EU, UN, UK)
:pep!           # PEP databases
:rf!            # Red flag / adverse media sources
:leaks!         # Leaked databases (Panama Papers, etc.)
```

### NEXUS Relationship Extraction
```
@ubo?           # Extract beneficial_owner_of relationships
@officer?       # Extract officer_of relationships  
@shareholder?   # Extract shareholder_of relationships
@X?             # Extract all NEXUS (relationships)
```

### Intersection Operator
```
A x B           # Find nexus between A and B (Known-Known)
A x [?]         # Find what connects to A (Known-Unknown)
x?              # Query intersection/overlap
```

### Grid Commands
```
/gridS          # Subject view
/gridL          # Location view
/gridX          # NEXUS view
/gridN          # Narrative view

/gridS{A}       # Column A (all subjects)
/gridS{C}       # Column C (related nodes)
/gridS{1-5A}    # Rows 1-5, Column A
```

### Conditionals
```
IF @PERSON THEN puk! ELSE cuk!
IF filled? :#slot THEN skip ELSE action
```

---

## CHAIN 1: UK Person Deep Due Diligence

### Phase 1: Anchor Subject
```
# Tag the subject
p: [SUBJECT_NAME] => +#SUBJECT

# UK registry search for all companies
:#SUBJECT :cruk! => +#CH_RESULTS

# Extract company relationships (NEXUS)
@officer? :#CH_RESULTS => +#OFFICER_NEXUS
@shareholder? :#CH_RESULTS => +#SHAREHOLDER_NEXUS
```

### Phase 2: Build Career Chapters
```
# Get all companies from NEXUS nodes
/gridX{:#OFFICER_NEXUS} => @C? => +#CURRENT_COMPANIES

# Extract temporal data from NEXUS
# (appointment_date, resignation_date are slots on NEXUS nodes)
/gridX{:#OFFICER_NEXUS} => +#CAREER_CHAPTERS
```

### Phase 3: Temporal Overlap Detection
```
# Find events for companies during subject's tenure
# x? = intersection query
:#SUBJECT x :#CURRENT_COMPANIES x :rf! => +#TEMPORAL_OVERLAPS

# Alternative: Check adverse on each company
/gridS{:#CURRENT_COMPANIES} => :rf! => +#COMPANY_ADVERSE
```

### Phase 4: Associate Network (One-Step-Removed)
```
# Get co-directors from same companies
/gridX{[?] x :#CURRENT_COMPANIES @officer_of} => @P? => +#CO_OFFICERS

# Get co-shareholders
/gridX{[?] x :#CURRENT_COMPANIES @shareholder_of} => @P? => +#CO_SHAREHOLDERS

# Network overlap check (handshake)
(:#CO_OFFICERS OR :#CO_SHAREHOLDERS) => /clink => +#NETWORK_OVERLAPS
```

### Phase 5: Mini-DD on Top Associates
```
# For each top 5 associate
/gridS{:#NETWORK_OVERLAPS}{1-5A} => +#TOP_ASSOCIATES

# Run compliance on each
:#TOP_ASSOCIATES :cruk! => +#ASSOC_CH
:#TOP_ASSOCIATES :sanctions! => +#ASSOC_SANCTIONS
:#TOP_ASSOCIATES :pep! => +#ASSOC_PEP
:#TOP_ASSOCIATES :rf! => +#ASSOC_ADVERSE
```

### Phase 6: Historical Affiliations (Post-Departure Events)
```
# Get past companies (where resignation_date is filled)
/gridX{:#OFFICER_NEXUS} => IF filled? :resignation_date THEN +#PAST_AFFILIATIONS

# Check for events AFTER subject left
:#PAST_AFFILIATIONS :rf! => +#POST_DEPARTURE_EVENTS
```

### Phase 7: Compliance Direct
```
# Direct checks on subject
:#SUBJECT :sanctions! => +#SANCTIONS_DIRECT
:#SUBJECT :pep! => +#PEP_DIRECT
:#SUBJECT :rf! => +#ADVERSE_DIRECT

# FCA check (UK specific)
:#SUBJECT :reguk! => +#FCA_DIRECT
```

### Phase 8: Litigation
```
:#SUBJECT :lituk! => +#LITIGATION
```

### Phase 9: Digital Footprint
```
# Brute search
:#SUBJECT => /brute => +#BRUTE_RESULTS

# Entity extraction from results
@ENT? :#BRUTE_RESULTS => +#BRUTE_ENTITIES

# Check for new companies/associates
:#BRUTE_ENTITIES x :#CURRENT_COMPANIES => +#NEW_CONNECTIONS
```

### Phase 10: Cross-Pollination Assessment
```
# Rotate through Grid views to find gaps

# SUBJECT view: What entities are incomplete?
/gridS{:#SUBJECT} => +#SUBJECT_STATE

# LOCATION view: What sources haven't been checked?
/gridL => +#SOURCE_STATE  

# NEXUS view: What relationships are unverified?
/gridX{:#OFFICER_NEXUS} => +#NEXUS_STATE
```

### Phase 11: Document Generation
```
# Write to EDITH template sections using tagged results
# (Section references use @ prefix for template sections)

:#SUBJECT => @Executive_Summary
:#CURRENT_COMPANIES => @Corporate_Affiliations
:#PAST_AFFILIATIONS => @Corporate_Affiliations
:#FCA_DIRECT => @Regulatory_Status
:#SANCTIONS_DIRECT => @Regulatory_Status
:#PEP_DIRECT => @Regulatory_Status
:#LITIGATION => @Litigation_History
:#NETWORK_OVERLAPS => @Associate_Network
:#ADVERSE_DIRECT => @Adverse_Media
:#TEMPORAL_OVERLAPS => @Temporal_Analysis
```

---

## CHAIN 2: UK Company Due Diligence

### Phase 1: Anchor Company
```
c: [COMPANY_NAME] => +#SUBJECT
:#SUBJECT :cruk! => +#CH_OFFICIAL
```

### Phase 2: Officers
```
# Extract officer relationships
@officer? :#CH_OFFICIAL => +#OFFICER_NEXUS

# Get person entities from NEXUS
/gridX{:#OFFICER_NEXUS} => @P? => +#OFFICERS

# Compliance on officers
:#OFFICERS :sanctions! => +#OFFICER_SANCTIONS
:#OFFICERS :pep! => +#OFFICER_PEP
```

### Phase 3: Ownership (UBO Chain)
```
# Extract shareholder relationships
@shareholder? :#CH_OFFICIAL => +#SHAREHOLDER_NEXUS

# Get direct shareholders
/gridX{:#SHAREHOLDER_NEXUS} => @P? => +#DIRECT_SHAREHOLDERS_P
/gridX{:#SHAREHOLDER_NEXUS} => @C? => +#DIRECT_SHAREHOLDERS_C

# UBO extraction (traverse beneficial_owner_of)
@ubo? :#SUBJECT => +#UBO_CHAIN

# Compliance on UBO chain
:#UBO_CHAIN :sanctions! => +#UBO_SANCTIONS
:#UBO_CHAIN :pep! => +#UBO_PEP
```

### Phase 4: Related Companies
```
# Same address
/gridL{:#CH_OFFICIAL @address} => +#ADDRESS
[?] x :#ADDRESS => @C? => +#SAME_ADDRESS_COMPANIES

# Same officers (reverse intersection)
/gridX{:#OFFICERS x [?] @officer_of} => @C? => +#SAME_OFFICER_COMPANIES

# Cluster related
(:#SAME_ADDRESS_COMPANIES OR :#SAME_OFFICER_COMPANIES) => /clink => +#RELATED_COMPANIES
```

### Phase 5: Regulatory & Compliance
```
:#SUBJECT :reguk! => +#FCA_CHECK
:#SUBJECT :lituk! => +#LITIGATION
:#SUBJECT :rf! => +#ADVERSE_MEDIA
```

### Phase 6: Digital Footprint
```
# Find company domain
cdom: :#SUBJECT => +#DOMAIN

# Domain analysis
alldom: :#DOMAIN => +#DOMAIN_ANALYSIS

# Backlinks
bl? :!:#DOMAIN => +#BACKLINKS
```

---

## CHAIN 3: Asset Trace

### Phase 1: Corporate Assets
```
# All companies where subject is UBO or officer
@ubo? :#SUBJECT => +#UBO_COMPANIES
@officer? :#SUBJECT => +#OFFICER_COMPANIES

# Multi-jurisdiction lookups
:#UBO_COMPANIES :cuk! => +#UK_COMPANIES
:#UBO_COMPANIES :ccy! => +#CY_COMPANIES
:#UBO_COMPANIES :cbvi! => +#BVI_COMPANIES
```

### Phase 2: Property Assets
```
# UK Land Registry (if available)
:#SUBJECT :landuk! => +#LAND_REGISTRY

# Property mentions in brute search
:#SUBJECT "property" OR "real estate" => /brute => +#PROPERTY_MENTIONS
@ENT? :#PROPERTY_MENTIONS => +#PROPERTY_ENTITIES
```

### Phase 3: Digital Assets
```
# Domains owned
?owl :!:#KNOWN_DOMAIN => +#OWNED_DOMAINS

# GA cluster (domains with same tracking)
ga? :!:#KNOWN_DOMAIN => +#GA_CLUSTER
```

### Phase 4: Offshore Discovery
```
# Leaked databases
:#SUBJECT :leaks! => +#LEAK_HITS

# Extract entities from leaks
@ENT? :#LEAK_HITS => +#LEAK_ENTITIES

# Filter to offshore jurisdictions
/gridS{:#LEAK_ENTITIES} => IF @LOCATION :offshore THEN +#OFFSHORE_ENTITIES
```

### Phase 5: Timeline
```
# Build acquisition timeline from NEXUS nodes
# (each NEXUS has temporal slots)
/gridX{:#UBO_COMPANIES} => +#ACQUISITION_TIMELINE

# Check for pre-sanction movements
:#ACQUISITION_TIMELINE x :sanctions! => +#SUSPICIOUS_TIMING
```

---

## CHAIN 4: Network Analysis

### Phase 1: Seeds
```
# Multiple starting entities
p: [NAME_1] => +#SEED_1
p: [NAME_2] => +#SEED_2
c: [COMPANY] => +#SEED_3

(:#SEED_1 OR :#SEED_2 OR :#SEED_3) => +#SEEDS
```

### Phase 2: Expand Layer 1
```
# For each seed, get one-hop connections
:#SEED_1 x [?] => +#LAYER1_1
:#SEED_2 x [?] => +#LAYER1_2
:#SEED_3 x [?] => +#LAYER1_3
```

### Phase 3: Intersection (Find Common)
```
# N×N comparison
:#SEEDS => /clink => +#SEED_OVERLAPS

# Find entities appearing in multiple Layer 1s
:#LAYER1_1 x :#LAYER1_2 => +#COMMON_12
:#LAYER1_1 x :#LAYER1_3 => +#COMMON_13
:#LAYER1_2 x :#LAYER1_3 => +#COMMON_23

# Union of common entities = network hubs
(:#COMMON_12 OR :#COMMON_13 OR :#COMMON_23) => +#NETWORK_HUBS
```

### Phase 4: NEXUS Assessment
```
# What relationships exist between seeds?
/gridX{:#SEEDS} => +#SEED_NEXUS

# What relationships exist to hubs?
/gridX{:#SEEDS x :#NETWORK_HUBS} => +#HUB_NEXUS
```

### Phase 5: Hidden Links
```
# Domain cross-linking
/gridL{:#SEEDS @domain} => +#SEED_DOMAINS
:#SEED_DOMAINS => bl? => +#DOMAIN_BACKLINKS
@ENT? :#DOMAIN_BACKLINKS => +#BACKLINK_ENTITIES

# Check for unexpected overlaps
:#BACKLINK_ENTITIES x :#SEEDS => +#HIDDEN_CONNECTIONS
```

---

## Key Syntax Differences from V1

| V1 (WRONG) | V2 (CORRECT) | Reason |
|------------|--------------|--------|
| `sanctions?` | `:sanctions!` | Compliance is LOCATION filter |
| `pep?` | `:pep!` | Compliance is LOCATION filter |
| `adverse?` | `:rf!` | Red flag is LOCATION filter |
| `ubo?` | `@ubo?` | UBO is NEXUS extraction |
| `##role:shareholder` | `@shareholder_of` | Relationship type, not filter |
| `/flag ##Section` | (removed) | Rejected |
| `@nexus` | `@NEXUS` or `@X` | Classes are CAPITALISED |
| `overlap?` | `x?` | Intersection operator |

---

## NEXUS as First-Class Nodes

Each relationship is stored as a node with:
- `party_a` / `party_b` — endpoints
- `type` — officer_of, shareholder_of, beneficial_owner_of, etc.
- Slots — `appointment_date`, `resignation_date`, `share_percentage`
- State — IDENTIFIED, SOUGHT, SPECULATED

Extracting NEXUS:
```
@officer? :#SOURCE        # Extract officer_of relationships
@shareholder? :#SOURCE    # Extract shareholder_of relationships
@ubo? :#SOURCE            # Extract beneficial_owner_of chain
@X? :#SOURCE              # Extract ALL relationships
```

Querying NEXUS:
```
/gridX{#john x #acme}              # Specific relationship
/gridX{#john x [?]}                # All John's connections
/gridX{[?] x #acme @officer_of}    # Acme's officers
```
