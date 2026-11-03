# VAT facts for the shop

This note holds the VAT facts that `vat.py` will be built on. The roastery is a Bergen
business registered for Norwegian VAT (MVA). It sells coffee beans and brewing equipment
(kettles, grinders) online to buyers in Norway, Sweden, Denmark and Finland, and over the
counter in Bergen. Prices are shown with VAT included.

Every fact below was read on the tax or customs authority's own page on **2026-11-03**, and
each one carries its URL. The rule for the code: **no rate from memory.** A rate that is not
in this note, or is marked "not confirmed", is not put into the app until someone reads it
on the authority's page and adds it here.

Norway is in the EEA but outside the EU VAT area and the EU customs union. Sweden, Denmark
and Finland are EU members. So a parcel from Bergen to Malmö, Aarhus or Turku is an export
from Norway and an import into the EU.

## Sources

Short names used in the tables. All read 2026-11-03.

| key | page |
|---|---|
| NO-rates | Skatteetaten, rates: https://www.skatteetaten.no/satser/merverdiavgift/ (also with `?year=2024`, `?year=2026`) |
| NO-hb5 | Skatteetaten, Merverdiavgiftshåndboken 2025, ch. 5: https://oppslag.rettskilder.skatteetaten.no/rettskilder2/type/handboker/merverdiavgiftshandboken/gjeldende/MVA2025_M-5 |
| NO-hb6 | Skatteetaten, Merverdiavgiftshåndboken 2025, 6-21.3: https://www.skatteetaten.no/en/rettskilder/type/handboker/merverdiavgiftshandboken/gjeldende/M-6/M-6-21/M-6-21.3/ |
| NO-toll | Tolletaten, export declaration: https://www.toll.no/no/bedrift/eksport/deklarering-ved-eksport- |
| SE-rates | Skatteverket, rates: https://www.skatteverket.se/foretag/moms/saljavarorochtjanster/momssatserochundantagfranmoms.4.58d555751259e4d66168000409.html |
| SE-news | Skatteverket, news 2026-02-26: https://www.skatteverket.se/omoss/pressochmedia/nyheter/2026/nyheter/livsmedelsmomsensankstill6procent.5.70685bee19c85dd5dd0a3f.html |
| SE-import | Skatteverket, buying goods from outside the EU: https://www.skatteverket.se/foretag/moms/kopavarorochtjanster/inkopfranlanderutanforeu/kopavarorfranlanderutanforeuimport.4.361dc8c15312eff6fd37208.html |
| SE-tull | Tullverket, fees when shopping online: https://www.tullverket.se/privat/panatet/handlapanatet/tullraknarenvadaravgiftenpaminvara/omtullarochavgifternarduhandlarpanatet.4.153f8c8c16ffad23c221cb2.html |
| DK-rate | Skattestyrelsen, Den juridiske vejledning 2026-2, D.A.9: https://info.skat.dk/data.aspx?oid=1921136 |
| DK-coffee | Skattestyrelsen, Den juridiske vejledning 2026-2, E.A.5.3.4 (coffee excise): https://info.skat.dk/data.aspx?oid=2061879 |
| DK-school | skat.dk, buying abroad: https://skat.dk/skole/onlineshopping/naar-du-koeber |
| DK-told | Toldstyrelsen, new duty from 1 July 2026: https://toldst.dk/borger/internethandel/ny-told-fra-1-juli-2026 |
| DK-import | Toldstyrelsen, import specification: https://toldst.dk/erhverv/import/forstaa-din-importspecifikation |
| FI-rates | Vero, rates of VAT (updated 2026-01-01): https://www.vero.fi/en/businesses-and-corporations/taxes-and-charges/vat/rates-of-vat/ |
| FI-changes | Vero, changes to VAT rates: https://www.vero.fi/en/businesses-and-corporations/taxes-and-charges/vat/rates-of-vat/the-changes-to-VAT-rates/ |
| FI-import | Vero, VAT on imported goods: https://www.vero.fi/en/businesses-and-corporations/taxes-and-charges/vat/international-commerce/value-added-taxation-of-imported-goods/ |
| EU-reg | Commission, Register to OSS: https://vat-one-stop-shop.ec.europa.eu/one-stop-shop/register-oss_en |
| EU-guide | Commission, Guide to the VAT One Stop Shop, July 2026 edition: https://vat-one-stop-shop.ec.europa.eu/document/download/55f4ec9d-83e6-4942-9e8d-11d44c243087_en?filename=OSS+Guidelines_revised_1Jan2027_0.pdf |
| EU-eur3 | Commission, The temporary EUR 3 customs duty and the Union handling fee, version of 5 October 2026: https://taxation-customs.ec.europa.eu/document/download/053e5b4e-f0be-4f20-9a23-3e3b659a6676_en?filename=Customs+Guidance+on+EUR+3+customs+duty.pdf |

Finnish Customs (tulli.fi) could not be read: the site answered with a bot check. Finland's
import facts below come from Vero and the Commission.

## Rates

| country | kind | rate | period | source |
|---|---|---|---|---|
| NO | standard (alminnelig sats) | 25 % | in force through 2024, 2025, 2026; start date not confirmed | NO-rates |
| NO | food (næringsmidler) | 15 % | since 2012-01-01 (reduced rate since 2001-07-01, first at 12 %) | NO-hb5; NO-rates |
| SE | standard | 25 % | in force through 2024-2026; start date not confirmed | SE-rates |
| SE | food (livsmedel) | 12 % | up to and including 2026-03-31; start date not confirmed | SE-rates |
| SE | food (livsmedel) | 6 % | 2026-04-01 up to and including 2027-12-31 | SE-news; SE-rates |
| DK | standard | 25 % | in force (JV 2026-2); 2024-2025 editions not read | DK-rate |
| DK | food | 25 % (no reduced rate: "Momssatsen er ens for alle varer og ydelser") | as above | DK-rate |
| FI | standard | 24 % | up to 2024-08-31 | FI-changes; FI-rates |
| FI | standard | 25.5 % | from 2024-09-01 | FI-changes; FI-rates |
| FI | food (groceries) | 14 % | up to 2025-12-31; start date not confirmed | FI-rates |
| FI | food (groceries) | 13.5 % | from 2026-01-01 | FI-changes; FI-rates |

Is roasted coffee "food"?

- **NO:** yes by the definition in § 5-2: "enhver mat- eller drikkevare og enhver annen vare
  som er bestemt til å konsumeres av mennesker". Roasted beans are not named. Coffee served
  for drinking on the premises is a serving service at 25 % (NO-hb5).
- **SE:** yes by the definition: food is "alla ämnen eller produkter som är avsedda för
  människor att äta"; non-alcoholic drinks take the food rate. Beans are not named. Coffee
  drunk in a café is a restaurant service at 12 % (SE-rates).
- **DK:** the question does not arise: one rate for all goods (DK-rate). But Denmark has a
  coffee excise (kaffeafgift): 7.67 kr per kg net weight for roasted coffee (tariff 0901
  21-22), in the table "fra og med 1. januar 2018" (DK-coffee). skat.dk names coffee among the
  goods that carry a special tax on top of duty and VAT when bought from outside the EU
  (DK-school).
- **FI:** yes by the list: the reduced rate covers "food, beverages and food ingredients".
  Coffee is not named (FI-rates).

Equipment (kettles, grinders) is at the standard rate in all four countries: none of the
pages lists such goods under a reduced rate.

## Norway: sales at home and exports

**Buyers in Norway, online or at the till.** The sale is a domestic supply: Norwegian VAT at
15 % on beans, 25 % on equipment (NO-rates, NO-hb5). Beans sold at the counter to take home
are goods at 15 %; coffee served to drink on the premises is 25 % (NO-hb5). That consumer
prices must be shown with VAT included is a consumer-law rule (Forbrukertilsynet), not on a
tax page: not confirmed from the listed sources.

**Buyers abroad: export at 0 %.** "Registrert næringsdrivende skal ikke beregne avgift ved
omsetning av varer ut av merverdiavgiftsområdet" (NO-hb6). The goods must actually leave
Norway, and the seller must document it:

- where a customs declaration is required, with the export declaration and its invoices
  (NO-hb6);
- where none is required, with "salgsdokument og bekreftelse fra transportøren om at varen
  er mottatt for utførsel" (NO-hb6).

Tolletaten: goods that need no permit from another authority and are worth at most
NOK 5,000 per consignment need no export declaration; businesses declare electronically,
through a forwarder or directly in TVINN (NO-toll). So a parcel up to NOK 5,000 goes on the
sales document plus the carrier's confirmation; above that, on an export declaration.

## Import into Sweden, Denmark and Finland: consumers

Every parcel from Bergen to an EU consumer is a distance sale of imported goods. VAT of the
buyer's country is always due, whatever the value: "Du ska alltid betala moms på varor som
du köper från länder utanför EU, oavsett varornas värde" (SE-tull). The rate is the
destination country's rate (SE-tull: 25 % most goods, 6 % food; DK-school: 25 %).

Two ways to collect it:

- **IOSS (the import scheme).** The seller charges the destination VAT at checkout and
  declares it in one EU country; the buyer then pays no VAT at the border (SE-tull). It
  covers consignments whose intrinsic value does not exceed EUR 150, per consignment, and not
  goods subject to excise duties (EU-guide). Freight is not counted in the EUR 150 (DK-school:
  "skal du ikke regne fragten med"). Sweden has fixed EUR 150 at 1,655.30 kr (SE-tull).
- **Without IOSS.** The buyer pays VAT at import. In practice the carrier (e.g. Postnord)
  sends the buyer the bill, with its own handling charge on top (SE-tull; DK-school, which
  puts the carrier charge at 150-250 kr). In Finland a private importer pays import VAT to
  Customs (FI-import).

**Above EUR 150** IOSS cannot be used; VAT is collected at import from the buyer, and customs
duty is charged at the goods' normal tariff rate (SE-tull; DK-told; EU-eur3).

**New customs charges in 2026** (customs, not VAT, but they change the price the buyer pays):

- From 2026-07-01 to 2028-07-01, a temporary customs duty of EUR 3 per item replaces the old
  duty relief for consignments up to EUR 150, where IOSS is used or the goods travel as a
  postal consignment (EU-eur3 §2.1.1). An "item" is counted as customs defines it;
  Toldstyrelsen explains it as one per varepost, that is per tariff code, not per piece
  (DK-told). Goods of preferential origin can claim their preference only when IOSS
  is not used; all IOSS imports pay the EUR 3 (EU-eur3 §5.4).
- From 2026-11-01, a Union handling fee of EUR 2 per item on every distance sale from outside
  the EU, whatever the value (EU-eur3 §3.2; SE-tull). Tullverket states the date as
  1 November 2026; the Commission guidance of 5 October 2026 says "expected to apply from
  1 November 2026", its delegated act then still under scrutiny.
- VAT is charged on top of the duty, and usually on the handling fee too (SE-tull; DK-told).

**Are parcels over EUR 150 typical here?** Not a tax question. A bag of beans is far below
EUR 150; a grinder, or a café's bulk order, may pass it. The app has to handle both cases.

## Import into Sweden, Denmark and Finland: businesses

A VAT-registered business buyer accounts for the import VAT on its own VAT return and deducts
it there, instead of paying it at the border:

- **SE:** "Om du är momsregistrerad och importerar varor ska du redovisa och betala moms på
  importen till Skatteverket", in the period Tullverket issued the customs bill (SE-import).
- **DK:** "Hvis din virksomhed er momsregistreret, skal du ikke indbetale momsen. Den skal du
  i stedet oplyse på momsangivelsen", both as output VAT and, with full deduction, as input
  VAT (DK-import).
- **FI:** an importer on the Finnish VAT register reports import VAT to the Tax
  Administration on its VAT return; others pay Customs (FI-import).

The seller exports at 0 % either way; the business buyer's customs declaration and any duty
are the buyer's (or its forwarder's) side.

## Registration in Sweden, Denmark or Finland

- The EUR 10,000 threshold is for EU-established sellers only and "does not apply to distance
  sales of imported goods" (EU-guide). There is no threshold that switches on for the
  roastery.
- IOSS is optional. A Norwegian supplier whose goods leave from Norway only may register for
  IOSS in any EU country it chooses, **without an intermediary**, because the EU and Norway
  have a VAT mutual-assistance agreement ("Currently only Norway") (EU-reg; EU-guide). One
  registration covers all EU destinations.
- Whether the roastery must register in a destination country if it ships "duties paid" and
  acts as importer of record above EUR 150: not confirmed.

## What this means for the app

- The app charges Norwegian VAT only when the buyer is in Norway, online or at the till:
  15 % on beans, 25 % on equipment, included in the shown price.
- A sale to a buyer in SE, DK or FI is an export: 0 % Norwegian VAT, with an export document
  kept per order (sales document plus carrier confirmation up to NOK 5,000; export
  declaration above).
- The rate depends on the order's date: Sweden's food rate changes on 2026-04-01 (12 to 6 %)
  and again after 2027-12-31; Finland's on 2024-09-01 and 2026-01-01. Rates are rows with
  dates, never constants.
- The buyer's country and type (consumer or business) must be known before a final price is
  shown, since they decide whether any VAT is in the price and whose.
- Without IOSS, a foreign consumer's price shows 0 % VAT and the buyer pays destination VAT,
  any duty and the carrier's charge at delivery. With IOSS (consignments up to EUR 150), the
  app charges the destination country's rate at checkout and the EUR 3 per item duty and
  EUR 2 handling fee land on the roastery or its carrier. Which of the two the shop uses is a
  business decision, not a tax fact.
- An EU consignment's EUR 150 is counted per parcel, on goods without freight; above it IOSS
  is never used.
- A foreign business buyer is invoiced at 0 % and settles import VAT on its own return.
- Coffee to Denmark carries Danish coffee excise on top; the app must not promise a landed
  price for Danish buyers until open point 1 is settled.

## Open points

1. Danish coffee excise on distance sales: who pays it, whether a Norwegian seller must
   register for it, and whether it counts as an "excise duty" that keeps coffee out of IOSS
   (the IOSS exclusion was not read in its legal text). The 7.67 kr/kg rate is shown "fra og
   med 1. januar 2018" in JV 2026-2; whether it is indexed each year was not checked.
2. Customs duty rates on roasted coffee (heading 0901) and on kettles and grinders when
   imported into the EU above EUR 150, and whether EEA preferential origin applies to coffee
   roasted in Bergen: not confirmed.
3. Start dates for NO 25 %, SE 25 % and 12 %, DK 25 %, FI 14 %: not confirmed (each is
   confirmed only as in force for the periods shown). The Skatteetaten rate page does not
   label which year its selector shows; the 15 % food rate rests on the handbook's "since
   1 January 2012".
4. Norwegian export documentation: the 2025 handbook still names form RD 0016/RD 0018;
   which document stands in for it today was not checked with Tolletaten.
5. Seller as importer of record (DDP) above EUR 150: registration duty in the destination
   country not confirmed.
6. Finnish Customs (tulli.fi) pages could not be read; Finland's consumer-side import
   handling (who bills the buyer, carrier fees) is not confirmed beyond Vero's "Customs
   handles your VAT".
7. Out of scope here: the new Union Customs Code changes from 2027-2028 (the EUR 3 duty ends
   2028-07-01; normal duty on all distance sales after that) and the ViDA changes in the OSS
   guide from 2027-01-01. Read again before 2027.
8. The price-display rule for Norwegian consumers (VAT included) comes from consumer law, not
   a listed source: not confirmed here.
