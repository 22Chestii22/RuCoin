# RuCoin Design System

## 0. Research Log
- **Layer A:** `minimalist-skill.md` — warm monochrome, editorial typography, bento grids, ultra-clean
- **Layer B:** No specific brand; mood direction: "premium crypto with hardware roots" — dark/light neutral, technical but elegant
- **Concept:** RuCoin is a cryptocurrency mined with USB hardware tokens. The design should feel **physical, technical, and minimal** — like a precision tool.

## 1. Brand Tokens
- **Voice:** Technical, direct, no hype. Russian language.
- **Logo:** `◎ RuCoin` — simple geometric circle + wordmark
- **Tagline:** Первая криптовалюта на USB-токенах

## 2. Color Palette
| Token | Value | Usage |
|-------|-------|-------|
| `--canvas` | `#F7F6F3` | Page background — warm off-white |
| `--surface` | `#FFFFFF` | Cards, sections |
| `--surface-secondary` | `#F0F0EF` | Code blocks, secondary fills |
| `--border` | `#EAEAEA` | All borders, dividers |
| `--text` | `#111111` | Primary text |
| `--text-secondary` | `#787774` | Secondary text, labels |
| `--accent` | `#1A1A2E` | Buttons, primary actions |
| `--accent-hover` | `#333333` | Button hover |
| `--success-bg` | `#EDF3EC` | Success status |
| `--success-text` | `#346538` | Success text |
| `--error-bg` | `#FDEBEC` | Error status |
| `--error-text` | `#9F2F2D` | Error text |

## 3. Typography
| Role | Font | Weight | Size |
|------|------|--------|------|
| Headings (h1-h2) | `Newsreader`, serif | 400-500 | `clamp(2.2em, 5vw, 3.6em)` |
| Headings (h3+) | `SF Pro Display`, sans-serif | 500 | `1em` |
| Body | `SF Pro Display`, sans-serif | 400 | `1em` / `0.88em` |
| Meta/Code | `Geist Mono`, `SF Mono`, monospace | 400 | `0.82em` |
| Eyebrow | Monospace | 400 | `0.7em`, uppercase, `0.12em` tracking |
| Buttons | Sans-serif | 500 | `0.88em` |

## 4. Spacing Scale
| Token | Value |
|-------|-------|
| `--gutter` | `24px` |
| Section padding | `96px` vertical (`56px` on mobile) |
| Card padding | `28px` |
| Border radius | `10px` (cards), `8px` (inputs), `6px` (buttons) |

## 5. Components
### Card
- Background: `var(--surface)`
- Border: `1px solid var(--border)`
- Radius: `10px`
- Padding: `28px`
- Hover: `box-shadow: 0 2px 16px rgba(0,0,0,0.05)`, `translateY(-1px)`

### Button
- Filled: `var(--accent)` bg, white text, `6px` radius
- Outline: transparent bg, `1px solid var(--border)`, dark text
- Hover: darker bg, `scale(0.97)` on click
- Padding: `10px 22px`

### Input / Textarea
- Border: `1px solid var(--border)`
- Radius: `8px`
- Background: `var(--canvas)` (slightly off-white)
- Focus: border darkens to `#bbb`
- Font: monospace

### Wallet Card
- Centered, max-width `560px`
- Large balance display (`2.8em`, serif)
- Address in monospace with secondary background
- Status messages with colored backgrounds

### Navigation
- Sticky, blurred background (`backdrop-filter: blur(16px)`)
- Thin bottom border
- 56px height
- Logo on left, links on right

## 6. Motion
- Entry animation: `fade-up` — `translateY(16px) + opacity 0 → 1` over `600ms` with `cubic-bezier(0.16, 1, 0.3, 1)`
- Stagger: `delay-1` through `delay-4` (100ms increments)
- Hover: `0.25s` transition on box-shadow and transform
- No decorative animations, no slop

## 7. Responsive
- Below 768px: collapse nav links, reduce section padding to `56px`, wallets go full-width
- Below 480px: tighter hero padding

## 8. Iconography
- No emoji as icons (exception: status indicators in wallet)
- Use simple SVG primitives or text-based indicators
- Status badges: pill-shaped, muted pastel backgrounds
