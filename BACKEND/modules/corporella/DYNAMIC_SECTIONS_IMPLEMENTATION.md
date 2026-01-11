# Dynamic Sections & Animated Buttons Implementation

## Overview
Successfully implemented a hierarchical, animated button system inspired by the operator button pattern for dynamically rendering wiki source buttons and compliance sections in Corporella Claude.

## Key Features Implemented

### 1. **Hierarchical Button System**
- **Primary Level**: Main categories (Corporate Registry, Litigation, Regulatory)
- **Secondary Level**: Expandable subcategories (Official Records, Third Party, etc.)
- **Staggered Animations**: Each button animates in with a slight delay
- **Context Detection**: Buttons only appear when relevant data exists

### 2. **Animation System**
```javascript
// Staggered animation for buttons
sources.forEach((source, index) => {
    setTimeout(() => {
        wrapper.style.transition = 'all 0.3s ease-out';
        wrapper.style.opacity = '1';
        wrapper.style.transform = 'translateY(0) scale(1)';
    }, index * 50); // 50ms delay between buttons
});
```

### 3. **Dynamic Source Categorization**
The system automatically categorizes sources based on their names:
- **Official**: Companies House, Registry sources
- **Third Party**: OCCRP, DueDil
- **Court**: Court records, BAILII
- **Case Law**: Legal case databases
- **Media**: News and reputation sources

### 4. **Visual Design**
- **Gradient Backgrounds**: Beautiful gradient effects on buttons
- **Hover Effects**: Ripple animations on hover
- **Dark Mode Support**: Automatic adaptation to system theme
- **Responsive Design**: Adapts to mobile screens

## Files Created

### `dynamic_sections.js`
Main JavaScript class that handles:
- Context detection
- Button rendering
- Hierarchical organization
- Animation timing
- Source categorization

### `dynamic_sections.css`
Comprehensive styling including:
- Gradient button designs
- Animation keyframes
- Hover effects
- Dark mode support
- Loading states
- Responsive breakpoints

## How It Works

### 1. Context Detection
```javascript
detectContext(entity) {
    return {
        hasJurisdiction: !!(entity?.about?.jurisdiction),
        hasCorporateRegistry: !!(entity?.about?._corporate_registry_sources),
        hasLitigation: !!(entity?.compliance?.litigation?._wiki_sources),
        // ... more conditions
    };
}
```

### 2. Hierarchical Rendering
When wiki sources are detected, the system:
1. Groups sources by type (official, third-party, etc.)
2. Creates expandable sections with counts
3. Renders buttons with staggered animations
4. Adds appropriate icons based on source type

### 3. Animation Flow
```
User searches → Entity update received → Wiki data enriched
→ Context detected → Sections render with delay
→ Buttons animate in one by one → User sees beautiful UI
```

## Integration with Existing System

### Backend Changes
- Wiki data is now enriched during EACH entity update
- Ensures data is available when the UI renders

### Frontend Changes
- `displayWikiSources()` now uses the new `DynamicSectionManager`
- Automatic icon assignment based on source name
- Expandable sections for better organization

## Usage Example

When searching for "Revolut Ltd" (UK):

1. **Corporate Registry Section** appears with:
   - Official Records (Companies House)
   - Third Party Sources (OCCRP, DueDil)

2. **Litigation Section** shows:
   - Court Records (UK Court Service)
   - Case Law (BAILII, Find Case Law)

3. **Each button**:
   - Animates in with a delay
   - Has a gradient background
   - Shows ripple effect on hover
   - Opens source in new tab

## Visual Features

### Button States
- **Default**: Gradient purple/blue
- **Hover**: Inverted gradient + shadow
- **Secondary**: Green/blue gradient
- **Loading**: Spinning indicator

### Animations
- **slideInFromTop**: Sections appear from above
- **slideInFromLeft**: Buttons slide in from left
- **fadeInScale**: Scale up with fade
- **Ripple**: Circular expansion on hover

## Performance Optimizations

1. **Lazy Rendering**: Buttons only render when sections expand
2. **Staggered Loading**: Prevents UI freeze with many buttons
3. **Show More**: Long lists collapse with "Show X more..." button
4. **CSS Transitions**: Hardware-accelerated animations

## Testing

1. Open `company_profile.html` in browser
2. Search for a UK company (e.g., "Revolut Ltd" with country "GB")
3. Watch as:
   - Wiki buttons appear with animations
   - Sections have expandable hierarchies
   - Hover effects work smoothly
   - Icons match source types

## Future Enhancements

1. **Save State**: Remember expanded/collapsed sections
2. **Filtering**: Allow filtering by source type
3. **Search**: Search within sources
4. **Favorites**: Mark frequently used sources
5. **Analytics**: Track which sources are most clicked

## Conclusion

The dynamic sections implementation brings a modern, animated UI to Corporella Claude, making wiki sources not just functional but visually delightful. The hierarchical organization helps manage large numbers of sources, while the animations provide smooth, professional interactions that match modern web standards.