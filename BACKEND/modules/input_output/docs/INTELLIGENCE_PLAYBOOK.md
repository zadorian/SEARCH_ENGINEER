# Intelligence Playbook: Strategic Source Filtering

**Purpose:** Leverage matrix intelligence metadata to identify arbitrage opportunities and build investigation strategies.

**Last Updated:** 2025-11-23

---

## Core Concept: Information Arbitrage

**Information Arbitrage** = Exploiting asymmetries in data availability across jurisdictions and source types.

### The Three Arbitrage Dimensions

1. **Geographic Arbitrage** - Data available in one jurisdiction but not others
2. **Access Arbitrage** - Free sources revealing what others charge for
3. **Temporal Arbitrage** - Historical data revealing patterns invisible in current snapshots

---

## Strategic Filtering Patterns

### Pattern 1: Free UBO Discovery

**Objective:** Find jurisdictions with free beneficial ownership transparency

**Filter:**

```typescript
const freeUBOJurisdictions = Object.entries(sources)
  .filter(([jurisdiction, srcs]) =>
    srcs.some(
      s =>
        s.related_entity_types.includes("UBO") &&
        s.access === "public" &&
        s.classification === "Official Registry"
    )
  )
  .map(([jurisdiction, srcs]) => ({
    jurisdiction,
    sources: srcs.filter(s => s.related_entity_types.includes("UBO")),
  }));
```

**Arbitrage Strategy:**

- UK Companies House reveals UBOs for free
- Most jurisdictions charge or don't reveal UBOs at all
- **Play:** Use free UBO data to trace cross-border ownership chains

**Example:**

```
UK Company → UBO in Cyprus → Cyprus company (private) → Assets in Panama
       ↑               ↑                    ↑                     ↑
    Free UBO      Use UK UBO to      Paywalled/        Hit wall
                 identify next link   Restricted
```

---

### Pattern 2: Foreign Branch Intelligence

**Objective:** Find sources that reveal managers/directors of foreign branches

**Filter:**

```typescript
const foreignBranchSources = Object.values(sources)
  .flat()
  .filter(s =>
    s.arbitrage_opportunities.some(opp => opp.includes("Foreign Branch Reveal"))
  );
```

**Arbitrage Strategy:**

- Some jurisdictions require foreign entities to register local representatives
- These representatives are often hidden in the entity's home jurisdiction
- **Play:** Use foreign registration requirements to identify undisclosed relationships

**Example:**

```
French company with "no directors listed" on official registry
    ↓
Search foreign branch registrations (Germany, Netherlands, Belgium)
    ↓
German trade registry reveals French company has branch with named manager
    ↓
Manager is actually undisclosed beneficial owner
```

---

### Pattern 3: Leak-to-Registry Correlation

**Objective:** Cross-reference leaked data with official sources to find discrepancies

**Filter:**

```typescript
const leakDatasets = Object.values(sources)
  .flat()
  .filter(s => s.classification === "Leak Dataset");

const officialRegistriesByJurisdiction = {};
Object.entries(sources).forEach(([jurisdiction, srcs]) => {
  officialRegistriesByJurisdiction[jurisdiction] = srcs.filter(
    s => s.classification === "Official Registry"
  );
});

// Build correlation pairs
const correlationPairs = leakDatasets
  .map(leak => {
    const leakJurisdictions = extractJurisdictions(leak); // Extract from notes/flows
    return leakJurisdictions.map(j => ({
      leak,
      official: officialRegistriesByJurisdiction[j],
    }));
  })
  .flat();
```

**Arbitrage Strategy:**

- Leaked data often contains entities/relationships not in official registries
- Time gaps between leak date and current registry state reveal changes
- **Play:** Identify sanitized records, removed directors, or dissolved entities

**Example:**

```
Panama Papers shows Entity X owned by Person Y (2016)
    ↓
Current registry shows Entity X owned by Foundation Z (2025)
    ↓
Timeline: Person Y transferred ownership after leak became public
    ↓
Arbitrage: Leak reveals true beneficial owner despite official sanitization
```

---

### Pattern 4: Historical Officer Tracking

**Objective:** Track entity movements over time via former directors/shareholders

**Filter:**

```typescript
const historicalSources = Object.values(sources)
  .flat()
  .filter(
    s =>
      s.related_entity_types.includes("historical_entities") ||
      s.arbitrage_opportunities.some(opp => opp.includes("Historical"))
  );
```

**Arbitrage Strategy:**

- Current snapshots hide relationships that existed in the past
- Directors who resign still reveal networks
- **Play:** Map historical connections to identify hidden affiliations

**Example:**

```
Company A (current directors: X, Y)
    ↓
Historical registry: Former director Z (resigned 2020)
    ↓
Search Z's current directorships → Director of Company B
    ↓
Arbitrage: Companies A and B are affiliated via historical director overlap
```

---

### Pattern 5: OSINT-to-Registry Validation Pipeline

**Objective:** Build validation chains from OSINT leads to official confirmation

**Filter:**

```typescript
const osintSources = Object.values(sources)
  .flat()
  .filter(s => s.classification === "OSINT Platform");

const officialSources = Object.values(sources)
  .flat()
  .filter(s => s.classification === "Official Registry");

// For each OSINT output, find official source that can validate it
const validationChains = osintSources.flatMap(osint =>
  osint.outputs.map(output => ({
    osint_source: osint,
    validates: output,
    official_sources: officialSources.filter(
      official =>
        official.inputs.includes(output) || official.outputs.includes(output)
    ),
  }))
);
```

**Arbitrage Strategy:**

- OSINT (EYE-D, breach data) provides leads but low reliability
- Official registries provide confirmation but require specific queries
- **Play:** Use OSINT for discovery, official sources for validation

**Example:**

```
EYE-D breach data: email@company.com → John Doe
    ↓
Extract company domain → company.com
    ↓
WHOIS/registry search → Company Ltd (UK)
    ↓
Companies House → Directors: John Doe (confirmed)
    ↓
Arbitrage: Breach email → validated director identification
```

---

### Pattern 6: Subsidiary Network Mapping

**Objective:** Trace corporate group structures via subsidiary reveals

**Filter:**

```typescript
const subsidiarySources = Object.values(sources)
  .flat()
  .filter(
    s =>
      s.related_entity_types.includes("subsidiaries") ||
      s.related_entity_types.includes("parent_company")
  );

// Group by jurisdiction for cross-border mapping
const subsidiaryMapByJurisdiction = {};
subsidiarySources.forEach(s => {
  if (!subsidiaryMapByJurisdiction[s.jurisdiction]) {
    subsidiaryMapByJurisdiction[s.jurisdiction] = [];
  }
  subsidiaryMapByJurisdiction[s.jurisdiction].push(s);
});
```

**Arbitrage Strategy:**

- Parent companies often hidden in offshore jurisdictions
- Subsidiaries registered in operating jurisdictions reveal group structure
- **Play:** Map upward from subsidiaries to find hidden parent entities

**Example:**

```
UK Subsidiary A (100% owned by Holding Co in BVI)
    ↓
UK Subsidiary B (100% owned by same BVI Holding Co)
    ↓
UK Subsidiary C (100% owned by same BVI Holding Co)
    ↓
Arbitrage: UK reveals group structure; BVI registry reveals nothing
```

---

### Pattern 7: Regulatory Arbitrage Detection

**Objective:** Identify entities exploiting regulatory gaps between jurisdictions

**Filter:**

```typescript
const multiJurisdictionEntities = Object.entries(sources).flatMap(
  ([jurisdiction, srcs]) =>
    srcs
      .filter(
        s =>
          s.classification === "Regulatory Authority" &&
          s.notes.toLowerCase().includes("foreign")
      )
      .map(s => ({
        jurisdiction,
        source: s,
      }))
);
```

**Arbitrage Strategy:**

- Entities regulated in multiple jurisdictions for different activities
- Gaps between regulatory regimes create compliance arbitrage
- **Play:** Identify entities operating in gray areas between regulations

**Example:**

```
Entity licensed as "investment advisor" in Jurisdiction A (light regulation)
    ↓
Same entity operates as "broker-dealer" in Jurisdiction B (heavy regulation)
    ↓
Arbitrage: Entity exploits classification differences to minimize compliance
```

---

### Pattern 8: Bulk Pattern Analysis

**Objective:** Download full datasets for network analysis and pattern detection

**Filter:**

```typescript
const bulkSources = Object.values(sources)
  .flat()
  .filter(
    s =>
      s.arbitrage_opportunities.some(opp =>
        opp.includes("Bulk Pattern Analysis")
      ) ||
      s.notes.toLowerCase().includes("bulk") ||
      s.notes.toLowerCase().includes("api")
  );
```

**Arbitrage Strategy:**

- Individual queries reveal trees; bulk data reveals forests
- Network analysis on full datasets exposes hidden patterns
- **Play:** Download entire registries to identify systemic patterns

**Example:**

```
Query 1: Company A → Director X
Query 2: Company B → Director X
Query N: Company Z → Director X
    ↓
Bulk download entire registry → Director X holds 47 directorships
    ↓
Cross-reference addresses → All 47 companies share same registered office
    ↓
Arbitrage: Systemic pattern invisible via individual queries
```

---

## Classification-Based Strategy Matrix

| Classification           | Primary Use Case          | Arbitrage Strategy                  |
| ------------------------ | ------------------------- | ----------------------------------- |
| **Official Registry**    | Ground truth verification | Free data vs paywalled aggregators  |
| **Private Aggregator**   | Enhanced data/speed       | Compare with official (sanitized?)  |
| **Leak Dataset**         | Historical truth          | Discrepancies with current official |
| **OSINT Platform**       | Lead generation           | Validate with official sources      |
| **Court System**         | Legal relationships       | Hidden ownership via litigation     |
| **Regulatory Authority** | Compliance gaps           | Multi-jurisdiction arbitrage        |
| **Public Database**      | Free deep dives           | Network analysis on bulk data       |

---

## Related Entity Type Strategies

| Entity Type             | Strategic Value   | Example Arbitrage                   |
| ----------------------- | ----------------- | ----------------------------------- |
| **UBO**                 | Ultimate control  | Free UBO → paid-only elsewhere      |
| **subsidiaries**        | Group structure   | UK reveals; offshore hides          |
| **directors**           | Personal networks | Historical = hidden affiliations    |
| **shareholders**        | Ownership chains  | Trace through multi-hop chains      |
| **parent_company**      | Hidden control    | Subsidiary→Parent mapping           |
| **affiliated_entities** | Related parties   | Transaction conflicts of interest   |
| **foreign_entities**    | Cross-border      | Foreign branch reveals hidden links |
| **historical_entities** | Timeline patterns | Director resignations = red flags   |

---

## Practical Investigation Workflows

### Workflow 1: Unknown Company → Full Network Map

```typescript
// Step 1: Identify jurisdiction
const company = "Acme Corp Ltd";
const jurisdiction = "GB"; // From initial intel

// Step 2: Get official profile
const officialSource = sources[jurisdiction].find(
  s => s.classification === "Official Registry"
);
// Query: company_name → officers, shareholders, UBOs

// Step 3: Expand via related entities
const directors = extractDirectors(officialProfile);
const subsidiaries = extractSubsidiaries(officialProfile);

// Step 4: Cross-check with OSINT
const osintSource = sources["GLOBAL"].find(
  s => s.classification === "OSINT Platform"
);
// Query each director → emails, social profiles, domain links

// Step 5: Historical tracking
const historicalSource = sources[jurisdiction].find(s =>
  s.related_entity_types.includes("historical_entities")
);
// Query: company → former directors → their current companies

// Step 6: Foreign branches
const foreignJurisdictions = identifyLikelyJurisdictions(industry, officers);
foreignJurisdictions.forEach(fj => {
  const foreignSource = sources[fj].find(s =>
    s.arbitrage_opportunities.some(opp => opp.includes("Foreign Branch"))
  );
  // Query: company_name → foreign branch registrations
});
```

### Workflow 2: Person Name → Hidden Asset Network

```typescript
// Step 1: OSINT lead generation
const osintSource = sources["GLOBAL"].find(
  s => s.classification === "OSINT Platform"
);
// Query: person_name → emails, domains, social profiles

// Step 2: Domain→Company mapping
const domains = extractDomains(osintResults);
const companyMappings = domains.map(domain => {
  // WHOIS → registered entity → corporate registry
  return traceDomainToCompany(domain);
});

// Step 3: Officer searches across all jurisdictions
const allOfficerSources = Object.values(sources)
  .flat()
  .filter(s => s.outputs.includes("company_officers"));

allOfficerSources.forEach(source => {
  // Query: person_name → directorships
});

// Step 4: Shareholder searches
const shareholderSources = Object.values(sources)
  .flat()
  .filter(s => s.related_entity_types.includes("shareholders"));

// Step 5: Property/asset registries
const assetSources = Object.values(sources)
  .flat()
  .filter(s => s.section === "at"); // Asset tracking

// Step 6: Litigation searches
const courtSources = Object.values(sources)
  .flat()
  .filter(s => s.classification === "Court System");
```

---

## Measuring Arbitrage Value

**Arbitrage Score Formula:**

```typescript
function calculateArbitrageScore(source) {
  let score = 0;

  // Free access to typically-paywalled data
  if (
    source.access === "public" &&
    source.related_entity_types.includes("UBO")
  ) {
    score += 10;
  }

  // Foreign entity reveals
  if (source.arbitrage_opportunities.some(opp => opp.includes("Foreign"))) {
    score += 8;
  }

  // Historical tracking
  if (source.related_entity_types.includes("historical_entities")) {
    score += 7;
  }

  // Bulk download capability
  if (source.arbitrage_opportunities.some(opp => opp.includes("Bulk"))) {
    score += 6;
  }

  // Official vs Leak correlation potential
  if (source.classification === "Leak Dataset") {
    score += 9;
  }

  // Multiple related entity types
  score += source.related_entity_types.length * 2;

  return score;
}

// Rank sources by arbitrage value
const rankedSources = Object.values(sources)
  .flat()
  .map(s => ({
    ...s,
    arbitrage_score: calculateArbitrageScore(s),
  }))
  .sort((a, b) => b.arbitrage_score - a.arbitrage_score);
```

---

## Frontend Implementation Checklist

### Search Interface Enhancements

- [ ] Filter by `classification` (dropdown: Official Registry, Leak Dataset, etc.)
- [ ] Filter by `related_entity_types` (checkboxes: UBO, subsidiaries, directors, etc.)
- [ ] Filter by `arbitrage_opportunities` (full-text search in opportunities array)
- [ ] Show arbitrage score badge on high-value sources
- [ ] "Similar Sources" based on classification + related_entity_types
- [ ] Jurisdiction comparison view (e.g., "UK reveals UBOs; BVI doesn't")
- [ ] Timeline view for historical_entities sources

### Result Display

- [ ] Badge for sources that `exposes_related_entities`
- [ ] Classification tag (colored by category)
- [ ] Arbitrage opportunities list (expandable)
- [ ] Related entity types icons (visual indicators)
- [ ] "Strategic value" score (calculated arbitrage score)

### Investigation Builder

- [ ] Multi-source workflow builder
- [ ] Chain suggestions based on outputs→inputs matching
- [ ] Arbitrage playbook templates (pre-built workflows)
- [ ] Export investigation plan as checklist

---

**Result: Matrix becomes not just a catalog, but a strategic intelligence engine.**
