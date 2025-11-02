# 🚀 Gap-Filling AI Quick Start for EDITh.app

## Starting EDITh with Gap-Filling

1. **Double-click EDITh.app** on your Desktop
   - This will open Terminal and start the server
   - Your browser will automatically open to http://localhost:8080

2. **Start typing in the main editor!**

## How to Use Gap-Filling

### Basic Usage
Type `[?]` where you want AI to fill information:
```
The capital of France is [?].
```
✨ Becomes: The capital of France is **Paris**.

### Multiple Gaps
```
Bill Clinton married [?] in [?].
```
✨ Becomes: Bill Clinton married **Hillary Rodham** in **1975**.

### Context-Aware Gaps
Provide hints inside the brackets:
```
Einstein published his theory of relativity in [year].
The [largest planet in our solar system] has a Great Red Spot.
```

### Triggering Gap-Fill
Gap filling activates when you:
- End a sentence with `.` or `!` or `?`
- Type a space and capital letter (new sentence)

## Visual Indicators

- **Green Text**: Shows AI-filled content
- **[^1] Citations**: Links to sources used
- **References**: Listed at the bottom

## Examples to Try

Copy and paste these into EDITh:

1. `The tallest mountain in the world is [?] at [height in meters] meters.`

2. `The [inventor of the telephone] filed his patent in [year].`

3. `Python was created by [?] and first released in [year].`

## Troubleshooting

**Nothing happens when I type [?]**
- Make sure you complete the sentence with punctuation
- Check if Terminal shows the server is running
- Try refreshing the browser

**Server won't start**
- Close any existing Terminal windows
- Double-click EDITh.app again
- Check Terminal for error messages

**Python errors**
Run in Terminal:
```bash
pip3 install google-genai requests
```

## Tips

- Keep gaps concise for best results
- Use descriptive hints in brackets for specific information
- Multiple gaps in one sentence work great
- Citations ensure accuracy

## Stop Server

To stop EDITh:
1. Click on the Terminal window
2. Press `Ctrl+C`
3. Close Terminal

---
Enjoy intelligent gap-filling with EDITh! 🎉