# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React with Vite and TypeScript (the owner's preference, 2026-11-07), in `apps/storefront`. It
talks to the shop's HTTP API (FastAPI, `packages/api`) over the Python service layer in
`packages/shop`. Runs locally for now; hosting is planned later.

## Users

People in Norway, Sweden, Denmark and Finland who buy coffee beans and brewing equipment
online for home, mostly on a phone or laptop in the evening. Bergen locals also use the site
to check on the shop before they walk in. They come in from the newsletter, from ads, or
directly.

## Product Purpose

The web shop of a small coffee roaster in Bergen that sells beans and brewing equipment. A
visitor browses the beans and the gear, puts some in a cart, checks out as a guest and pays.
Afterwards they can follow the order from a private link. Success: a first-time visitor
understands what the roaster sells and gets from the home page to a placed, paid order
without help.

## Positioning

A roaster from Bergen, where it rains on most days of the year. The beans are roasted in the city and
sold over the counter, Monday to Saturday, as well as on the web. The Bergen counter, with
its loose espresso sold by the gram and its club, is a fact a generic coffee shop cannot
copy.

## Operating Context

- **Countries:** Norway, Sweden, Denmark and Finland. Prices are stored in NOK. They are shown
  in the buyer's currency: NOK, SEK, DKK or EUR.
- **VAT:** Norwegian buyers pay VAT included (15% on beans, 25% on equipment). For buyers in
  Sweden, Denmark and Finland the sale is an export with no Norwegian VAT. Swedish and Finnish
  buyers pay import VAT on delivery. Denmark gets no landed-price promise (coffee excise).
- **Checkout:** guest only, with no logins. The country is chosen before a final price is shown.
- **Payment:** a sandbox for now, labelled as a test.
- **The counter in Bergen:** open Monday to Saturday, closed on Sundays. It has its own till.

## Capabilities and Constraints

- **The catalogue:**
  - P-10 Morning roast: Ethiopia, light, washed, 250 g, NOK 129.
  - P-11 Dark espresso: Brazil, dark, natural, 1000 g, NOK 349.
  - P-12 Decaf: Colombia, medium, washed, 250 g. No price yet, so it is "coming soon".
  - P-20 Hand grinder: wood, 24-month warranty, NOK 899.
  - P-21 Pour-over kettle: steel, 12-month warranty, NOK 549.
- **Categories:** Beans (Filter, Espresso) and Equipment (Kettles, Grinders › Hand grinders).
- **Campaigns** are dated percentage discounts, for example "Brew at home", 15%, 16–29 November
  2026.
- **The server owns every price.** The client never sends one.
- **Out of scope for now:** subscriptions (the shop has one plan, a bag a month, but guests
  cannot manage it), business accounts, refunds, real payments.
- **Undecided:** shipping prices and delivery times (none exist in the data), and the shop's
  street address.

## Brand Commitments

- **Name:** Sydvest Kaffebrenneri; the wordmark is "Sydvest" (the owner, 2026-11-07). A sydvest
  is the sou'wester rain hat, and the south-west wind that brings Bergen its rain.
- **Theme:** dark by default, with a light theme too (the owner's binding constraint).
- **Mood:** Bergen in autumn, dark and rainy most of the time, and cozy (the owner's words).

## Evidence on Hand

- The real catalogue, prices, campaigns, countries and VAT facts (`docs/facts/vat.md`,
  `packages/spec/contract.md`).
- The cafés and offices that buy from the roaster, in the simulated data (for example
  Fjordkontoret and Kahvila Kallio). They are fictional, and none of them gave a quote.
- **Absent, and must not be invented:** testimonials, reviews, press, awards, shipping prices,
  delivery promises, staff photos, a founding story or year.

## Product Principles

1. The server is the single source of every price, VAT line and stock state. The page
   never guesses.
2. Honest money: show the buyer's currency and the right VAT wording for their country.
   Promise no landed price that is not true.
3. A guest can buy without an account, and can come back to the order from a private link.
4. Bergen is a fact, not a costume: the counter, the hours and the rain are real context.

## Accessibility & Inclusion

WCAG 2.2 AA contrast in both themes. Every flow works with a keyboard. Motion respects
`prefers-reduced-motion`. Prices are read out with their currency.
