# Input-Output Routing Matrix

## Purpose
Smart routing based on:
1. **What we're searching for** (target entity type)
2. **What data we have** (available inputs)
3. **What country** (jurisdiction)

## Input Types Available

### Basic Inputs
- `company_name` - Company name search
- `company_id` - Official company registration number
- `person_name` - Individual's name
- `person_id` - Official person identifier
- `generic_query` - Free text search

### Enhanced Inputs (when available)
- `person_dob` - Date of birth (enables better person matching)
- `company_jurisdiction` - Specific jurisdiction code
- `company_country` - Country code

## Output Schemas

### Company
Fields: company_name, company_id, company_address, company_country, company_jurisdiction, company_status, company_incorporation_date, company_dissolution_date, company_website, company_owner_person, company_owner_company

### Person
Fields: person_name, person_id, person_dob, person_nationality, person_address, person_country, person_website

### Entity (Generic)
Fields: id, schema, caption, countries, addresses, websites, publisher, collection_id

## Routing Rules

### Rule 1: Country-Specific Company Search
**IF**: Have `company_name` + `country_code`
**THEN**: Route to country-specific collections

**Examples**:
- GB + company_name → Collections 809 (Companies House), 2053 (PSC), fca_register (FCA)
- DE + company_name → Collection 1027 (German Registry)
- MX + company_name → Collection 506 (Personas de Interes)

### Rule 2: Company with ID (Highest Precision)
**IF**: Have `company_id` + `country_code`
**THEN**: Direct fetch from official registry

**Examples**:
- GB + company_id "12345678" → Collection 809 (Companies House) - returns full company profile + PSC data
- GB + company_id → Also check Collection 2053 for beneficial ownership

### Rule 3: Person Search
**IF**: Have `person_name` + `country_code`
**THEN**: Route to relevant person collections

**Examples**:
- GB + person_name → Collections 809 (directors), 2302 (disqualified directors), 1303 (sanctions), 153 (parliamentary)
- GB + person_name + person_dob → Higher precision matching in Collection 2302

### Rule 4: Person with ID
**IF**: Have `person_id` + `country_code`
**THEN**: Direct person lookup

**Examples**:
- GB + person_id → Collection 2302 (Disqualified Directors)

### Rule 5: Ownership/Control Search
**IF**: Target is "beneficial ownership" or "PSC"
**THEN**: Route to specific ownership collections

**Examples**:
- GB + company_name + target="ownership" → Collection 2053 (UK PSC) - returns company_owner_person, company_owner_company

### Rule 6: Regulatory/Sanctions Search
**IF**: Need regulatory or sanctions check
**THEN**: Route to specialized collections

**Examples**:
- GB + company_name + check="regulatory" → fca_register (returns fca_permissions, fca_disciplinary_history)
- GB + person_name + check="sanctions" → Collection 1303 (HM Treasury Sanctions)

### Rule 7: Fallback to Generic
**IF**: No country specified OR no specific match
**THEN**: Use generic_query across all collections

## Priority Matrix

When multiple inputs available, priority:
1. **company_id + country** (highest precision)
2. **person_id + person_dob + country**
3. **company_name + country**
4. **person_name + person_dob + country**
5. **company_name only** (generic search)
6. **person_name only** (generic search)

## Collection Capabilities by Country

### GB (United Kingdom) - 6 collections
| Collection | ID | Input Types | Output Schema | Special Features |
|------------|-----|-------------|---------------|------------------|
| Companies House | 809 | company_name, company_id, person_name, person_id | Company, Person | Full registry + directors |
| PSC | 2053 | company_name, company_id, person_name, person_id | Company, Person | Beneficial ownership |
| Disqualified Directors | 2302 | person_name, person_id | Person | person_dob available |
| HM Treasury Sanctions | 1303 | person_name, person_id | Person | Sanctions screening |
| Parliamentary Inquiries | 153 | person_name, person_id | Person | Political exposure |
| FCA Register | fca_register | company_name, company_id, person_name, person_id | Company, Person | fca_permissions, fca_disciplinary_history |

### DE (Germany) - 1 collection
| Collection | ID | Input Types | Output Schema | Special Features |
|------------|-----|-------------|---------------|------------------|
| German Registry | 1027 | company_name | Company | OpenCorporates 2019 data |

### MX (Mexico) - 1 collection
| Collection | ID | Input Types | Output Schema | Special Features |
|------------|-----|-------------|---------------|------------------|
| Personas de Interes | 506 | company_name, company_id, person_name, person_id | Company, Person | 2014 dataset |

## Smart Routing Examples

### Example 1: UK Company with Ownership
**User provides**:
- company_name: "Revolut Ltd"
- country: "GB"
- want: "ownership structure"

**Router executes**:
1. Collection 809 (Companies House) - get company profile
2. Collection 2053 (PSC) - get beneficial owners
3. Returns: company_owner_person, company_owner_company from both

### Example 2: Person Due Diligence
**User provides**:
- person_name: "John Smith"
- person_dob: "1985-03-15"
- country: "GB"

**Router executes**:
1. Collection 2302 (Disqualified Directors) - check if disqualified
2. Collection 1303 (HM Treasury Sanctions) - sanctions check
3. Collection 809 (Companies House) - find directorships
4. Collection 153 (Parliamentary) - check political exposure

### Example 3: Regulatory Check
**User provides**:
- company_name: "Barclays Bank"
- country: "GB"
- check: "regulatory"

**Router executes**:
1. fca_register - get FCA permissions and disciplinary history
2. Collection 809 - get company status
3. Returns: fca_permissions, fca_requirements, fca_disciplinary_history

### Example 4: Cross-Border Search
**User provides**:
- company_name: "Deutsche Bank"
- countries: ["DE", "GB"]

**Router executes**:
1. DE Collection 1027 - German registry
2. GB Collection 809 - UK subsidiary/branch
3. GB fca_register - UK regulatory status

## Implementation Strategy

```python
class SmartRouter:
    def route(self, inputs: dict, target: str) -> List[SearchTask]:
        """
        inputs = {
            'company_name': 'Revolut Ltd',
            'country': 'GB',
            'person_dob': '1985-03-15'  # optional
        }
        target = 'ownership' | 'regulatory' | 'person_dd' | 'company_profile'

        Returns list of SearchTask with:
        - collection_id
        - input_type
        - filters
        - expected_output_schema
        """
```

This enables the Corporella web app to intelligently route searches to the right sources based on what the user provides and what they're looking for!
