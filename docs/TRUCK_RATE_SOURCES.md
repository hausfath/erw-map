# What does trucking rock actually cost? Sources behind the haul rate

Research note, 2026-08-24. The map ships `TRUCK_COST_USD_T_KM = 0.12` as a single
global rate, flagged in `constants.py` as an assumption with no citation. This
note is the first attempt to source it. Conclusion up front: **$0.12/t-km is a
good number for the United States at the map's median haul and roughly twice too
high for Brazil and India** — the two countries with the most active ERW
deployment — so the error is regionally structured, not random. A single global
rate misprices the Global South, and the fix is a small regional rate table, not
a different global constant.

Everything here was read from the primary document named (fetched directly;
quotes verified against the page or PDF), except where marked *derived* or
*unverified*. Currency conversions and inflation adjustments are ours and are
shown.

## 1. United States — USDA Grain Truck and Ocean Rate Advisory (current, primary)

[USDA AMS GTOR, 2nd quarter 2026](https://www.ams.usda.gov/services/transportation-analysis/gtor)
(published July 2026). Quarterly survey of grain elevators by North Dakota State
University; rates are per loaded mile per truckload at an 80,000 lb GVW limit, and
the report states "The truck is assumed to carry 55,000 lbs. or 25 metric tons".
Grain hauling is the closest well-surveyed analog to hauling crushed rock to
farms: same regions, same dump/hopper equipment class, same seasonal rural market.

| haul | $/mile/truckload (Table 1) | **derived $/t-km** | derived $/t for the trip |
|---|---|---|---|
| 25 miles | 7.53 | **0.187** | 7.53 over 40 km |
| 100 miles | 4.84 | **0.120** | 19.36 over 161 km |
| 200 miles | 4.09 | **0.102** | 32.72 over 322 km |

Two things follow. First, at the map's cropland-median haul of 275 road km
(171 mi), the US rate interpolates to **$0.10–0.12/t-km — the shipped $0.12 is
squarely a current US number.** Second, the per-mile rate falls with distance
because a fixed per-trip cost (loading, unloading, positioning) is spread over
more km. Decomposing the three points: **fixed ≈ $3.6–6.0/t per trip plus
$0.083–0.098/t-km marginal.** The map's pure `rate × distance` therefore
*understates* short hauls (<100 km) and *overstates* long hauls, US-anchored.

## 2. Global comparison — World Bank, *Transport Prices and Costs in Africa* (2007, primary)

Teravaninthorn & Raballand 2009, [World Bank Directions in Development](https://documents.worldbank.org/en/publication/documents-reports/documentdetail/278561468201609212)
(ISBN 978-0-8213-7650-8; PDF read directly). Figure 2.1, "Average Transport
Prices: A Global Comparison in 2007", in US cents per tonne-km, long-haul
corridors, general freight:

| corridor / region | 2007 ¢/t-km (Fig 2.1) | *derived* ≈2026 $ (×1.55 US CPI) |
|---|---|---|
| Pakistan | 2 | 0.031 |
| Brazil | 3.5 | 0.054 |
| United States | 4 | 0.062 |
| China | 5 | 0.078 |
| Western Europe (France, long-distance) | 5 | 0.078 |
| Africa: Durban–Lusaka | 6 | 0.093 |
| Africa: Lomé–Ouagadougou | 7 | 0.109 |
| Africa: Mombasa–Kampala | 8 | 0.124 |
| Africa: Douala–N'Djaména | 11 | 0.171 |

Table 2.2 gives operating *costs* per vehicle-km (2007): Central Africa $1.88,
East Africa $1.02, France $1.59 — with payload utilisation 75–87%, i.e. costs of
roughly $0.05–0.09/t-km, with African *prices* elevated above costs by cartel
margins (the book's central finding).

Caveats: these are 2007 prices for long-haul international corridors, general
freight, not short-haul tipper work; the ×1.55 CPI adjustment is US inflation
applied to other countries' dollar prices, which is crude. The US row (4¢ 2007 ≈
6¢ today) sits below the USDA 200-mile rate (10¢) — the gap is the long-haul vs
farm-market difference, and it brackets how much market segment matters.

## 3. India — NITI Aayog / RMI, *Fast Tracking Freight in India* (2021, primary)

[Report PDF](https://www.niti.gov.in/sites/default/files/2021-06/FreightReportNationalLevel.pdf),
Exhibit 3-1, cost by mode in INR/tonne-km: road **3.6**, rail 1.6, waterways 2,
air 18 ("5 times the rate of road transport", which anchors the road reading),
pipeline 2. At the 2021 exchange rate (₹74.5/$): **$0.048/t-km**. Note the
extraction of this exhibit interleaves footnote markers with values; the air
anchor is what makes the road figure unambiguous.

## 4. The ERW literature — Strefler et al. 2018 (primary)

[Strefler et al. 2018, *ERL* 13 034010](https://iopscience.iop.org/article/10.1088/1748-9326/aaa9c4):
"we use the cost estimate for transport on road of 0.05 $ km⁻¹ t⁻¹", explicitly
an **upper estimate**, with rail ~2× and ship ~50× cheaper. So the ERW
literature's *upper* transport estimate is at the *cheap* end of observed market
rates and 2.4× below this map's default — worth knowing when comparing our $/t
against published ERW cost curves. (Beerling et al. 2020's transport assumptions
are in their paywalled SI and could not be read this session.)

## 5. Gate-cost cross-check — USGS Mineral Commodity Summaries 2025 (primary)

[USGS MCS 2025, crushed stone](https://pubs.usgs.gov/periodicals/mcs2025/mcs2025-stone-crushed.pdf):
US average unit value **$17.50/t (2024e)**, up from $12.69 in 2020. Consistent
with the repo's existing note that graded-product averages sit at $15–18/t and
fines below that; the $10/t gate default stands.

## 6. Assessment of the $0.12 default

| region | best estimate $/t-km | $0.12 is… | source quality |
|---|---|---|---|
| US (100–300 km haul) | 0.10–0.12 | **right** | current, primary, quarterly |
| US short-haul (<50 km) | 0.15–0.19 | low | same |
| Western Europe | ~0.08–0.10 | ~1.3× high | 2007 + inflation; weak |
| Brazil | ~0.05–0.06 | **~2× high** | 2007 + inflation; dated |
| India | ~0.045–0.05 | **~2.5× high** | 2021 national avg |
| China | ~0.07–0.08 | ~1.6× high | 2007 + inflation; weak |
| Africa (corridors) | 0.09–0.17 | about right to low | 2007; cartel-inflated prices |
| Pakistan / S Asia | ~0.03–0.05 | ~3× high | 2007 + inflation |

The bias is not noise: it lands on Brazil and India, which hold much of the
warm, wet, high-CDR cropland *and* most current ERW deployment. A uniform $0.12
systematically overstates delivered cost — and therefore understates
suitability-with-cost — in exactly the places the physics favours.

## 7. Recommendation

1. **Regionalise the rate** rather than change the global default. A short
   country-group table (US/Canada 0.10, Europe 0.09, Brazil/Latin America 0.055,
   India/South Asia 0.045, China/SE Asia 0.07, Africa 0.11, elsewhere 0.08)
   captures the first-order structure. The truck slider then becomes a global
   multiplier on the regional surface, and the harness identity test still holds.
2. **Add the fixed per-trip component**: `haul = F + r·d` with F ≈ $5/t, which
   the USDA distance curve demands and which changes the shape (short hauls get
   dearer, long hauls cheaper) independently of any regional level.
3. Vintage flags stay mandatory: only the US number is current; Brazil, China and
   Europe rest on 2007 prices inflated by US CPI, and India on a 2021 national
   average. Each regional entry should carry its source and year in
   `constants.py`, the way `FEEDSTOCK_GATE_REGIONAL_USD_T` already does.
4. The strongest possible upgrade remains a validation against the
   verified-delivery fixture's actual delivered costs, if those fields exist —
   that would convert all of this from benchmarks to calibration.

## Search-path note

Compiled without web search (session budget exhausted): documents were fetched
directly by URL and read as PDFs. ATRI's *Operational Costs of Trucking* (the
standard US long-haul cost survey) and current CNR European costs were not
retrievable this way and are worth adding when search is available; neither is
likely to move the table above by much, since USDA covers the US farm market
directly.
