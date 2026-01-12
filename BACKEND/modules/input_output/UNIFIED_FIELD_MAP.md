# UNIFIED FIELD MAP - All Indices to 5 Entity Types

## ENTITY TYPE 1: DOMAIN

| Index | Field | Type | Notes |
|-------|-------|------|-------|
| **domains_unified** | domain | keyword | PRIMARY |
| domains_unified | url | keyword | |
| domains_unified | tld | keyword | FILTER |
| domains_unified | title | text | |
| domains_unified | description | text | |
| domains_unified | rank | integer | RANKING |
| domains_unified | tld_rank | integer | RANKING |
| domains_unified | tranco_rank | integer | RANKING |
| domains_unified | majestic_rank | integer | RANKING |
| domains_unified | authority_rank | integer | RANKING |
| domains_unified | authority_score | float | RANKING |
| domains_unified | best_rank | integer | RANKING |
| domains_unified | trust_flow | integer | QUALITY |
| domains_unified | citation_flow | integer | QUALITY |
| domains_unified | backlinks_fetched | integer | LINKS |
| domains_unified | backlinks_ips | integer | LINKS |
| domains_unified | backlinks_subnets | integer | LINKS |
| domains_unified | backlinks_tier | keyword | LINKS |
| domains_unified | ref_ips | integer | LINKS |
| domains_unified | ref_subnets | integer | LINKS |
| domains_unified | categories | keyword[] | CATEGORY |
| domains_unified | all_categories | keyword[] | CATEGORY |
| domains_unified | primary_category | keyword | CATEGORY |
| domains_unified | news_categories | keyword[] | CATEGORY |
| domains_unified | bang_categories | keyword[] | CATEGORY |
| domains_unified | bang_subcategories | keyword[] | CATEGORY |
| domains_unified | curlie_paths | keyword[] | CATEGORY |
| domains_unified | curlie_top_categories | keyword[] | CATEGORY |
| domains_unified | country | keyword | GEO |
| domains_unified | countries | keyword[] | GEO |
| domains_unified | primary_country | keyword | GEO |
| domains_unified | lang | keyword | LANG |
| domains_unified | languages | keyword[] | LANG |
| domains_unified | has_search_template | boolean | SEARCH |
| domains_unified | search_url | keyword | SEARCH |
| domains_unified | search_url_templates | keyword[] | SEARCH |
| domains_unified | entity_types | keyword[] | WDC |
| domains_unified | schema_types | keyword[] | WDC |
| domains_unified | wdc_entity_count | integer | WDC |
| domains_unified | wdc_entity_names | keyword[] | WDC |
| domains_unified | wdc_confidence | float | WDC |
| domains_unified | company_name | text | COMPANY_LINK |
| domains_unified | company_industry | keyword | COMPANY_LINK |
| domains_unified | company_linkedin_url | keyword | COMPANY_LINK |
| domains_unified | linked_companies | keyword[] | COMPANY_LINK |
| domains_unified | linked_people | keyword[] | PERSON_LINK |
| domains_unified | social_links | keyword[] | SOCIAL |
| domains_unified | sources | keyword[] | PROVENANCE |
| domains_unified | indexed_at | date | META |
| **top_domains** | domain | keyword | PRIMARY |
| top_domains | rank | integer | RANKING |
| top_domains | tld_rank | integer | RANKING |
| top_domains | backlinks_ips | integer | LINKS |
| top_domains | backlinks_subnets | integer | LINKS |
| top_domains | tld | keyword | FILTER |
| top_domains | country | keyword | GEO |
| top_domains | lang | keyword | LANG |
| **atlas_unified_domains** | domain | keyword | PRIMARY |
| atlas_unified_domains | tld | keyword | FILTER |
| atlas_unified_domains | tranco_rank | integer | RANKING |
| atlas_unified_domains | majestic_rank | integer | RANKING |
| atlas_unified_domains | authority_rank | integer | RANKING |
| atlas_unified_domains | trust_flow | integer | QUALITY |
| atlas_unified_domains | citation_flow | integer | QUALITY |
| atlas_unified_domains | categories | keyword[] | CATEGORY |
| atlas_unified_domains | countries | keyword[] | GEO |
| atlas_unified_domains | languages | keyword[] | LANG |
| **unified_domain_profiles** | domain | keyword | PRIMARY |
| unified_domain_profiles | tld | keyword | FILTER |
| unified_domain_profiles | tranco_rank | integer | RANKING |
| unified_domain_profiles | majestic_rank | integer | RANKING |
| unified_domain_profiles | majestic_tld_rank | integer | RANKING |
| unified_domain_profiles | best_rank | integer | RANKING |
| unified_domain_profiles | authority_score | float | RANKING |
| unified_domain_profiles | ref_ips | integer | LINKS |
| unified_domain_profiles | ref_subnets | integer | LINKS |
| unified_domain_profiles | bang_categories | keyword[] | CATEGORY |
| unified_domain_profiles | bang_subcategories | keyword[] | CATEGORY |
| unified_domain_profiles | curlie_paths | keyword[] | CATEGORY |
| unified_domain_profiles | news_categories | keyword[] | CATEGORY |
| unified_domain_profiles | all_categories | keyword[] | CATEGORY |
| unified_domain_profiles | countries | keyword[] | GEO |
| unified_domain_profiles | primary_country | keyword | GEO |
| unified_domain_profiles | languages | keyword[] | LANG |
| unified_domain_profiles | has_search_shortcut | boolean | SEARCH |
| unified_domain_profiles | search_url_templates | keyword[] | SEARCH |
| **wdc-domain-profiles** | domain | keyword | PRIMARY |
| wdc-domain-profiles | tld | keyword | FILTER |
| wdc-domain-profiles | entity_type_counts | object | WDC |
| wdc-domain-profiles | primary_entity_type | keyword | WDC |
| wdc-domain-profiles | entity_type_tags | keyword[] | WDC |
| wdc-domain-profiles | language_counts | object | LANG |
| wdc-domain-profiles | primary_language | keyword | LANG |
| wdc-domain-profiles | language_tags | keyword[] | LANG |
| wdc-domain-profiles | country_counts | object | GEO |
| wdc-domain-profiles | primary_country | keyword | GEO |
| wdc-domain-profiles | address_countries | keyword[] | GEO |
| wdc-domain-profiles | total_entities | integer | WDC |
| wdc-domain-profiles | total_quads | integer | WDC |
| wdc-domain-profiles | confidence_score | float | QUALITY |
| **breach_records** | email_domain | keyword | DOMAIN_FROM_EMAIL |
| **linkedin_unified** | company_domain | keyword | DOMAIN_FROM_COMPANY |
| **linkedin_unified** | domain | keyword | DOMAIN_FROM_COMPANY |
| **affiliate_linkedin_companies** | domain | keyword | DOMAIN_FROM_COMPANY |
| **companies_unified** | domain | keyword | DOMAIN_FROM_COMPANY |
| **companies_unified** | domains | keyword[] | DOMAIN_FROM_COMPANY |
| **wdc-localbusiness-entities** | domain | keyword | DOMAIN_FROM_ENTITY |
| **wdc-organization-entities** | domain | keyword | DOMAIN_FROM_ENTITY |
| **wdc-person-entities** | domain | keyword | DOMAIN_FROM_ENTITY |
| **indom** | domain | keyword | PRIMARY |

---

## ENTITY TYPE 2: COMPANY / ORGANISATION

| Index | Field | Type | Notes |
|-------|-------|------|-------|
| **companies_unified** | company_id | keyword | PRIMARY_ID |
| companies_unified | name | text | NAME |
| companies_unified | legal_name | text | NAME |
| companies_unified | alternate_names | keyword[] | NAME |
| companies_unified | company_number | keyword | REG_ID |
| companies_unified | jurisdiction_code | keyword | JURISDICTION |
| companies_unified | entity_type | keyword | TYPE |
| companies_unified | industry | keyword | INDUSTRY |
| companies_unified | naics | keyword | INDUSTRY |
| companies_unified | founding_date | date | DATE |
| companies_unified | number_of_employees | integer | SIZE |
| companies_unified | street_address | text | ADDRESS |
| companies_unified | city | keyword | ADDRESS |
| companies_unified | region | keyword | ADDRESS |
| companies_unified | postal_code | keyword | ADDRESS |
| companies_unified | country | keyword | ADDRESS |
| companies_unified | telephone | keyword | PHONE_LINK |
| companies_unified | fax_number | keyword | PHONE_LINK |
| companies_unified | emails | keyword[] | EMAIL_LINK |
| companies_unified | domain | keyword | DOMAIN_LINK |
| companies_unified | domains | keyword[] | DOMAIN_LINK |
| companies_unified | linkedin_url | keyword | SOCIAL |
| companies_unified | website_url | keyword | DOMAIN_LINK |
| companies_unified | same_as | keyword[] | SAME_AS |
| companies_unified | parent_organization | keyword | OWNERSHIP |
| companies_unified | sub_organizations | keyword[] | OWNERSHIP |
| companies_unified | duns | keyword | EXT_ID |
| companies_unified | tax_id | keyword | EXT_ID |
| companies_unified | vat_id | keyword | EXT_ID |
| **linkedin_unified** | company_name | text | NAME |
| linkedin_unified | linkedin_id | keyword | PRIMARY_ID |
| linkedin_unified | linkedin_url | keyword | SOCIAL |
| linkedin_unified | company_domain | keyword | DOMAIN_LINK |
| linkedin_unified | industry | keyword | INDUSTRY |
| linkedin_unified | company_size | keyword | SIZE |
| linkedin_unified | founded | keyword | DATE |
| linkedin_unified | specialties | keyword[] | INDUSTRY |
| linkedin_unified | country | keyword | ADDRESS |
| linkedin_unified | location | text | ADDRESS |
| **affiliate_linkedin_companies** | company_name | text | NAME |
| affiliate_linkedin_companies | linkedin_url | keyword | SOCIAL |
| affiliate_linkedin_companies | domain | keyword | DOMAIN_LINK |
| affiliate_linkedin_companies | website_url | keyword | DOMAIN_LINK |
| affiliate_linkedin_companies | industry | keyword | INDUSTRY |
| **openownership** | subject_name | text | NAME (owned company) |
| openownership | subject_id | keyword | PRIMARY_ID |
| openownership | company_number | keyword | REG_ID |
| openownership | jurisdiction | keyword | JURISDICTION |
| openownership | entity_type | keyword | TYPE |
| openownership | incorporation_date | date | DATE |
| openownership | dissolution_date | date | DATE |
| openownership | address | text | ADDRESS |
| openownership | address_country | keyword | ADDRESS |
| openownership | country | keyword | ADDRESS |
| openownership | interested_party_name | text | OWNER (person or company) |
| openownership | interested_party_id | keyword | OWNER_ID |
| openownership | ownership_percentage | float | OWNERSHIP |
| openownership | voting_percentage | float | OWNERSHIP |
| openownership | control_types | keyword[] | OWNERSHIP |
| openownership | statement_date | date | DATE |
| **uk_ccod** | proprietor_name_1 | text | NAME (property owner) |
| uk_ccod | proprietor_name_2 | text | NAME |
| uk_ccod | proprietorship_category_1 | keyword | TYPE |
| uk_ccod | proprietorship_category_2 | keyword | TYPE |
| uk_ccod | company_reg_no_1 | keyword | REG_ID |
| uk_ccod | company_reg_no_2 | keyword | REG_ID |
| uk_ccod | proprietor_address_1 | text | ADDRESS |
| uk_ccod | proprietor_address_2 | text | ADDRESS |
| **uk_ocod** | proprietor_name | text | NAME (offshore owner) |
| uk_ocod | country_incorporated | keyword | JURISDICTION |
| uk_ocod | proprietor_address | text | ADDRESS |
| **uk_addresses** | owner_name | text | NAME |
| uk_addresses | owner_type | keyword | TYPE |
| uk_addresses | company_number | keyword | REG_ID |
| uk_addresses | country_incorporated | keyword | JURISDICTION |
| uk_addresses | jurisdiction | keyword | JURISDICTION |
| **wdc-organization-entities** | name | text | NAME |
| wdc-organization-entities | legalName | text | NAME |
| wdc-organization-entities | alternateName | keyword[] | NAME |
| wdc-organization-entities | duns | keyword | EXT_ID |
| wdc-organization-entities | naics | keyword | INDUSTRY |
| wdc-organization-entities | isicV4 | keyword | INDUSTRY |
| wdc-organization-entities | numberOfEmployees | integer | SIZE |
| wdc-organization-entities | foundingDate | date | DATE |
| wdc-organization-entities | dissolutionDate | date | DATE |
| wdc-organization-entities | address | text | ADDRESS |
| wdc-organization-entities | telephone | keyword | PHONE_LINK |
| wdc-organization-entities | faxNumber | keyword | PHONE_LINK |
| wdc-organization-entities | email | keyword | EMAIL_LINK |
| wdc-organization-entities | sameAs | keyword[] | SAME_AS |
| wdc-organization-entities | parentOrganization | keyword | OWNERSHIP |
| wdc-organization-entities | subOrganization | keyword[] | OWNERSHIP |
| **wdc-localbusiness-entities** | name | text | NAME |
| wdc-localbusiness-entities | legalName | text | NAME |
| wdc-localbusiness-entities | telephone | keyword | PHONE_LINK |
| wdc-localbusiness-entities | faxNumber | keyword | PHONE_LINK |
| wdc-localbusiness-entities | email | keyword | EMAIL_LINK |
| wdc-localbusiness-entities | address | text | ADDRESS |
| wdc-localbusiness-entities | geo | object | GEO |
| wdc-localbusiness-entities | sameAs | keyword[] | SAME_AS |
| wdc-localbusiness-entities | openingHours | keyword[] | BUSINESS |
| wdc-localbusiness-entities | priceRange | keyword | BUSINESS |
| wdc-localbusiness-entities | paymentAccepted | keyword[] | BUSINESS |
| **wdc-governmentorganization-entities** | name | text | NAME |
| wdc-governmentorganization-entities | legalName | text | NAME |
| wdc-governmentorganization-entities | duns | keyword | EXT_ID |
| wdc-governmentorganization-entities | naics | keyword | INDUSTRY |
| wdc-governmentorganization-entities | telephone | keyword | PHONE_LINK |
| wdc-governmentorganization-entities | faxNumber | keyword | PHONE_LINK |
| wdc-governmentorganization-entities | email | keyword | EMAIL_LINK |
| wdc-governmentorganization-entities | address | text | ADDRESS |
| **domains_unified** | company_name | text | NAME (from domain) |
| domains_unified | company_industry | keyword | INDUSTRY |
| domains_unified | company_linkedin_url | keyword | SOCIAL |
| domains_unified | linked_companies | keyword[] | RELATED |

---

## ENTITY TYPE 3: EMAIL

| Index | Field | Type | Notes |
|-------|-------|------|-------|
| **breach_records** | email | keyword | PRIMARY |
| breach_records | email_domain | keyword | DOMAIN_LINK |
| breach_records | local_part | keyword | LOCAL_PART |
| breach_records | name | text | PERSON_LINK |
| breach_records | breach_name | keyword | SOURCE |
| breach_records | breach_year | integer | DATE |
| breach_records | password_hash | keyword | SENSITIVE |
| breach_records | hash_type | keyword | META |
| breach_records | ip_address | keyword | IP_LINK |
| breach_records | phone | keyword | PHONE_LINK |
| breach_records | address | text | ADDRESS |
| breach_records | city | keyword | ADDRESS |
| breach_records | state | keyword | ADDRESS |
| breach_records | country | keyword | ADDRESS |
| **nexus_breach_records** | parsed_fields.email | keyword | PRIMARY |
| nexus_breach_records | parsed_fields.domain | keyword | DOMAIN_LINK |
| nexus_breach_records | breach_name | keyword | SOURCE |
| nexus_breach_records | node_ids | keyword[] | GRAPH_LINK |
| **kazaword_emails** | from.email | keyword | PRIMARY (sender) |
| kazaword_emails | from.name | text | PERSON_LINK |
| kazaword_emails | to[].email | keyword | PRIMARY (recipient) |
| kazaword_emails | to[].name | text | PERSON_LINK |
| kazaword_emails | cc[].email | keyword | SECONDARY |
| kazaword_emails | bcc[].email | keyword | SECONDARY |
| kazaword_emails | all_emails | keyword[] | ALL |
| kazaword_emails | all_recipients | keyword[] | ALL_RECIPIENTS |
| kazaword_emails | subject | text | CONTENT |
| kazaword_emails | body_text | text | CONTENT |
| kazaword_emails | date | date | DATE |
| kazaword_emails | originating_ip | keyword | IP_LINK |
| kazaword_emails | attachments | nested | FILES |
| kazaword_emails | source_archive | keyword | SOURCE |
| **companies_unified** | emails | keyword[] | COMPANY_EMAILS |
| **persons_unified** | email | keyword | PERSON_EMAIL |
| **persons_unified** | emails | keyword[] | PERSON_EMAILS |
| **persons_unified** | email_ids | keyword[] | EMAIL_IDS |
| **wdc-organization-entities** | email | keyword | ORG_EMAIL |
| **wdc-localbusiness-entities** | email | keyword | BUSINESS_EMAIL |
| **wdc-governmentorganization-entities** | email | keyword | GOV_EMAIL |

---

## ENTITY TYPE 4: PHONE NUMBER

| Index | Field | Type | Notes |
|-------|-------|------|-------|
| **phones_unified** | phone_id | keyword | PRIMARY_ID |
| phones_unified | phone_e164 | keyword | PRIMARY (normalized) |
| phones_unified | phone_raw | keyword | RAW |
| phones_unified | country_code | keyword | COUNTRY |
| phones_unified | area_code | keyword | AREA |
| phones_unified | local_number | keyword | LOCAL |
| phones_unified | phone_type | keyword | TYPE |
| phones_unified | person_names | keyword[] | PERSON_LINK |
| phones_unified | person_ids | keyword[] | PERSON_LINK |
| phones_unified | organization_names | keyword[] | COMPANY_LINK |
| phones_unified | company_ids | keyword[] | COMPANY_LINK |
| phones_unified | city | keyword | GEO |
| phones_unified | region | keyword | GEO |
| phones_unified | country | keyword | GEO |
| phones_unified | breach_count | integer | BREACH |
| phones_unified | breach_names | keyword[] | BREACH |
| phones_unified | sources | keyword[] | PROVENANCE |
| **breach_records** | phone | keyword | FROM_BREACH |
| **companies_unified** | telephone | keyword | COMPANY_PHONE |
| **companies_unified** | fax_number | keyword | COMPANY_FAX |
| **persons_unified** | telephone | keyword | PERSON_PHONE |
| **persons_unified** | telephones | keyword[] | PERSON_PHONES |
| **persons_unified** | phone_ids | keyword[] | PHONE_IDS |
| **wdc-organization-entities** | telephone | keyword | ORG_PHONE |
| **wdc-organization-entities** | faxNumber | keyword | ORG_FAX |
| **wdc-localbusiness-entities** | telephone | keyword | BUSINESS_PHONE |
| **wdc-localbusiness-entities** | faxNumber | keyword | BUSINESS_FAX |
| **wdc-localbusiness-entities** | phone | keyword | BUSINESS_PHONE |
| **wdc-governmentorganization-entities** | telephone | keyword | GOV_PHONE |
| **wdc-governmentorganization-entities** | faxNumber | keyword | GOV_FAX |
| **wdc-person-entities** | Telephone | keyword | PERSON_PHONE |
| **wdc-person-entities** | telephone | keyword | PERSON_PHONE |

---

## ENTITY TYPE 5: PERSON

| Index | Field | Type | Notes |
|-------|-------|------|-------|
| **persons_unified** | person_id | keyword | PRIMARY_ID |
| persons_unified | full_name | text | NAME |
| persons_unified | given_name | keyword | NAME |
| persons_unified | family_name | keyword | NAME |
| persons_unified | alternate_names | keyword[] | NAME |
| persons_unified | email | keyword | EMAIL_LINK |
| persons_unified | emails | keyword[] | EMAIL_LINK |
| persons_unified | telephone | keyword | PHONE_LINK |
| persons_unified | telephones | keyword[] | PHONE_LINK |
| persons_unified | job_title | keyword | EMPLOYMENT |
| persons_unified | job_titles | keyword[] | EMPLOYMENT |
| persons_unified | employer | keyword | COMPANY_LINK |
| persons_unified | employers | keyword[] | COMPANY_LINK |
| persons_unified | employer_domains | keyword[] | DOMAIN_LINK |
| persons_unified | linkedin_url | keyword | SOCIAL |
| persons_unified | same_as | keyword[] | SAME_AS |
| persons_unified | nationality | keyword | GEO |
| persons_unified | country | keyword | GEO |
| persons_unified | address_locality | keyword | ADDRESS |
| persons_unified | has_password_exposed | boolean | BREACH |
| persons_unified | has_phone_exposed | boolean | BREACH |
| persons_unified | breach_count | integer | BREACH |
| persons_unified | breach_names | keyword[] | BREACH |
| persons_unified | sources | keyword[] | PROVENANCE |
| **wdc-person-entities** | name | text | NAME |
| wdc-person-entities | givenName | keyword | NAME |
| wdc-person-entities | familyName | keyword | NAME |
| wdc-person-entities | additionalName | keyword | NAME |
| wdc-person-entities | alternateName | keyword[] | NAME |
| wdc-person-entities | email | keyword | EMAIL_LINK |
| wdc-person-entities | telephone | keyword | PHONE_LINK |
| wdc-person-entities | Telephone | keyword | PHONE_LINK |
| wdc-person-entities | jobTitle | keyword | EMPLOYMENT |
| wdc-person-entities | worksFor | keyword | COMPANY_LINK |
| wdc-person-entities | WorksFor | keyword | COMPANY_LINK |
| wdc-person-entities | affiliation | keyword | COMPANY_LINK |
| wdc-person-entities | alumniOf | keyword | EDUCATION |
| wdc-person-entities | birthDate | date | DATE |
| wdc-person-entities | birthPlace | keyword | GEO |
| wdc-person-entities | deathDate | date | DATE |
| wdc-person-entities | nationality | keyword | GEO |
| wdc-person-entities | address | text | ADDRESS |
| wdc-person-entities | sameAs | keyword[] | SAME_AS |
| wdc-person-entities | SameAs | keyword[] | SAME_AS |
| **linkedin_unified** | person_name | text | NAME |
| linkedin_unified | person_id | keyword | PRIMARY_ID |
| linkedin_unified | profile_slug | keyword | LINKEDIN_ID |
| linkedin_unified | linkedin_url | keyword | SOCIAL |
| linkedin_unified | job_title | keyword | EMPLOYMENT |
| linkedin_unified | headline | text | EMPLOYMENT |
| linkedin_unified | company_name | keyword | COMPANY_LINK |
| linkedin_unified | industry | keyword | INDUSTRY |
| linkedin_unified | location | text | ADDRESS |
| linkedin_unified | country | keyword | GEO |
| **openownership** | interested_party_name | text | NAME (as owner) |
| openownership | interested_party_id | keyword | PRIMARY_ID |
| **breach_records** | name | text | NAME (from breach) |
| **kazaword_emails** | from.name | text | NAME (email sender) |
| **kazaword_emails** | to[].name | text | NAME (email recipient) |
| **domains_unified** | linked_people | keyword[] | NAMES (from domain) |

---

## DOMAIN FILTER FIELDS (Maximum Filtering)

| Field | Indices | Filter Type |
|-------|---------|-------------|
| **tld** | domains_unified, top_domains, atlas_unified_domains, unified_domain_profiles, wdc-domain-profiles | EXACT |
| **country** | domains_unified, top_domains | EXACT |
| **countries** | domains_unified, atlas_unified_domains, unified_domain_profiles | MULTI |
| **primary_country** | domains_unified, atlas_unified_domains, unified_domain_profiles, wdc-domain-profiles | EXACT |
| **address_countries** | wdc-domain-profiles | MULTI |
| **lang** | domains_unified, top_domains | EXACT |
| **languages** | domains_unified, atlas_unified_domains, unified_domain_profiles | MULTI |
| **primary_language** | wdc-domain-profiles | EXACT |
| **categories** | domains_unified, top_domains, atlas_unified_domains | MULTI |
| **all_categories** | domains_unified, unified_domain_profiles | MULTI |
| **primary_category** | domains_unified, atlas_unified_domains | EXACT |
| **news_categories** | domains_unified, unified_domain_profiles | MULTI |
| **bang_categories** | domains_unified, unified_domain_profiles | MULTI |
| **bang_subcategories** | domains_unified, unified_domain_profiles | MULTI |
| **curlie_paths** | domains_unified, unified_domain_profiles | MULTI |
| **curlie_top_categories** | domains_unified | MULTI |
| **entity_types** | domains_unified, atlas_unified_domains | MULTI |
| **schema_types** | domains_unified, atlas_unified_domains | MULTI |
| **entity_type_tags** | wdc-domain-profiles | MULTI |
| **primary_entity_type** | wdc-domain-profiles | EXACT |
| **rank** | domains_unified, top_domains | RANGE |
| **tld_rank** | domains_unified, top_domains | RANGE |
| **tranco_rank** | domains_unified, atlas_unified_domains, unified_domain_profiles | RANGE |
| **majestic_rank** | domains_unified, atlas_unified_domains, unified_domain_profiles | RANGE |
| **majestic_tld_rank** | domains_unified, unified_domain_profiles | RANGE |
| **authority_rank** | domains_unified, atlas_unified_domains | RANGE |
| **authority_score** | domains_unified, unified_domain_profiles | RANGE |
| **best_rank** | domains_unified, unified_domain_profiles | RANGE |
| **trust_flow** | domains_unified, atlas_unified_domains | RANGE |
| **citation_flow** | domains_unified, atlas_unified_domains | RANGE |
| **backlinks_ips** | domains_unified, top_domains | RANGE |
| **backlinks_subnets** | domains_unified, top_domains | RANGE |
| **ref_ips** | domains_unified, unified_domain_profiles | RANGE |
| **ref_subnets** | domains_unified, unified_domain_profiles | RANGE |
| **has_search_template** | domains_unified, atlas_unified_domains | BOOLEAN |
| **has_search_shortcut** | domains_unified, unified_domain_profiles | BOOLEAN |
| **wdc_entity_count** | domains_unified | RANGE |
| **wdc_confidence** | domains_unified | RANGE |
| **total_entities** | wdc-domain-profiles | RANGE |
| **total_quads** | wdc-domain-profiles | RANGE |
| **confidence_score** | wdc-domain-profiles | RANGE |
| **sources** | domains_unified, top_domains, unified_domain_profiles | MULTI (provenance) |

---

## OVERLAP DETECTION KEYS

For finding the same entity across indices:

| Entity Type | Primary Key Field | Secondary Match Fields |
|-------------|-------------------|------------------------|
| **DOMAIN** | domain | url |
| **COMPANY** | company_number + jurisdiction | name (fuzzy), linkedin_url, domain |
| **EMAIL** | email (lowercase) | local_part + email_domain |
| **PHONE** | phone_e164 (normalized) | phone_raw, country_code + local_number |
| **PERSON** | linkedin_url | full_name (fuzzy), email, same_as[] |

