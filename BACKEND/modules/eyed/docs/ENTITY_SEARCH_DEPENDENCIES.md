# Entity Search Dependencies & References

## Complete Dependency Map for `entity_search.py`

### 1. **Python Standard Libraries**

- `sys` - System-specific parameters
- `os` - Operating system interface
- `json` - JSON encoder/decoder
- `asyncio` - Asynchronous I/O
- `re` - Regular expression operations
- `uuid` - UUID generation
- `datetime` - Date and time handling
- `pathlib.Path` - Object-oriented filesystem paths
- `typing` - Type hints (Dict, List, Any, Optional)
- `time` - Time-related functions
- `traceback` - Stack trace extraction

### 2. **EYE-D Core Modules** (External)

**Location:** `../EYE-D/` directory

- `unified_osint.UnifiedSearcher` - Main OSINT search aggregator class
- `ip_geolocation.IPGeolocation` - IP geolocation lookups

### 3. **Entity Storage System**

**Location:** `../Indexer/`

- `entity_graph_storage_v2.EntityGraphStorageV2` - Graph database for entities and relationships

### 4. **AI/ML Integration**

**Location:** `../TOOLS/`

- `openai_chatgpt.chat_sync` - Synchronous ChatGPT interface
- `openai_chatgpt.analyze` - AI analysis function
- `openai_chatgpt.GPT5_MODELS` - GPT-5 model configurations

### 5. **Entity Extraction System**

**Location:** `../entities/`

- `central_extractor.CentralEntityExtractor` - Central entity extraction manager
- `central_extractor.ExtractionMethod` - Extraction method enumeration

## Class Methods & Internal Functions

### **Main Class: `EyeDSearchHandler`**

#### **Public Search Methods:**

- `search_email(email: str)` - Email OSINT search
- `search_phone(phone: str)` - Phone number search
- `search_people(person_name: str)` - People/name search
- `search_password(password: str)` - Password breach search
- `search_linkedin(linkedin_url: str)` - LinkedIn profile search
- `search_whois(domain: str)` - WHOIS domain search
- `search_username(username: str)` - Username search
- `search_ip(ip_address: str)` - IP address geolocation

#### **Internal Helper Methods:**

- `_extract_entities_from_data(data, osint_type)` - Main entity extraction router
- `_extract_whois_entities(data)` - WHOIS-specific entity extraction
- `_extract_dehashed_entities(data)` - DeHashed breach data extraction
- `_extract_osint_industries_entities(data)` - OSINT Industries extraction
- `_extract_generic_entities(data, osint_type)` - Generic entity extraction
- `_fallback_entity_extraction(data)` - Fallback extraction without AI
- `_enhance_entity_context(entity, osint_type, query, all_entities)` - Add context to entities
- `_map_subtype_to_entity_type(subtype)` - Map search subtypes to entity types
- `_map_entity_type_to_storage(entity_type)` - Map entity types for storage
- `_detect_search_type(keyword)` - Detect search type from query
- `_convert_results(results)` - Convert results to standard format

#### **Utility Methods:**

- `extract_query_value(query, search_type)` - Clean query string
- `store_results(results)` - Store results in graph database
- `run_search()` - Main search runner

## External API Dependencies

### **OSINT Services Called via UnifiedSearcher:**

1. **RocketReach** - Professional email/contact info
2. **ContactOut** - Business contact discovery
3. **DeHashed** - Breach database search
4. **OSINT Industries** - Intelligence platform
5. **WHOIS** - Domain registration data
6. **HaveIBeenPwned** - Breach checking
7. **Hunter.io** - Email finder
8. **Clearbit** - Company/person enrichment

### **Event System:**

- `event_emitter` - Optional event emitter for progress updates
  - Events: `entity_progress`, `entity_extracted`, `engine_status`, `result`

## Data Flow

```
Input (email/phone/username/etc.)
    ↓
EyeDSearchHandler.search_*() method
    ↓
UnifiedSearcher.search() [External EYE-D]
    ↓
Multiple OSINT APIs (parallel)
    ↓
Raw data returned
    ↓
_extract_entities_from_data()
    ├── CentralEntityExtractor (if available)
    └── _fallback_entity_extraction()
    ↓
_enhance_entity_context()
    ↓
EntityGraphStorageV2.store_entity()
    ↓
Results with entities & relationships
```

## Configuration Requirements

### **Environment Variables Needed:**

- `EYED_API_KEY` - EYE-D platform access
- `OPENAI_API_KEY` - GPT entity extraction
- Individual API keys for each OSINT service

### **Directory Structure Required:**

```
/OBJECT/OSINT_tools/
    entity_search.py (this file)
../EYE-D/
    unified_osint.py
    ip_geolocation.py
../Indexer/
    entity_graph_storage_v2.py
../TOOLS/
    openai_chatgpt.py
../entities/
    central_extractor.py
```

## Error Handling

The system gracefully handles missing dependencies:

- Falls back to basic extraction if AI unavailable
- Works without storage if EntityGraphStorageV2 missing
- Returns limited results if EYE-D modules unavailable
- Each import wrapped in try/except blocks

## Key Features

1. **Multi-source aggregation** - Queries 8+ OSINT sources simultaneously
2. **AI entity extraction** - Uses GPT-5 for intelligent entity recognition
3. **Graph storage** - Stores entities and relationships in graph database
4. **Event streaming** - Real-time progress updates via event emitter
5. **Fallback mechanisms** - Works with degraded functionality if dependencies missing
6. **Type detection** - Automatically detects input type (email, phone, etc.)
7. **Context enhancement** - Adds rich context to extracted entities
8. **Confidence scoring** - Assigns confidence scores to extracted entities

## Performance Notes

- Async/await for parallel API calls
- Caching via EntityGraphStorageV2
- Event streaming for responsive UI
- Timeout handling for slow APIs
- Rate limiting awareness

This is a highly sophisticated OSINT aggregator that coordinates multiple services and intelligently extracts and stores entity relationships.
