# WIKIMAN ID Decoder - Usage Guide

## ✅ UPDATED: 3 MODES NOW AVAILABLE

The WIKIMAN ID decoder now supports **3 different modes** for maximum flexibility:

---

## 🎯 MODE 1: AUTO-DETECT (Default)

**Use when:** You have an ID number and want the best match automatically

**MCP Tool Call:**
```json
{
  "tool": "id_search",
  "arguments": {
    "id": "3527091604810001"
  }
}
```

**Python Direct:**
```python
from wikiman import tool_id_search
result = tool_id_search("3527091604810001")
```

**Returns:**
- Best matching ID format
- Decoded information (DOB, gender, location)
- Automatically routes to appropriate search (company/flight/OSINT)

**Example Output:**
```
✓ Valid NIK - Indonesia
📋 Decoded Information:
  • Province Code: 35 (East Java)
  • Regency Code: 27 (Surabaya)
  • Date Of Birth: 1981-04-16
  • Gender: Male
🔍 Routed to: OSINT Search
```

---

## 🔍 MODE 2: SHOW ALL POSSIBILITIES

**Use when:** You want to see ALL possible ID format matches for a number

**MCP Tool Call:**
```json
{
  "tool": "id_search",
  "arguments": {
    "id": "12345678901",
    "show_all": true
  }
}
```

**Python Direct:**
```python
from wikiman import tool_id_search
result = tool_id_search("12345678901", show_all=True)
```

**Returns:**
- ALL possible format matches
- Confidence level for each (high/low)
- Decoded info for valid matches
- Error messages for invalid matches

**Example Output:**
```
Found 2 possible format(s):

1. ✓ CPF - Brazil
   Confidence: high
   Decoded:
     • Formatted: 123.456.789-01
     • Check Digits: 01

2. ✗ National Register - Belgium
   Confidence: low
   Error: month must be in 1..12
```

---

## 📌 MODE 3: EXPLICIT ID TYPE

**Use when:** You KNOW the exact ID type and want precise decoding

**MCP Tool Call:**
```json
{
  "tool": "id_search",
  "arguments": {
    "id": "3527091604810001",
    "id_type": "indonesia_nik"
  }
}
```

**Python Direct:**
```python
from wikiman import tool_id_search
result = tool_id_search("3527091604810001", id_type="indonesia_nik")
```

**Available ID Types:**
- `indonesia_nik` - Indonesia NIK (16 digits)
- `brazil_cpf` - Brazil Individual Tax ID (11 digits)
- `brazil_cnpj` - Brazil Company Tax ID (14 digits)
- `sweden_personnummer` - Sweden Personal Number (10 digits)
- `china_national_id` - China National ID (18 digits)
- `france_nir` - France Social Security Number (15 digits)
- `belgium_national_register` - Belgium National Register (11 digits)
- `czech_slovak_birth_number` - Czech/Slovak Birth Number (10 digits)
- `romania_cnp` - Romania Personal Numeric Code (13 digits)
- `south_korea_rrn` - South Korea Resident Registration (13 digits)
- `chile_rut` - Chile Tax ID (7-9 characters)

**Returns:**
- Validation status (valid/invalid)
- Full decoded information
- Error message if invalid format

**Example Output:**
```
✓ Valid NIK - Indonesia
📋 Decoded Information:
  • Province Code: 35
  • Regency Code: 27
  • District Code: 09
  • Date Of Birth: 1981-04-16
  • Gender: Male
  • Unique Id: 0001
```

---

## 🚀 Quick Examples

### Example 1: "What could this ID be?"
```python
# Show all possibilities for ambiguous ID
tool_id_search("12345678901", show_all=True)
# Returns: Brazil CPF (high confidence) OR Belgium National Register (low confidence)
```

### Example 2: "This is an Indonesia NIK"
```python
# Explicit decoding
tool_id_search("3527091604810001", id_type="indonesia_nik")
# Returns: Province 35, DOB 1981-04-16, Gender Male
```

### Example 3: "Just decode it automatically"
```python
# Auto-detect best match
tool_id_search("3527091604810001")
# Returns: Detects NIK, decodes it, routes to OSINT search
```

---

## 📊 What Each ID Format Can Decode

| Country | ID Type | Extracts |
|---------|---------|----------|
| 🇮🇩 Indonesia | NIK | Province, Regency, District, DOB, Gender |
| 🇧🇷 Brazil | CPF/CNPJ | Tax ID format, Check digits |
| 🇸🇪 Sweden | Personnummer | Date of birth |
| 🇨🇱 Chile | RUT/RUN | Tax ID, Check digit |
| 🇨🇳 China | National ID | Admin division, DOB, Gender |
| 🇫🇷 France | NIR | Gender, DOB, Department, Municipality |
| 🇧🇪 Belgium | National Register | DOB, Gender |
| 🇨🇿🇸🇰 Czech/Slovak | Birth Number | DOB, Gender |
| 🇷🇴 Romania | CNP | Gender, Century, DOB, County |
| 🇰🇷 South Korea | RRN | DOB, Gender |

---

## 🎓 Best Practices

1. **Use AUTO-DETECT for most cases** - It's smart and fast
2. **Use SHOW ALL when uncertain** - See what the ID could be
3. **Use EXPLICIT when you're sure** - Most accurate results
4. **Check the `valid` field** - Not all IDs can be decoded
5. **Look at `confidence` in SHOW ALL mode** - Prioritize high confidence matches

---

## 🔧 Technical Notes

- **Pattern Detection**: Based on length, format, and special characters
- **Validation**: Each decoder validates date ranges, check digits, etc.
- **Routing**: Company IDs → Company Search, Personal IDs → OSINT Search
- **Performance**: Cached results, optimized vector search
- **Extensibility**: Easy to add new ID formats (55+ documented, 11 implemented)

---

## 📞 Support

**Command Line Test:**
```bash
cd "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/0. WIKIMAN"
python3 wikiman_id_decoder.py 3527091604810001
```

**MCP Server:** Restart Claude Desktop to load the updated tool definitions
