# SASTRE Autopilot - Visual Reference Guide

## UI States Overview

### State 1: Normal Mode (Before Investigation)

```
┌────────────────────────────────────────────────────────────────────────┐
│  Drill Search                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                                                                  │  │
│  │  GlobalSearchBar (Normal State)                                 │  │
│  │  ┌────────────────────────────────────────────────────────────┐ │  │
│  │  │                                                            │ │  │
│  │  │  [🔍]  Search...                              [🔍 Live]   │ │  │
│  │  │   ▲                                              ▲         │ │  │
│  │  │   │                                              │         │ │  │
│  │  │  Gray                                          Gray        │ │  │
│  │  │  icon                                          status      │ │  │
│  │  │                                                            │ │  │
│  │  └────────────────────────────────────────────────────────────┘ │  │
│  │   ▲                                                            │  │
│  │   │                                                            │  │
│  │  White background, rounded, subtle shadow                     │  │
│  │                                                                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                                                                  │  │
│  │                      Main Content Area                          │  │
│  │                                                                  │  │
│  │             (Grid, Narrative Editor, etc.)                      │  │
│  │                                                                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│                                                                        │
│  [No SastreAutopilotBar - hidden when not running]                   │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

### State 2: SASTRE Mode Active (During Investigation)

```
┌────────────────────────────────────────────────────────────────────────┐
│  Drill Search                                        [C0GN1T0 MODE]    │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                                                                  │  │
│  │  GlobalSearchBar (SASTRE State)                                 │  │
│  │  ┌────────────────────────────────────────────────────────────┐ │  │
│  │  │                                                            │ │  │
│  │  │  [🔍]  csr: Microsoft Corporation    [● SASTRE]           │ │  │
│  │  │   ▲     ▲                               ▲     ▲           │ │  │
│  │  │   │     │                               │     │           │ │  │
│  │  │  Green  Pulsing                      Pulse  Green         │ │  │
│  │  │  icon   green text                   dot    label         │ │  │
│  │  │                                                            │ │  │
│  │  └────────────────────────────────────────────────────────────┘ │  │
│  │   ▲                                                            │  │
│  │   │                                                            │  │
│  │  Dark background (#0d1117), green glow border                 │  │
│  │                                                                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                                                                  │  │
│  │                      Main Content Area                          │  │
│  │                                                                  │  │
│  │             (Grid being populated with results)                 │  │
│  │                                                                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  SastreAutopilotBar                                             │  │
│  │  ┌────────────────────────────────────────────────────────────┐ │  │
│  │  │                                                            │ │  │
│  │  │  [●] SASTRE AUTOPILOT  [SEARCH #3]  csr: Microsoft   [■]  │ │  │
│  │  │   ▲                     ▲            ▲                 ▲   │ │  │
│  │  │   │                     │            │                 │   │ │  │
│  │  │  Pulse               Phase        Current           STOP   │ │  │
│  │  │  (green,             (gray)       syntax           (red)   │ │  │
│  │  │  pulsing)                          (cyan)           btn    │ │  │
│  │  │                                                            │ │  │
│  │  └────────────────────────────────────────────────────────────┘ │  │
│  │   ▲                                                            │  │
│  │   │                                                            │  │
│  │  Dark bg, green border, shadow glow, centered bottom          │  │
│  │                                                                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

### State 3: Error State

```
┌────────────────────────────────────────────────────────────────────────┐
│  Drill Search                                        [C0GN1T0 MODE]    │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  GlobalSearchBar (returns to normal on error)                   │  │
│  │  ┌────────────────────────────────────────────────────────────┐ │  │
│  │  │  [🔍]  Search...                              [🔍 Live]   │ │  │
│  │  └────────────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      Main Content Area                          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  SastreAutopilotBar (Error State)                               │  │
│  │  ┌────────────────────────────────────────────────────────────┐ │  │
│  │  │                                                            │ │  │
│  │  │  [●] SASTRE AUTOPILOT  [ERROR]  Connection lost      [■]  │ │  │
│  │  │   ▲                     ▲        ▲                     ▲   │ │  │
│  │  │   │                     │        │                     │   │ │  │
│  │  │  Pulse               Phase    Error msg            STOP   │ │  │
│  │  │  (RED,               (gray)   (red text)           (red)   │ │  │
│  │  │  solid)                                            btn    │ │  │
│  │  │                                                            │ │  │
│  │  └────────────────────────────────────────────────────────────┘ │  │
│  │   ▲                                                            │  │
│  │   │                                                            │  │
│  │  Dark bg, red pulse indicator, error message visible          │  │
│  │                                                                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown - SastreAutopilotBar

### Layout Structure

```
┌──────────────────────────────────────────────────────────────────────┐
│  SastreAutopilotBar Container                                        │
│  (fixed, bottom: 80px, centered, z-index: 9999)                      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                                                                │ │
│  │  ┌──────┐  ┌──────────────┐  ┌─────────┐  ┌────────┐  ┌────┐ │ │
│  │  │ [●]  │  │ SASTRE       │  │ [PHASE] │  │ SYNTAX │  │STOP│ │ │
│  │  │ Pulse│  │ AUTOPILOT    │  │ #ITER   │  │        │  │ ■  │ │ │
│  │  └──────┘  └──────────────┘  └─────────┘  └────────┘  └────┘ │ │
│  │     1            2                3            4         5    │ │
│  │                                                                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

1. Pulse Indicator
   - Size: 10px × 10px
   - Color: #00ff88 (running), #ff4444 (error)
   - Animation: sastrePulse 1.5s infinite

2. Label
   - Text: "SASTRE AUTOPILOT"
   - Font: monospace, 13px, 600 weight
   - Color: #00ff88
   - Letter-spacing: 0.5px

3. Phase Info
   - Text: e.g., "SEARCH #3"
   - Font: monospace, 11px
   - Color: #888
   - Format: "{PHASE} #{ITERATION}"

4. Syntax Display
   - Text: e.g., "csr: Microsoft Corporation"
   - Font: monospace, 12px
   - Color: #00d4ff
   - Background: rgba(0,0,0,0.3)
   - Max-width: 300px (truncates with ellipsis)
   - Hover: shows full text via title attribute

5. Stop Button
   - Text: "STOP"
   - Background: gradient red (#dc2626 → #b91c1c)
   - Color: white
   - Font: 12px, 600 weight
   - Hover: scale(1.05), brighter gradient
   - Icon: ⏹ (stop square)
```

---

## Component Breakdown - GlobalSearchBar (SASTRE Mode)

### Layout Structure

```
┌──────────────────────────────────────────────────────────────────────┐
│  GlobalSearchBar Container                                           │
│  (normal: white bg, SASTRE: dark bg with glow)                       │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                                                                │ │
│  │  ┌──────┐  ┌────────────────────────────────┐  ┌────────────┐ │ │
│  │  │ [🔍] │  │ {SYNTAX TEXT}                  │  │ [● SASTRE] │ │ │
│  │  │ Icon │  │ Pulsing green animation        │  │ Status     │ │ │
│  │  └──────┘  └────────────────────────────────┘  └────────────┘ │ │
│  │     1                  2                            3         │ │
│  │                                                                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

1. Search Icon
   - Normal: gray (#6b7280)
   - SASTRE: green (#00ff88)
   - Size: 16px × 16px

2. Syntax Display (replaces input in SASTRE mode)
   - Text: Current syntax (e.g., "csr: Microsoft Corporation")
   - Font: monospace, 14px
   - Color: #00ff88
   - Animation: animate-pulse (Tailwind)
   - Truncates with ellipsis
   - Hover: full text via title attribute

3. Status Indicator
   - Normal: "Live" with search icon
   - SASTRE: "SASTRE" with pulsing dot
   - Font: uppercase, 11px, tracking-wide
   - Dot: 8px × 8px, #00ff88, animate-pulse
```

---

## Color Palette Reference

### COGNITO_COLORS

```
┌────────────────────────────────────────────────────────────────┐
│  Primary Colors                                                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Neon Green (#00ff88)                                          │
│  ████████████████████████████████████████                     │
│  Usage: Primary accent, pulsing indicators, active states      │
│  RGB: rgb(0, 255, 136)                                         │
│  HSL: hsl(152, 100%, 50%)                                      │
│                                                                │
│  Neon Green Glow (#00ff8833)                                   │
│  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                     │
│  Usage: Border glows, box shadows                              │
│  RGBA: rgba(0, 255, 136, 0.2)                                  │
│                                                                │
│  Neon Blue (#00d4ff)                                           │
│  ████████████████████████████████████████                     │
│  Usage: Secondary accent, syntax text                          │
│  RGB: rgb(0, 212, 255)                                         │
│  HSL: hsl(190, 100%, 50%)                                      │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│  Background Colors                                             │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Panel Background (#0d1117)                                    │
│  ██████████████████████████████████████████                   │
│  Usage: Dark mode backgrounds                                  │
│  RGB: rgb(13, 17, 23)                                          │
│  HSL: hsl(216, 28%, 7%)                                        │
│                                                                │
│  Syntax Background (rgba(0,0,0,0.3))                           │
│  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                     │
│  Usage: Code/syntax containers                                 │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│  Text Colors                                                   │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Text Secondary (#888888)                                      │
│  ████████████████████████████████████████                     │
│  Usage: Muted text, phase labels                               │
│  RGB: rgb(136, 136, 136)                                       │
│  HSL: hsl(0, 0%, 53%)                                          │
│                                                                │
│  White (#ffffff)                                               │
│  ████████████████████████████████████████                     │
│  Usage: High contrast text, button labels                      │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│  Error Colors                                                  │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Red (#ff4444)                                                 │
│  ████████████████████████████████████████                     │
│  Usage: Error states, pulse indicator on error                 │
│  RGB: rgb(255, 68, 68)                                         │
│  HSL: hsl(0, 100%, 63%)                                        │
│                                                                │
│  Red Button Gradient (#dc2626 → #b91c1c)                       │
│  ████████████████████████████████████████                     │
│  Usage: Stop button background                                 │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Animation Reference

### Pulse Animation (SastreAutopilotBar)

```css
@keyframes sastrePulse {
  0% {
    transform: scale(1);
    opacity: 1;
  }

  50% {
    transform: scale(1.3);
    opacity: 0.7;
  }

  100% {
    transform: scale(1);
    opacity: 1;
  }
}

/* Applied to: .pulse element in SastreAutopilotBar */
/* Duration: 1.5s */
/* Timing: ease-in-out */
/* Iteration: infinite */
```

### Timeline Visualization

```
Time:     0s        0.75s       1.5s       2.25s       3s
          │           │           │           │           │
Scale:    1.0  ────▶ 1.3  ────▶ 1.0  ────▶ 1.3  ────▶ 1.0
          │     grow  │   shrink  │     grow  │   shrink  │
Opacity:  1.0  ────▶ 0.7  ────▶ 1.0  ────▶ 0.7  ────▶ 1.0
          │    fade   │  restore  │    fade   │  restore  │
```

### Tailwind Animate-Pulse (GlobalSearchBar)

```css
/* Built-in Tailwind animation */
.animate-pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

/* Applied to: syntax text in GlobalSearchBar */
```

---

## Responsive Behavior

### Desktop (> 1024px)

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  GlobalSearchBar: Full width (max 800px centered)               │
│                                                                  │
│  SastreAutopilotBar: Centered, all elements visible             │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ [●] AUTOPILOT [SEARCH #3] csr: Microsoft Corporation [STOP]│ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Tablet (768px - 1024px)

```
┌────────────────────────────────────────────────────────────┐
│                                                            │
│  GlobalSearchBar: Full width with padding                 │
│                                                            │
│  SastreAutopilotBar: Syntax text truncates earlier        │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ [●] AUTOPILOT [SEARCH #3] csr: Micros... [STOP]      │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### Mobile (< 768px)

```
┌──────────────────────────────────────────┐
│                                          │
│  GlobalSearchBar: Full width, no padding│
│  Status "SASTRE" → "S"                  │
│                                          │
│  SastreAutopilotBar: Stacked layout     │
│  ┌────────────────────────────────────┐ │
│  │ [●] AUTOPILOT [SEARCH #3]          │ │
│  │ csr: Microsoft...         [STOP]   │ │
│  └────────────────────────────────────┘ │
│   ▲                                     │
│   │                                     │
│   Two rows for better mobile UX        │
│                                          │
└──────────────────────────────────────────┘

Note: Mobile responsive layout not yet implemented
Future enhancement in roadmap
```

---

## Interaction States

### SastreAutopilotBar - Stop Button

```
┌────────────────────────────────────────────────────────────┐
│  State: Default                                            │
│  ┌──────┐                                                  │
│  │ STOP │  Background: linear-gradient(#dc2626, #b91c1c) │
│  └──────┘  Color: white                                   │
│            Box-shadow: 0 2px 8px rgba(220,38,38,0.3)      │
│            Transform: scale(1)                             │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│  State: Hover                                              │
│  ┌──────┐                                                  │
│  │ STOP │  Background: linear-gradient(#ef4444, #dc2626) │
│  └──────┘  Color: white                                   │
│            Box-shadow: 0 4px 12px rgba(239,68,68,0.4)     │
│            Transform: scale(1.05)                          │
│            Transition: all 0.2s ease                       │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│  State: Active (click)                                     │
│  ┌──────┐                                                  │
│  │ STOP │  Background: linear-gradient(#b91c1c, #991b1b) │
│  └──────┘  Color: white                                   │
│            Transform: scale(0.95)                          │
└────────────────────────────────────────────────────────────┘
```

### GlobalSearchBar - Mode Transition

```
┌────────────────────────────────────────────────────────────┐
│  Transition: Normal → SASTRE (< 300ms)                     │
│                                                            │
│  Step 1: sastre-query event received                       │
│  Step 2: setSastreSyntax(syntax) triggers re-render       │
│  Step 3: Conditional classes apply:                        │
│          - background: #ffffff → #0d1117                   │
│          - border: #e5e7eb → #00ff8880                     │
│          - box-shadow: subtle → green glow                 │
│  Step 4: Input hidden, syntax displayed                    │
│  Step 5: Transition duration: 0.3s                         │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│  Transition: SASTRE → Normal (< 300ms)                     │
│                                                            │
│  Step 1: setSastreSyntax(null) on complete/stop           │
│  Step 2: Conditional classes revert                        │
│  Step 3: Syntax hidden, input displayed                    │
│  Step 4: Colors fade back to normal                        │
│  Step 5: Transition duration: 0.3s                         │
└────────────────────────────────────────────────────────────┘
```

---

## Z-Index Layering

```
┌────────────────────────────────────────────────────────────┐
│  Z-Index Stack (highest to lowest)                        │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  z-index: 9999  ──  SastreAutopilotBar                    │
│                     Fixed at bottom, always on top         │
│                                                            │
│  z-index: 100   ──  CognitoChatDropdown                   │
│                     Modal-like overlay                     │
│                                                            │
│  z-index: 50    ──  GlobalSearchBar                       │
│                     Top bar element                        │
│                                                            │
│  z-index: 10    ──  Grid overlays, tooltips               │
│                                                            │
│  z-index: 1     ──  Main content (Grid, Narrative)        │
│                                                            │
│  z-index: 0     ──  Background                            │
│                                                            │
└────────────────────────────────────────────────────────────┘

Why 9999 for SastreAutopilotBar?
- Must appear above all other UI elements
- User must always see investigation status
- Stop button must always be accessible
- Similar to notification toasts, critical alerts
```

---

## Event Timeline Example

### Complete Investigation Flow (60 seconds)

```
Time    Event Type     GlobalSearchBar          SastreAutopilotBar
────────────────────────────────────────────────────────────────────
0s      init           [transforms to dark]     [appears]
                       ───────────────────       ──────────

2s      query          "csr: Microsoft"         [SEARCH #1]
        (syntax)       [pulsing green]          csr: Microsoft

5s      result         (still showing syntax)   [SEARCH #1]
        (42 results)                            csr: Microsoft

8s      query          "chr: Microsoft"         [SEARCH #1]
        (syntax)       [updates]                chr: Microsoft

10s     phase          (still showing syntax)   [EXTRACT #1]
        (EXTRACT)                               chr: Microsoft

12s     query          "wik: Microsoft CEO"     [EXTRACT #1]
        (syntax)       [updates]                wik: Microsoft CEO

20s     phase          (still showing syntax)   [ASSESS #1]
        (ASSESS)                                wik: Microsoft CEO

25s     phase          (still showing syntax)   [SEARCH #2]
        (SEARCH #2)                             (syntax cleared)

27s     query          "csr: Satya Nadella"     [SEARCH #2]
        (syntax)       [updates]                csr: Satya Nadella

...     ...            ...                      ...

58s     complete       [transforms to normal]   [disappears]
                       ───────────────────       ──────────
                       Search...                (hidden)

60s     (idle)         [normal state]           (not rendered)
```

---

## Accessibility Visual Guide

### Keyboard Navigation

```
┌────────────────────────────────────────────────────────────┐
│  Tab Order                                                 │
│                                                            │
│  1. GlobalSearchBar input (if not in SASTRE mode)         │
│     ┌────────────────────────────────────────────────┐    │
│     │ [🔍] [Search...]                              │    │
│     └────────────────────────────────────────────────┘    │
│       ▲ focusable, type to search                         │
│                                                            │
│  2. SastreAutopilotBar Stop Button (if visible)           │
│     ┌──────────────────────────────────────────┐          │
│     │ [● AUTOPILOT] [SEARCH #3] [...] [STOP]  │          │
│     └──────────────────────────────────────────┘          │
│                                          ▲                 │
│                                          │                 │
│                                    Focus ring visible      │
│                                    Press Enter to activate │
│                                                            │
│  3. Main content (Grid, Narrative, etc.)                  │
│     Continue tabbing through interactive elements         │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### Focus States

```
┌────────────────────────────────────────────────────────────┐
│  Stop Button - Focus Indicator                            │
│                                                            │
│  No Focus:                                                 │
│  ┌──────┐                                                  │
│  │ STOP │                                                  │
│  └──────┘                                                  │
│                                                            │
│  With Focus (Tab):                                         │
│  ┌────────┐                                                │
│  │ ┌────┐ │                                                │
│  │ │STOP│ │  ← Blue outline (browser default)            │
│  │ └────┘ │                                                │
│  └────────┘                                                │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

---

## Print-Friendly Version (Future)

```
When investigation is active and user prints:

┌────────────────────────────────────────────────────────────┐
│  Investigation Status (printed at top of page)             │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  SASTRE AUTOPILOT ACTIVE                                   │
│  Phase: SEARCH #3                                          │
│  Current Query: csr: Microsoft Corporation                 │
│                                                            │
│  [Print-friendly black & white version]                   │
│  [No animations, no colors]                                │
│  [Static snapshot of state]                                │
│                                                            │
└────────────────────────────────────────────────────────────┘

Note: Print CSS not yet implemented
Future enhancement
```

---

## Summary

This visual reference provides:

✅ All UI states (Normal, SASTRE, Error)
✅ Component layout breakdowns
✅ Complete color palette with hex codes
✅ Animation specifications
✅ Responsive behavior (desktop/tablet/mobile)
✅ Interaction states and transitions
✅ Z-index layering
✅ Event timeline example
✅ Accessibility visual guide
✅ Print-friendly considerations

Use this guide for:
- Design reviews
- QA visual testing
- Developer onboarding
- Product documentation
- User training materials
