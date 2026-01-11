# Field Mapping: API Sources → Entity Template

## Entity Template Structure
```json
{
  "id": "",
  "name": {"value": "", "source": ""},
  "about": {
    "company_number": "",
    "incorporation_date": "",
    "jurisdiction": "",
    "registered_address": {"value": "", "source": ""},
    "website": {"value": "", "source": ""}
  },
  "officers": [{"type": "", "name": "", "details": "", "source": ""}],
  "ownership_structure": {"shareholders": "", "beneficial_owners": "", "source": ""}
}
```

---

## OpenCorporates → Entity Template

### Source Data Structure
```json
{
  "name": "Apple Inc",
  "company_number": "C0806592",
  "jurisdiction_code": "us_ca",
  "incorporation_date": "1977-01-03",
  "dissolution_date": null,
  "company_type": "Domestic Stock",
  "registry_url": "...",
  "branch": "F",
  "branch_status": null,
  "inactive": false,
  "current_status": "Active",
  "created_at": "...",
  "updated_at": "...",
  "retrieved_at": "...",
  "opencorporates_url": "...",
  "previous_names": [],
  "source": {...},
  "registered_address_in_full": "ONE APPLE PARK WAY, CUPERTINO, CA, 95014",
  "officers": [
    {
      "name": "TIM COOK",
      "position": "CEO",
      "start_date": "2011-08-24",
      "end_date": null
    }
  ]
}
```

### Field Mapping
```javascript
{
  "id": company.company_number,  // "C0806592"
  "name": {
    "value": company.name,  // "Apple Inc"
    "variations": company.previous_names?.join(", ") || "",
    "alias": "",
    "source": "[OC]"
  },
  "node_class": "entity",
  "type": "company",
  "about": {
    "company_number": company.company_number,  // "C0806592"
    "incorporation_date": company.incorporation_date,  // "1977-01-03"
    "jurisdiction": company.jurisdiction_code,  // "us_ca"
    "registered_address": {
      "value": company.registered_address_in_full,  // "ONE APPLE PARK WAY..."
      "comment": "",
      "source": "[OC]"
    },
    "website": {
      "value": "",  // NOT PROVIDED
      "source": ""
    },
    "contact_details": {
      "phone": {"value": "", "source": ""},  // NOT PROVIDED
      "email": {"value": "", "source": ""}   // NOT PROVIDED
    },
    "source": "[OC]"
  },
  "officers": company.officers.map(o => ({
    "type": o.position?.includes("Director") ? "director" :
            o.position?.includes("CEO") || o.position?.includes("CFO") ? "executive" : "other",
    "name": o.name,  // "TIM COOK"
    "details": `Position: ${o.position}, Appointed: ${o.start_date}${o.end_date ? `, Resigned: ${o.end_date}` : ''}`,
    "source": "[OC]"
  })),
  "ownership_structure": {
    "shareholders": "",  // NOT PROVIDED
    "beneficial_owners": "",  // NOT PROVIDED
    "source": ""
  },
  "financial_results": "",  // NOT PROVIDED
  "notes": `Status: ${company.current_status}, Type: ${company.company_type}, Branch: ${company.branch || 'N/A'}`
}
```

---

## Aleph (OCCRP) → Entity Template

### Source Data Structure
```json
{
  "id": "NK-a1mnptn4rv3hgzqfk4cawrxoi4",
  "caption": "Apple Inc",
  "schema": "Company",
  "properties": {
    "name": ["Apple Inc"],
    "registrationNumber": ["C0806592"],
    "country": ["us"],
    "incorporationDate": ["1977-01-03"],
    "address": ["One Apple Park Way, Cupertino, CA 95014"],
    "website": ["https://www.apple.com"],
    "email": ["contact@apple.com"],
    "phone": ["+1-408-996-1010"]
  },
  "datasets": ["us_companies"],
  "referents": [],
  "countries": ["us"],
  "first_seen": "...",
  "last_seen": "..."
}
```

### Field Mapping
```javascript
{
  "id": entity.properties.registrationNumber?.[0] || entity.id,  // "C0806592"
  "name": {
    "value": entity.caption || entity.properties.name?.[0],  // "Apple Inc"
    "variations": entity.properties.alias?.join(", ") || "",
    "alias": entity.properties.previousName?.join(", ") || "",
    "source": "[AL]"
  },
  "node_class": "entity",
  "type": "company",
  "about": {
    "company_number": entity.properties.registrationNumber?.[0] || "",  // "C0806592"
    "incorporation_date": entity.properties.incorporationDate?.[0] || "",  // "1977-01-03"
    "jurisdiction": entity.properties.country?.[0] || entity.countries?.[0] || "",  // "us"
    "registered_address": {
      "value": entity.properties.address?.[0] || "",  // "One Apple Park Way..."
      "comment": "",
      "source": "[AL]"
    },
    "website": {
      "value": entity.properties.website?.[0] || "",  // "https://www.apple.com"
      "comment": "",
      "source": "[AL]"
    },
    "contact_details": {
      "phone": {
        "value": entity.properties.phone?.[0] || "",  // "+1-408-996-1010"
        "source": "[AL]"
      },
      "email": {
        "value": entity.properties.email?.[0] || "",  // "contact@apple.com"
        "source": "[AL]"
      },
      "source": "[AL]"
    },
    "source": "[AL]"
  },
  "officers": [],  // Requires separate Directorship query
  "ownership_structure": {
    "shareholders": entity.properties.shareholders?.join(", ") || "",
    "beneficial_owners": entity.properties.beneficialOwners?.join(", ") || "",
    "source": "[AL]"
  },
  "financial_results": entity.properties.revenue?.[0] || entity.properties.assets?.[0] || "",
  "notes": `Datasets: ${entity.datasets?.join(", ")}`
}
```

### Aleph Directorship Query (for officers)
```javascript
// Fetch related directorships
const directorships = await aleph.searchEntity(companyName, {
  schema: "Directorship",
  "filter:organization": entity.id
});

// Map to officers
"officers": directorships.results.map(d => ({
  "type": d.properties.role?.[0]?.includes("Director") ? "director" :
          d.properties.role?.[0]?.includes("CEO") ? "executive" : "other",
  "name": d.properties.director?.[0] || "",
  "details": `Role: ${d.properties.role?.[0] || 'N/A'}, Start: ${d.properties.startDate?.[0] || 'Unknown'}${d.properties.endDate?.[0] ? `, End: ${d.properties.endDate[0]}` : ''}`,
  "source": "[AL]"
}))
```

---

## EDGAR (SEC) → Entity Template

### Source Data Structure
```json
{
  "cik": "0000320193",
  "entityType": "operating",
  "sic": "3571",
  "sicDescription": "Electronic Computers",
  "name": "Apple Inc.",
  "tickers": ["AAPL"],
  "exchanges": ["Nasdaq"],
  "ein": "942404110",
  "description": "...",
  "category": "Large accelerated filer",
  "fiscalYearEnd": "0930",
  "stateOfIncorporation": "CA",
  "stateOfIncorporationDescription": "CA",
  "addresses": {
    "mailing": {
      "street1": "ONE APPLE PARK WAY",
      "city": "CUPERTINO",
      "stateOrCountry": "CA",
      "zipCode": "95014"
    },
    "business": {
      "street1": "ONE APPLE PARK WAY",
      "city": "CUPERTINO",
      "stateOrCountry": "CA",
      "zipCode": "95014"
    }
  },
  "phone": "4089961010",
  "flags": "",
  "formerNames": []
}
```

### Field Mapping
```javascript
{
  "id": company.ein || company.cik,  // "942404110"
  "name": {
    "value": company.name,  // "Apple Inc."
    "variations": company.tickers?.join(", ") || "",  // "AAPL"
    "alias": company.formerNames?.map(f => f.name).join(", ") || "",
    "source": "[ED]"
  },
  "node_class": "entity",
  "type": "company",
  "about": {
    "company_number": company.cik,  // "0000320193"
    "incorporation_date": "",  // NOT PROVIDED - need to query filings
    "jurisdiction": company.stateOfIncorporation,  // "CA"
    "registered_address": {
      "value": `${company.addresses.business.street1}, ${company.addresses.business.city}, ${company.addresses.business.stateOrCountry} ${company.addresses.business.zipCode}`,
      "comment": "",
      "source": "[ED]"
    },
    "website": {
      "value": "",  // NOT PROVIDED
      "source": ""
    },
    "contact_details": {
      "phone": {
        "value": company.phone,  // "4089961010"
        "source": "[ED]"
      },
      "email": {"value": "", "source": ""}  // NOT PROVIDED
    },
    "source": "[ED]"
  },
  "officers": [],  // Requires parsing recent 10-K/DEF14A filings
  "ownership_structure": {
    "shareholders": "",  // Requires parsing Schedule 13D/13G filings
    "beneficial_owners": "",  // Requires parsing DEF14A proxy statements
    "source": ""
  },
  "financial_results": `SIC: ${company.sicDescription} (${company.sic}), Fiscal Year End: ${company.fiscalYearEnd}, Category: ${company.category}`,
  "filings": [],  // Requires separate filings API query
  "notes": `CIK: ${company.cik}, EIN: ${company.ein}, Exchanges: ${company.exchanges?.join(", ")}`
}
```

---

## Source Coverage Summary

| Field | OpenCorporates | Aleph | EDGAR |
|-------|----------------|-------|-------|
| **name** | ✅ Full | ✅ Full | ✅ Full |
| **company_number** | ✅ | ✅ | ✅ (CIK) |
| **incorporation_date** | ✅ | ✅ | ❌ |
| **jurisdiction** | ✅ | ✅ | ✅ (State) |
| **registered_address** | ✅ | ✅ | ✅ |
| **website** | ❌ | ✅ | ❌ |
| **phone** | ❌ | ✅ | ✅ |
| **email** | ❌ | ✅ | ❌ |
| **officers** | ✅ (some) | ✅ (via Directorship) | ✅ (via filings) |
| **ownership** | ❌ | ✅ (some) | ✅ (via filings) |
| **financial_results** | ❌ | ✅ (some) | ✅ (via filings) |

---

## Implementation Priority

### Phase 1: Deterministic Mapping (FAST PATH)
Map all directly available fields from each source:
- OpenCorporates: name, company_number, jurisdiction, incorporation_date, address, officers
- Aleph: name, company_number, jurisdiction, incorporation_date, address, website, phone, email
- EDGAR: name, CIK, jurisdiction, address, phone

### Phase 2: Haiku Merging (SMART PATH)
Use Claude Haiku 4.5 to:
1. Deduplicate officers across sources
2. Merge contradicting addresses ("123 Main St [OC]" vs "123 Main Street, Suite 100 [AL]")
3. Fill gaps (use Aleph website when OC doesn't have it)
4. Format ownership_structure as readable text
5. Add source badges to ALL fields

### Phase 3: Advanced Fetching (COMPREHENSIVE PATH)
For complete data:
- Aleph: Query Directorship schema for officers/directors
- EDGAR: Parse recent 10-K/DEF14A for officers and ownership
- OpenCorporates: Query officer detail endpoints
