# The quarry gate at scale: what basalt costs when it stops being waste

Research note, 2026-08-24, companion to `TRUCK_RATE_SOURCES.md`. The map's $10/t
gate is a **byproduct price** — operator-reported quarry-fines deals, several of
them free. This note asks what the gate becomes when ERW demand outgrows the
byproduct stream and has to pay for dedicated primary production, by region.

Conclusion up front: **at scale the US/European gate is $15–22/t, not $10** —
the current default understates it roughly 2× — while Brazil plausibly lands
near $10–15 and India near $4–7. Byproduct pricing is genuinely near-uniform
globally ($0–10/t); at-scale pricing is regional, like the haul rate. And the
supply arithmetic says "at scale" arrives early: identifiable fines-class US
traprock sales are ~5 Mt/yr, so even a 1 Mha US programme at 30 t/ha (30 Mt/yr)
exhausts the byproduct market several times over.

As with the haul note: primary documents fetched directly and read; conversions
and inflation adjustments are ours and shown; anything not from a named primary
is marked *derived* or *unverified*.

## 1. United States — USGS Minerals Yearbook 2023 (primary, current)

[USGS MYB crushed stone, 2023 tables](https://www.usgs.gov/centers/national-minerals-information-center/crushed-stone-statistics-and-information)
(`myb1-2023-stonec-ert.xlsx`), Tables 2 and 12. Traprock is the USGS category
for basalt and diabase.

**Table 2 — by rock type, 2023, f.o.b. quarry:**

| rock type | quarries | Mt sold | **$/t average** |
|---|---|---|---|
| **Traprock (basalt/diabase)** | 259 | 93.0 | **21.33** |
| Granite | 364 | 235 | 21.19 |
| Limestone | 2,007 | 993 | 14.28 |
| All crushed stone | 3,531 | 1,550 | 15.86 |

Basalt is a **premium** rock in the US market — $7/t above limestone. And the
level is rising fast: the all-stone average unit value went $12.69 → $17.50
between 2020 and 2024e ([USGS MCS 2025](https://pubs.usgs.gov/periodicals/mcs2025/mcs2025-stone-crushed.pdf)),
+38% in four years.

**Table 12 — traprock by use, 2023 (computed unit values):** the product classes
closest to what ERW buys:

| traprock product | Mt | $/t |
|---|---|---|
| Stone sand, bituminous (a fines product) | 0.64 | 11.32 |
| Crusher run / fill / **waste** | 0.59 | 12.59 |
| Unspecified fine aggregate | 3.44 | 21.28 |
| Riprap | 0.64 | 14.02 |
| Unspecified graded coarse | 10.6 | 25.75 |
| (granite screenings, traprock's withheld) | 0.89 | 15.01 |

So in the US market, even the classes literally labelled *waste* trade at
**$11–13/t**, and undifferentiated fine aggregate at $21/t. The $0–10/t deals
ERW operators report are real, but they are quarry-by-quarry surplus disposal,
not a market price — the market prices traprock fines above the map's entire
current gate.

**The supply ceiling that forces the at-scale question:** identifiable
fines-class traprock sales (stone sand + unspecified fine + crusher run) total
**~4.7 Mt/yr** — a lower bound, since 62 of the 93 Mt is "unspecified", but the
order of magnitude stands. At 30 t/ha, a US ERW programme covering 3 Mha of
cropland consumes the **entire current US traprock output** (93 Mt/yr), and
10 Mha needs 3.2× it. At that point ERW is not buying anyone's byproduct; it is
the anchor customer of dedicated quarries, and pays full production cost plus
margin — which is what the $21.33/t average *is*.

## 2. Europe — BGS construction aggregates factsheet (2019, primary)

[BGS mineral planning factsheet](https://nora.nerc.ac.uk/id/eprint/524079/):
"Sales of primary aggregates in the UK were some 190 million tonnes in 2017 with
an estimated value of £2258 million based on ex-quarry values" → **£11.9/t
ex-quarry** (2017), ≈ $15.3/t at 2017 fx, *derived* ≈ **$19–20/t in 2026 money**.
The UK Aggregates Levy adds **£2/t** on primary aggregate (the factsheet's
current rate) — a tax that byproduct/waste-derived material can avoid, which is
itself a small structural subsidy for the current waste-fines model that
disappears at scale.

## 3. Brazil and India — operator prices (current) with no primary-market anchor

The repo's existing gate sourcing (`FEEDSTOCK_GATE_SOURCE`): Brazilian *pó de
pedra* at R$45–50/t ≈ **$8–9/t**, Indian raw crusher dust ~₹200/t ≈ **$2.3/t**
(single vendor, weakly sourced). These are already *market* fines prices, not
free-disposal deals, so the at-scale premium is the fines-to-dedicated ratio
rather than a jump from zero. In the US that ratio (waste/fines classes → the
traprock average) is roughly **1.6–1.9×**. Applying it: Brazil at scale
*derived* **~$10–15/t**, India *derived* **~$4–7/t**. Both need a primary
source — Brazil's ANM Anuário Mineral (gov.br blocked non-browser fetches this
session) and the Indian Bureau of Mines yearbook are the upgrades.

## 4. What the ERW literature assumes

[Strefler et al. 2018](https://iopscience.iop.org/article/10.1088/1748-9326/aaa9c4):
"Total costs at 300 km transportation amount to 76 (73/82/143) $ t⁻¹ rock for a
grain size of 20 (50/10/2) µm" — i.e. ~$73–76/t all-in for mining, grinding to
50–20 µm, and 300 km of transport. Netting out their transport (~$15 at their
$0.05/t-km) and fine grinding leaves an implied rock-production cost well above
the observed US market price of finished crushed basalt ($21/t) — the at-scale
literature is, if anything, conservative against what the industry actually
charges. (Their mining investment/O&M split did not extract cleanly from the
HTML and is deliberately not quoted here.)

Grinding from fines/crusher sizes to ERW spec is small against all of this:
~$1/t to p80 100 µm, ~$2/t to p80 50 µm (Frontiers in Climate 2024, already
cited in `constants.py`).

## 5. Boundary with the fixed haul charge — no double count

A fair question once both exist: is the fixed trip charge (50 km-equivalent at
the regional rate, $2.25–5.50/t) already inside the gate price? No, and the
boundary is clean. The gate is an **f.o.b. quarry** price — USGS unit values and
the operator-reported prices alike — which by definition includes the *quarry's*
loading service (its loader, its operator, its wear). The trip charge is
decomposed from USDA **trucking** rates, which are what shippers pay haulers and
exclude the commodity and its loading service: it is the *hauler's* fixed
per-trip cost — truck and driver time while being loaded and while tipping at
the field, plus positioning. Different party, different invoice, and it is
exactly why the trucking per-mile rate falls with distance while the f.o.b. rock
price does not. (What is in **neither**: spreading the rock on the field, which
the model does not price at all.)

## 6. Comparison table

| region | today (byproduct deals) | fines market price | **at-scale dedicated** | basis |
|---|---|---|---|---|
| US | $0–12 (operator-reported) | $11–15 (USGS T12) | **$15–22** | USGS 2023, primary |
| UK/Europe | ~$0–10 | — | **$15–20** (+£2/t levy in UK) | BGS 2017 + CPI, *derived* |
| Brazil | $8–9 (pó de pedra) | $8–9 | **~$10–15** | operator prices × US fines→dedicated ratio, *derived* |
| India | ~$2–3 (crusher dust) | ~$2–3 | **~$4–7** | single weak source × ratio, *unverified* |

Against these, the map's uniform $10/t gate is a fair description of **current
procurement** (the middle of the byproduct range, above the free deals) and an
understatement of **at-scale procurement** in the US and Europe by roughly 2×,
while being roughly right for at-scale Brazil and generous for India.

## 7. What this means for the map

1. **The gate does not move the map** (the penalty applies to the haul increment
   only), so none of this changes the colour. It changes every reported $/t and
   $/tCO₂ and the cost-screened headline total, and the sensitivity is severe —
   measured on the shipped build (regional haul; $100/tCO₂ screen against each
   application's discounted lifetime carbon at 5%; drainage-limited carbon
   counted, unit-cost screen unclamped — the footer basis since 2026-08-24):
   gate **$10 → 0.24 GtCO₂/yr on 0.27 Gha; $12 → 0.20 on 0.21; $18 → 0.07 on
   0.07; $21.50 → 0.02 on 0.02**. (On the pre-ceiling footer the same sweep
   read 0.93 / 0.79 / 0.30 / 0.06 Gt — the *area* response to the gate is
   nearly identical; the drainage limit rescales the carbon each kept hectare
   yields.) At the US at-scale gate, the $100/tCO₂ screen collapses toward
   nothing — gate plus the fixed trip charge alone is $42–54/tCO₂ of year-one
   carbon (less against lifetime carbon, but the haul still stacks on top)
   before any grinding, spreading or MRV. The at-scale question is therefore
   not a parameter nicety; it decides whether the sub-$100 map has much area
   in it.
2. **The gate slider now spans $0–25** so the at-scale US/European value is
   reachable; it previously capped at $15, below the observed US traprock
   average. The default stays $10/t — the current-procurement number — because a
   single global at-scale value would be *more* wrong than a single global
   byproduct value: byproduct pricing is near-uniform globally, at-scale pricing
   is regional.
3. **The right implementation of "at scale" is a regional gate**, which already
   has a tracked item (`to_do` 10.4, `FEEDSTOCK_GATE_REGIONAL_USD_T`) and a
   known blocker: the gate-cancellation logic in the value function is only
   coherent while the gate is spatially uniform. Regionalising the gate means
   deciding whether regional gate differences should move the map (they carry
   real spatial information, unlike a uniform gate). That decision should be
   made once, alongside at-scale values: proposed at-scale regional gates
   US/CA $18, Europe $17, Brazil $12, India $5, elsewhere $12 — all above,
   sourced or flagged.

## Search-path note

Compiled without web search (session budget exhausted); documents fetched
directly by URL. Remaining upgrades: ANM Anuário Mineral (Brazil), IBM Indian
Minerals Yearbook, and Beerling et al. 2020's SI mining-cost assumptions
(paywalled this session).
