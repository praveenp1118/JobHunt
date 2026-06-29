# Frontend conventions — apply to ALL React components

## Component structure
- New UI components: frontend/src/components/ui/
- Page components: frontend/src/pages/
- API clients: frontend/src/api/
- One component per file, named exports

## Styling
- Use Tailwind classes only
- No inline styles except for dynamic values
- Color scale: emerald for success, amber for warning,
  red for error, blue for info

## Score display
- Always use DualRingPill for ATS/Pursuit scores
- Always use TokenBadge for token costs
- Always use ScoreToggle for ATS/Pursuit switching
- Never hardcode score colors — use the color scale

## API calls
- Always use api/ client files
  (never fetch() directly in components)
- Handle loading state: show skeleton/spinner
- Handle error state: show error message
- Handle empty state: show helpful message

## Token badges
- Show TokenBadge after EVERY Claude operation
- Format: "⚡ 12.4K · ₹1.24"
- Location: below the result, small size

## State management
- Use React useState/useEffect (no Redux)
- User preferences: fetch once on mount, cache in state
- Score view (ATS/Pursuit): read from userPrefs
  on mount, not hardcoded default
