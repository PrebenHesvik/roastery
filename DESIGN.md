---
name: Sydvest Kaffebrenneri
description: A Bergen coffee roaster's web shop, in oilskin yellow on wet slate.
colors:
  ground: "#11161b"
  surface: "#1a2128"
  surface-raised: "#212a32"
  text: "#e9e6df"
  muted: "#a7afb7"
  rule: "#2a323a"
  rule-strong: "#3d4751"
  oilskin: "#f3c623"
  oilskin-hover: "#ffd84a"
  oilskin-edge: "#f3c623"
  oilskin-text: "#f3c623"
  on-oilskin: "#1b1608"
  on-oilskin-muted: "#4a3d0c"
  window: "#e8a04a"
  window-field: "#e8a04a"
  on-window: "#1b1608"
  on-window-muted: "#4a2f0c"
  danger: "#f2937f"
  scale-off: "#343c45"
  focus: "#f3c623"
typography:
  display:
    fontFamily: "Schibsted Grotesk Variable, system-ui, sans-serif"
    fontSize: "6rem"
    fontWeight: 800
    lineHeight: 0.9
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Schibsted Grotesk Variable, system-ui, sans-serif"
    fontSize: "2.75rem"
    fontWeight: 800
    lineHeight: 1.02
    letterSpacing: "-0.03em"
  section:
    fontFamily: "Schibsted Grotesk Variable, system-ui, sans-serif"
    fontSize: "2.25rem"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Schibsted Grotesk Variable, system-ui, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 700
    lineHeight: 1.2
  body:
    fontFamily: "Schibsted Grotesk Variable, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  small:
    fontFamily: "Schibsted Grotesk Variable, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Schibsted Grotesk Variable, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    letterSpacing: "0.12em"
  figures:
    fontFamily: "Schibsted Grotesk Variable, system-ui, sans-serif"
    fontWeight: 700
    fontFeature: "tnum"
rounded:
  none: "0"
spacing:
  gutter: "56px"
  gutter-mobile: "20px"
  card-gap: "20px"
  card-pad: "22px"
  panel-pad: "32px"
  section: "128px"
  section-mobile: "88px"
components:
  button-primary:
    backgroundColor: "{colors.oilskin}"
    textColor: "{colors.on-oilskin}"
    rounded: "{rounded.none}"
    padding: "11px 20px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.oilskin-hover}"
    textColor: "{colors.on-oilskin}"
  button-ink:
    backgroundColor: "{colors.on-oilskin}"
    textColor: "{colors.oilskin}"
    rounded: "{rounded.none}"
    padding: "11px 20px"
    height: "44px"
  button-line:
    textColor: "{colors.oilskin-text}"
    rounded: "{rounded.none}"
    padding: "11px 20px"
    height: "44px"
  button-line-hover:
    backgroundColor: "{colors.oilskin}"
    textColor: "{colors.on-oilskin}"
  button-ink-line:
    textColor: "{colors.on-oilskin}"
    rounded: "{rounded.none}"
    padding: "11px 20px"
    height: "44px"
  button-quiet:
    textColor: "{colors.text}"
    rounded: "{rounded.none}"
    padding: "11px 20px"
    height: "44px"
  button-soon:
    textColor: "{colors.muted}"
    rounded: "{rounded.none}"
    padding: "8px 14px"
    height: "38px"
  button-small:
    padding: "8px 14px"
    height: "38px"
  bag-chip:
    backgroundColor: "{colors.oilskin}"
    textColor: "{colors.on-oilskin}"
    rounded: "{rounded.none}"
    padding: "8px 14px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.none}"
    padding: "{spacing.card-pad}"
  side-panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.none}"
    padding: "28px"
  field-input:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.text}"
    rounded: "{rounded.none}"
    padding: "10px 12px"
    height: "46px"
  choice-option-selected:
    backgroundColor: "{colors.oilskin}"
    textColor: "{colors.on-oilskin}"
    rounded: "{rounded.none}"
    padding: "14px 16px"
  coat:
    backgroundColor: "{colors.oilskin}"
    textColor: "{colors.on-oilskin}"
    typography: "{typography.display}"
    padding: "56px 56px 48px"
  window-light:
    backgroundColor: "{colors.window-field}"
    textColor: "{colors.on-window}"
    padding: "48px 48px 40px"
---

# Design System: Sydvest Kaffebrenneri

## Overview

**Creative North Star: "The Oilskin Coat in the Rain"**

Sydvest is a Bergen roaster seen on a dark, wet evening. The ground is wet slate with a faint slanted rain streak; the brand is an oilskin-yellow coat, a flat material field that carries the headline and every primary action. Warmth comes from one other source only: window amber, the light of the counter seen from the street, used for what is "inside and warm" (the counter, its hours, the roast scale). Dark is the default whatever the system prefers; a considered light theme ("overcast noon") puts the same coat on fog grey with slate ink.

The system is square and plain. Everything is cut with 0 radius and 1px rules except the coat, which has one curved oilskin edge. One typeface, Schibsted Grotesk, does everything from a 96px heavy headline to tabular prices. Depth is tonal: slate steps up to raised slate, and the coat alone casts a soft shadow. Density is moderate: the home page is a sequence of distinct shapes (coat and shelf, gear split, lit window, four-column money rows, closing coat); the working pages (shop, product, bag, checkout, pay, order, the counter) are quiet two-column layouts with a surface side panel.

The build refuses the roaster default of kraft paper, stamps and cream, and it ships no photography: products are named, described in facts, and shown by their roast scale.

**Key Characteristics:**
- Oilskin yellow as a material field, never a tint: flat, edged, with oil-ink text on it.
- Window amber only for the counter, hours and roast fill; never on an action.
- Square everywhere; one curved coat edge per coat.
- One grotesk, heavy and tight at display sizes, tabular in figures.
- Tonal slate layering with 1px rules; the coat is the only lifted thing.
- Rain is ambient: a fixed slanted streak on the ground and a quiet canvas behind the home page's first viewport.

## Colors

Wet slate neutrals, one loud material (oilskin yellow) and one warm light (window amber); every colour is a token on `:root` with a light-theme counterpart set by `data-theme="light"`.

### Primary
- **Oilskin Yellow** (`oilskin`): the coat panels, the primary button, the bag chip, the selected checkout option, the done steps of the order track, the skip link. Same value in both themes; it is the brand, so it does not move.
- **Bright Oilskin** (`oilskin-hover`): hover on any oilskin field.
- **Oilskin as Text** (`oilskin-text`): links, the active nav underline, the active shelf, the line button. In dark it is the yellow itself; in light it darkens to a deep olive-gold (#6e5200) to hold AA on fog.
- **Oil Ink** (`on-oilskin`, `on-oilskin-muted`): text and ink buttons on the coat. The ink button (oil ink with yellow text) is the action inside a coat.

### Secondary
- **Window Amber** (`window`): the counter's "open today" line, the visit page's today line, and the roast scale's filled steps. In light it becomes a burnt amber (#8a4a00) so it reads as text and as fill on fog.
- **Window Field** (`window-field`, `on-window`, `on-window-muted`): the lit half of the counter panel, with a pale slanted light stripe across it. In light it stays a pale amber field (#f2b866).
- **Window Glow / Spill** (sidecar): translucent amber radial and linear gradients behind the stage foot, the hours panel and the counter pane; warmth by light, not by shadow.

### Neutral
- **Wet Slate** (`ground`): the page, with a 1px streak every 47px at 100 degrees. Inputs and unselected choices sit on it.
- **Raised Slate** (`surface`, `surface-raised`): cards, side panels, the counter pane, notices; `surface-raised` for hover fills and the skeleton highlight.
- **Chalk** (`text`) and **Mist** (`muted`): primary and secondary text.
- **Rules** (`rule`, `rule-strong`): 1px dividers and card borders; `rule-strong` for inputs, quiet buttons and the quantity stepper.
- **Scale Off** (`scale-off`): unfilled roast steps, unfilled track steps, disabled primary.
- **Danger** (`danger`): errors, stock shortfalls, invalid fields; a soft coral in dark, a brick red (#9b2c17) in light.
- **Focus** (`focus`): oilskin yellow in dark, slate ink in light.

### Named Rules
**The Coat Rule.** Oilskin fields and actions are opaque yellow, never a wash or a gradient; the one translucent oilskin is the text-selection highlight. On it, text is oil ink (`on-oilskin`); in the light theme every oilskin field carries a 1px ink edge (`oilskin-edge`).

**The Window Rule.** Amber means "inside, warm": the counter, its hours, the roast. No button, link, selection or price is amber.

**The Two Themes Rule.** Every colour is a token with a dark and a light value; no colour is written for one theme only. Dark is the default regardless of the system preference.

## Typography

**Display Font:** Schibsted Grotesk Variable (with system-ui, sans-serif)
**Body Font:** Schibsted Grotesk Variable
**Label/Mono Font:** none; figures use tabular numerals of the same face.

**Character:** One Norwegian news grotesk carries the whole shop: heavy (800) and tightly tracked at display sizes, plain at 400 for reading, 700 for prices and actions.

### Hierarchy
- **Display** (800, 6rem, 0.9, -0.035em): the coat headline only; 4.75rem under 1180px, `clamp(3rem, 15vw, 4.5rem)` under 960px. The closing coat uses 4.5rem / 0.95.
- **Headline** (800, 2.75rem, 1.02, -0.03em): page titles; 4rem / 0.95 on product, order, visit and not-found; 2.125rem on mobile. The counter pane title is 3rem / 1.
- **Section** (800, 2.25rem, 1.05, -0.03em): home section titles; 2rem on mobile.
- **Title** (700 to 800, 1.375rem, 1.2): card names, legends, panel headings, totals.
- **Body** (400, 1rem, 1.5): running text; ledes at 1.0625 to 1.1875rem, measure 30rem to 64ch. Product copy 1.125rem / 1.6, max 62ch.
- **Small** (400, 0.875rem): facts lines, notes, footer, crumbs, hints (0.8125rem).
- **Label** (600, 0.6875rem, 0.12em, uppercase): only the roast scale's Light and Dark ends; the sandbox's TEST badge (800, 0.8125rem, 0.16em) is the only other uppercase text.

### Named Rules
**The Tight Heavy Rule.** Display, headline and section titles are 800 with negative tracking (-0.015em base, -0.03em to -0.035em at headline and display) and `text-wrap: balance`. Body never goes below 400 or above 1.1875rem.

**The Honest Figures Rule.** Prices, totals, quantities and outputs use tabular numerals, never break across lines, and are set at 700 or 800.

## Layout

A 1328px container with 56px gutters (20px under 960px). The home page's first viewport is a two-column stage: a 640px coat panel flush to the left edge, and the shelf on slate to its right with the counter line at its foot; it falls to equal columns at 1180px and to one column at 960px, where the coat keeps a 20px right margin. Sections below are separated by 128px (88px mobile); the closing coat is flush to the right edge, mirroring the hero.

Working pages use a main column plus a sticky surface side panel (bag, checkout at 400px; product, order, visit at 1.4fr / 1fr), with 48 to 72px gaps; all collapse to one column at 960px. Product grids use `repeat(auto-fill, minmax(260px, 1fr))` with 20px gaps. The shop has a 200px sticky shelf list that becomes a wrapping row on mobile. The header wraps on mobile: nav moves to a full-width row with a rule beneath, and the bag chip drops its word to keep its count.

Breakpoints: 1180px and 960px (sidecar).

## Elevation & Depth

Flat with tonal layering. Slate steps up from `ground` to `surface` to `surface-raised`, every container is bounded by a 1px rule, and hover deepens the rule rather than lifting the box. One soft ambient shadow exists, on the hero coat, so the coat reads as a material hung in front of the street. Warmth is conveyed with translucent amber gradients (glow and spill), never with shadow.

### Shadow Vocabulary
- **Coat Hang** (`--shadow`, see sidecar for both themes): the hero coat only.

### Named Rules
**The One Hung Coat Rule.** Only the hero coat casts a shadow. Cards, panels and buttons stay flat; depth elsewhere is tone and rule.

## Shapes

Square corners (0 radius) on every button, input, card, panel, chip and stepper. The one exception is the coat: a large elliptical corner (220px by 120px; 120px by 72px under 960px), top-right on the hero coat, which is flush left, and top-left on the closing coat, which is flush right. A coat never has more than one curved corner, and the edge it sits on loses its border. Dashed 1px borders mark the provisional: the Soon button and the sandbox payment panel. Icons are drawn on a 24 grid with a 1.75 stroke, square caps and mitre joins.

## Components

### Buttons
Square, bold, 44px tall.
- **Shape:** square (0), 1px border, `11px 20px`, 700 at 0.9375rem; small is 38px tall at `8px 14px`, 0.875rem.
- **Primary:** oilskin field, oil-ink text, `oilskin-edge` border; hover brightens to `oilskin-hover`. Disabled falls to `scale-off` with muted text.
- **Ink:** oil-ink field with yellow text; the action inside a coat (the hero Add, the closing Shop).
- **Line:** transparent with an `oilskin-text` border and text; hover fills with oilskin.
- **Ink line:** transparent with an oil-ink border, the secondary action inside a coat.
- **Quiet:** transparent, chalk text, `rule-strong` border; hover takes the border to chalk.
- **Soon:** transparent, muted text, 1px dashed muted border, disabled: a product with no price.
- **Hover / Focus:** 160ms ease-out on background, colour and border. Focus is a 2px `focus` outline at 3px offset; on oilskin fields the outline turns oil ink.

### Chips
- **Bag chip:** oilskin field, oil-ink 700, 16px bag icon and count; the count bumps in (420ms) when an item is added.

### Cards / Containers
- **Corner Style:** square (0).
- **Background:** `surface`.
- **Shadow Strategy:** none (see Elevation).
- **Border:** 1px `rule`, to `rule-strong` on hover (200ms).
- **Internal Padding:** 22px cards; 28 to 32px side panels (22px 18px mobile).
- A product card is name (title), facts line (small, muted), then the roast scale for beans or one line for gear, then a buy row: price left, Add right.

### Inputs / Fields
- **Style:** `ground` fill, 1px `rule-strong`, square, 46px tall, `10px 12px`; label 0.875rem 700 above, hint 0.8125rem muted below.
- **Focus:** 2px `focus` outline at 0 offset and the border turns `focus`.
- **Error / Disabled:** border turns `danger`; the error text is 0.8125rem 600 in `danger`.
- **Choice options** (country): a grid of square `ground` tiles with `rule-strong` borders; the checked tile becomes an oilskin field.
- **Quantity stepper:** one `rule-strong` box, 38px minus and plus, tabular count between rules.

### Navigation
- **Header:** the Sydvest wordmark (800, 1.5rem, +0.02em) left; nav links 0.9375rem in mist, chalk on hover, the current page chalk with a 1px `oilskin-text` underline; then the country select (a bordered-on-hover button), the 38px square theme toggle, and the bag chip.
- **Shop shelves:** a vertical list with a 1px left rule; the current shelf turns `oilskin-text` with its rule.
- **Mobile:** nav drops to a full-width row under a rule; shelves wrap inline with an underline for the current one.

### Roast Scale (signature)
Seven rising bars (20% to 100% high) with 3px gaps, 34px tall on cards and 64px large on the product page; unfilled steps are `scale-off`, this roast's steps fill in `window` from the bottom with a 900ms ease-out and a 90ms stagger when the scale enters view. Light and Dark are labelled at the ends in the uppercase label style.

### The Coat (signature)
The oilskin panel: the hero coat (the display headline, a lede, the ink Add with its price, a muted VAT note) and the closing coat. One curved corner, flush to a page edge, oil-ink everything.

### The Lit Window (signature)
The counter pane: the text half on raised slate with an amber spill, the facts half on the `window-field` with a pale slanted light stripe and oil-ink rows between translucent ink rules. Unsettled facts (the street address) are set italic and muted.

### Rain
A canvas behind the home stage: at most 140 slanted streaks in three alpha layers, coloured from `--rain`; it stops off-screen and draws one still frame under reduced motion.

## Do's and Don'ts

### Do:
- **Do** put every primary action and every selection on oilskin yellow, with oil-ink text and the `oilskin-edge` border.
- **Do** use the ink button for the action inside a coat, and the ink-line button for its second action.
- **Do** keep amber to the counter, its hours and the roast scale fill.
- **Do** set every colour through a token that has both a dark and a light value; keep dark the default.
- **Do** keep corners square; give a coat one curved corner (220px by 120px) and sit it flush on a page edge.
- **Do** show prices in tabular figures at 700 or more, with their currency, and never wrapped.
- **Do** mark a fact the shop has not settled (address, shipping) as italic muted text rather than inventing it.
- **Do** honour `prefers-reduced-motion`: the rain stills and all transitions collapse.

### Don't:
- **Don't** put amber on a button, link, price or selection.
- **Don't** round a button, card, input or panel.
- **Don't** add a second typeface.
- **Don't** cast shadows from cards, panels or buttons; the hero coat is the only hung thing.
- **Don't** use kraft paper, stamps, cream paper or stock photos of coffee bags.
- **Don't** fade or gradient an oilskin field or action; translucent oilskin is for text selection only.
