# Maximizing Output Limits for GPT and Claude

## Current Model Output Limits

### GPT-4.1 (GPT-4-Turbo)
- **Maximum Output Tokens**: 4,096 tokens
- **Current Setting**: 200 tokens (WAY TOO LOW!)
- **Optimal Setting**: 2,000-3,000 tokens for gap filling

### Claude (Sonnet/Opus)
- **Maximum Output Tokens**: 4,096 tokens (Sonnet), 8,192 tokens (Opus)
- **Optimal Setting**: 4,096 tokens

### Gemini 1.5/2.0
- **Maximum Output Tokens**: 8,192 tokens
- **Optimal Setting**: 4,096 tokens

## Optimized Settings for Gap Filling

### 1. For Gap Filling (JSON responses)
```python
# CURRENT (TOO LIMITED):
max_tokens=200  # Only ~50-75 words!

# OPTIMIZED:
max_tokens=1000  # ~250-300 words per gap
```

### 2. For Document Assembly/Extraction
```python
# CURRENT:
max_tokens=4096  # Often not specified

# OPTIMIZED FOR GPT-4.1:
response = await client.chat.completions.create(
    model=get_gpt_full_model(),
    messages=[...],
    max_tokens=4096,  # Maximum for GPT-4.1
    temperature=0.1
)

# OPTIMIZED FOR CLAUDE:
response = await claude_client.messages.create(
    model=get_claude_model(),  # Sonnet
    messages=[...],
    max_tokens=4096,  # Maximum for Sonnet
    temperature=0.1
)

# FOR CLAUDE OPUS (Extended output):
response = await claude_client.messages.create(
    model=get_claude_opus_4(),
    messages=[...],
    max_tokens=8192,  # Double the output!
    temperature=0.1
)
```

## Fixed Gap Filler with Maximized Output

```python
# In gap_filler_ultra_fast_live.py, change line 349:

# FROM:
max_tokens=200,   # Limit response size

# TO:
max_tokens=1000,  # Allow full detailed responses
```

## For Document Assembly (Ensamblers)

### Extraction Phase (GPT-4.1-mini)
```python
# Batch API with maximum output
batch_request = {
    "custom_id": f"extract_{idx}",
    "method": "POST",
    "url": "/v1/chat/completions",
    "body": {
        "model": get_gpt_model(),
        "messages": [...],
        "max_tokens": 4096,  # MAXIMIZE!
        "temperature": 0.1
    }
}
```

### Merging Phase (Claude)
```python
# Claude with maximum output
response = await claude_client.messages.create(
    model=get_claude_model(),
    messages=[...],
    max_tokens=4096,  # Full capacity
    temperature=0.1
)
```

### Final Rewrite (Claude Opus)
```python
# Opus for extended output
response = await claude_client.messages.create(
    model=get_claude_opus_4(),
    messages=[...],
    max_tokens=8192,  # DOUBLE OUTPUT!
    temperature=0.1
)
```

## Quick Fixes

### 1. Gap Filler - Immediate Fix
```bash
# Edit line 349 in gap_filler_ultra_fast_live.py
sed -i '' 's/max_tokens=200/max_tokens=1000/g' /Users/brain/GARSON/cog_chatbot/cont_int/gap_filler_ultra_fast_live.py
```

### 2. For Ensamblers
Look for any `max_tokens` settings and ensure they're set to:
- GPT-4.1: 4096
- Claude Sonnet: 4096
- Claude Opus: 8192
- Gemini: 4096

## Impact of Maximizing Output Limits

### Before (200 tokens):
- Gap fills limited to ~50 words
- May cut off mid-sentence
- Missing important details

### After (1000-4096 tokens):
- Full, detailed gap fills
- Complete explanations
- No truncation issues
- Better context preservation

## Token to Word Conversion
- 1 token ≈ 0.75 words
- 200 tokens ≈ 150 words (current limit)
- 1000 tokens ≈ 750 words (good for gaps)
- 4096 tokens ≈ 3000 words (full responses)
- 8192 tokens ≈ 6000 words (Opus only)