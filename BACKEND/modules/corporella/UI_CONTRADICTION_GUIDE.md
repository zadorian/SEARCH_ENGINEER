# UI Implementation Guide: Contradiction Display

## Quick Reference for Frontend Developers

### 🎯 Goal
When the backend returns a `_contradictions` array, display contradicting fields with:
1. Red background
2. Red source badges
3. Arrow indicator
4. "CONTRADICTION" warning
5. Explanation text

---

## Step 1: Check for Contradictions

When receiving entity data from WebSocket:

```javascript
function renderEntity(entity) {
  // Check if entity has contradictions
  const contradictions = entity._contradictions || [];

  // Build lookup map for quick checking
  const contradictionMap = {};
  contradictions.forEach(c => {
    contradictionMap[c.field] = c;
  });

  // Render each field
  renderField('name', entity.name, contradictionMap);
  renderField('about.jurisdiction', entity.about?.jurisdiction, contradictionMap);
  // ... etc
}
```

---

## Step 2: Render Field with Contradiction Check

```javascript
function renderField(fieldPath, fieldData, contradictionMap) {
  const isContradiction = contradictionMap[fieldPath];

  if (isContradiction) {
    // 🔴 RENDER AS CONTRADICTION
    return renderContradictionField(fieldPath, fieldData, isContradiction);
  } else {
    // ✅ RENDER AS NORMAL
    return renderNormalField(fieldPath, fieldData);
  }
}
```

---

## Step 3: Render Normal Field

```javascript
function renderNormalField(fieldPath, fieldData) {
  const value = fieldData.value || fieldData;
  const source = fieldData.source || '';

  return `
    <div class="field-group">
      <label>${formatFieldName(fieldPath)}</label>
      <div class="field-value">
        ${value}
        ${source ? `<span class="badge badge-normal">${source}</span>` : ''}
      </div>
    </div>
  `;
}
```

**CSS for Normal Badges**:
```css
.badge-normal {
  background-color: #4CAF50; /* Green */
  color: white;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.85em;
  margin-left: 10px;
  float: right;
}
```

---

## Step 4: Render Contradiction Field 🔴

```javascript
function renderContradictionField(fieldPath, fieldData, contradictionInfo) {
  // Parse the pipe-separated values
  const values = contradictionInfo.values; // Array of {value, source}

  // Build the display
  const valuesHTML = values.map(v => `
    <span class="contradiction-value">
      ${v.value}
      <span class="badge badge-contradiction">${v.source}</span>
    </span>
  `).join('<span class="separator">|</span>');

  return `
    <div class="field-group contradiction">
      <label>${formatFieldName(fieldPath)} ⚠️ CONTRADICTION</label>
      <div class="value-with-contradiction">
        ${valuesHTML}
      </div>
      <div class="contradiction-notice">
        ⬆️ Multiple sources provide different values - verify manually
      </div>
    </div>
  `;
}
```

**CSS for Contradiction Display**:
```css
/* Field container */
.field-group.contradiction {
  background-color: #fee; /* Light red background */
  border-left: 4px solid #d00; /* Dark red left border */
  padding: 10px;
  margin: 10px 0;
}

/* 🔴 RED BADGES - This is the key requirement! */
.badge-contradiction {
  background-color: #d00 !important; /* Dark red */
  color: white !important;
  border: 2px solid #a00 !important; /* Darker red border */
  font-weight: bold;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.85em;
  margin-left: 5px;
}

/* Pipe separator between values */
.value-with-contradiction .separator {
  color: #d00;
  font-weight: bold;
  margin: 0 10px;
}

/* Warning notice */
.contradiction-notice {
  color: #d00;
  font-weight: bold;
  margin-top: 8px;
  font-size: 0.9em;
}

/* Each value block */
.contradiction-value {
  display: inline-block;
}
```

---

## Complete Example

### Input Data (from backend):
```json
{
  "about": {
    "jurisdiction": "us_ca [OC] | us_de [AL]"
  },
  "_contradictions": [
    {
      "field": "about.jurisdiction",
      "values": [
        {"value": "us_ca", "source": "[OC]"},
        {"value": "us_de", "source": "[AL]"}
      ],
      "highlight": "red"
    }
  ]
}
```

### Output HTML:
```html
<div class="field-group contradiction">
  <label>Jurisdiction ⚠️ CONTRADICTION</label>
  <div class="value-with-contradiction">
    <span class="contradiction-value">
      us_ca
      <span class="badge badge-contradiction">[OC]</span>
    </span>
    <span class="separator">|</span>
    <span class="contradiction-value">
      us_de
      <span class="badge badge-contradiction">[AL]</span>
    </span>
  </div>
  <div class="contradiction-notice">
    ⬆️ Multiple sources provide different values - verify manually
  </div>
</div>
```

### Visual Result:
```
╔════════════════════════════════════════════════════╗
║ Jurisdiction ⚠️ CONTRADICTION                      ║
║                                                    ║
║ us_ca [OC] | us_de [AL]                           ║
║       ^^^^       ^^^^                              ║
║       RED        RED (badges are red)              ║
║                                                    ║
║ ⬆️ Multiple sources provide different values -    ║
║    verify manually                                 ║
╚════════════════════════════════════════════════════╝
```

---

## Testing Checklist

When implementing, verify:

- [ ] Normal fields show green/blue badges
- [ ] Contradiction fields have red background
- [ ] 🔴 **Source badges are RED** for contradictions
- [ ] Pipe separator `|` is visible between values
- [ ] Warning arrow `⬆️` is displayed
- [ ] "CONTRADICTION" label is in the field label
- [ ] Explanation text is shown below values
- [ ] Layout is responsive and readable

---

## Common Mistakes to Avoid

❌ **WRONG**: Using same badge color for contradictions as normal fields
```css
/* DON'T DO THIS */
.badge { background-color: #4CAF50; } /* Same for all */
```

✅ **RIGHT**: Different badge colors based on context
```css
.badge-normal { background-color: #4CAF50; } /* Green */
.badge-contradiction { background-color: #d00; } /* RED */
```

---

❌ **WRONG**: Not checking `_contradictions` array
```javascript
// DON'T DO THIS
function render(entity) {
  return renderNormalField(entity.name);
}
```

✅ **RIGHT**: Always check for contradictions first
```javascript
function render(entity) {
  const contradictions = entity._contradictions || [];
  const isContradiction = contradictions.find(c => c.field === 'name');

  if (isContradiction) {
    return renderContradictionField('name', entity.name, isContradiction);
  } else {
    return renderNormalField('name', entity.name);
  }
}
```

---

## Summary

**Normal Field**:
- Clean value
- Green/blue badge in top-right
- Example: `Apple Inc [OC] [AL]`

**Contradiction Field**:
- Red background
- 🔴 **RED badges** (most important!)
- Pipe separator between values
- Warning arrow + explanation
- Example: `us_ca [OC] | us_de [AL]` (both badges RED)

**Key Rule**: If `_contradictions` array contains the field → use RED badges!
