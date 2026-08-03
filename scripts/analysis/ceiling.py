"""
Where is the real ceiling on drainage-water bicarbonate under ERW?

Three candidate ceilings, computed from carbonate equilibria (Plummer & Busenberg
1982 constants, dilute solution, activity coefficients = 1):

  C1  "fixed exogenous pH"  -- [HCO3] = K1*KH*pCO2/[H+] with pH held at the
      soil's PRE-TREATMENT value. This is what the repo's audit computed.
  C2  "carbonate-saturation" -- alkalinity is free to rise (pH is endogenous:
      adding base cations raises pH at fixed pCO2), bounded by the onset of
      calcite (or dolomite/magnesite) precipitation.
  C3  Zhang et al. 2022 riverine limit, back-converted to an added-HCO3
      concentration for comparison.
"""
import numpy as np

def pk(T_C):
    T = T_C + 273.15
    lgKH = (108.3865 + 0.01985076*T - 6919.53/T - 40.45154*np.log10(T)
            + 669365.0/T**2)                      # [H2CO3*]/pCO2, mol/kg/atm
    lgK1 = (-356.3094 - 0.06091964*T + 21834.37/T + 126.8339*np.log10(T)
            - 1684915.0/T**2)
    lgK2 = (-107.8871 - 0.03252849*T + 5151.79/T + 38.92561*np.log10(T)
            - 563713.9/T**2)
    lgKcal = (-171.9065 - 0.077993*T + 2839.319/T + 71.595*np.log10(T))
    # Magnesite, Bénézeth et al. 2011 / PHREEQC llnl: log K ~ -8.03 at 25 C
    lgKmag = -8.03
    return 10**lgKH, 10**lgK1, 10**lgK2, 10**lgKcal, 10**lgKmag

# ---------------------------------------------------------------- C1 and pH(A)
print("=== C1: [HCO3] if soil pH is treated as FIXED and exogenous ===")
print("    (this is the repo audit's 'equilibrium [HCO3] at that cell's own pH')")
T = 15.0
KH, K1, K2, Kcal, Kmag = pk(T)
print(f"    T={T} C:  KH={KH:.4f}  pK1={-np.log10(K1):.3f}  pK2={-np.log10(K2):.3f}  "
      f"pKcalcite={-np.log10(Kcal):.3f}")
for pco2 in (4000e-6, 10000e-6, 40000e-6):
    row = []
    for pH in (5.6, 6.77, 7.77):
        A = K1*KH*pco2/10**(-pH)
        row.append(f"pH {pH}: {A*1e3:8.3f}")
    print(f"    pCO2={pco2*1e6:6.0f} uatm   " + "   ".join(row) + "   mmol/L")

print()
print("=== The same relation read the OTHER way: pH is endogenous ===")
print("    Add base cations at fixed pCO2 -> alkalinity rises -> pH follows.")
print("    pH required to hold a given [HCO3] at pCO2 = 4,000 / 10,000 uatm:")
for A in (0.5e-3, 1e-3, 2e-3, 4e-3, 10e-3, 28.5e-3):
    out = []
    for pco2 in (4000e-6, 10000e-6):
        H = K1*KH*pco2/A
        out.append(f"{-np.log10(H):5.2f}")
    print(f"    [HCO3] = {A*1e3:6.2f} mmol/L  ->  pH {out[0]} / {out[1]}")

# ------------------------------------------------------- C2 saturation ceiling
def alk_at_omega(pco2, omega, T_C, f_Ca, mineral="calcite"):
    """Alkalinity (= [HCO3], mol/L) at which the given carbonate reaches
    saturation state omega, at fixed pCO2. Charge balance: 2*[Ca]+2*[Mg] = [HCO3].
    f_Ca = fraction of the divalent cation charge carried by Ca."""
    KH, K1, K2, Kcal, Kmag = pk(T_C)
    Ksp = Kcal if mineral == "calcite" else Kmag
    f = f_Ca if mineral == "calcite" else (1.0 - f_Ca)
    if f <= 0:
        return np.inf
    # [H+] = K1*KH*pCO2/A ;  [CO3] = K2*A/[H+] = K2*A^2/(K1*KH*pCO2)
    # [M2+] = f*A/2 ;  omega = [M2+][CO3]/Ksp
    #  -> omega = (f*A/2) * K2*A^2/(K1*KH*pCO2*Ksp)
    return (omega * 2.0 * K1*KH*pco2 * Ksp / (f * K2))**(1.0/3.0)

print()
print("=== C2: alkalinity ceiling set by CARBONATE SATURATION, pH endogenous ===")
print("    Basalt-like cation release: Ca and Mg roughly equal charge (f_Ca=0.5).")
print("    Values are [HCO3] in mmol/L.\n")
hdr = f"    {'pCO2 (uatm)':>12} | {'calcite W=1':>11} {'calcite W=10':>12} | {'magnesite W=1':>13}"
print(hdr); print("    " + "-"*(len(hdr)-4))
for pco2u in (1000, 4000, 10000, 20000, 50000, 100000):
    p = pco2u*1e-6
    a1 = alk_at_omega(p, 1.0, 15.0, 0.5, "calcite")
    a10 = alk_at_omega(p, 10.0, 15.0, 0.5, "calcite")
    m1 = alk_at_omega(p, 1.0, 15.0, 0.5, "magnesite")
    print(f"    {pco2u:12d} | {a1*1e3:11.2f} {a10*1e3:12.2f} | {m1*1e3:13.2f}")

print()
print("    Pure-Mg endmember (f_Ca=0, i.e. all Ca retained/taken up), calcite")
print("    cannot form; magnesite is kinetically inhibited at surface T, so the")
print("    thermodynamic bound is effectively absent. Sensitivity to f_Ca at")
print("    pCO2=10,000 uatm, calcite Omega=1:")
for fca in (0.9, 0.5, 0.2, 0.05):
    a = alk_at_omega(10000e-6, 1.0, 15.0, fca, "calcite")
    print(f"      f_Ca={fca:4.2f} -> {a*1e3:6.2f} mmol/L")

# ------------------------------------------------------------- C3 Zhang et al.
print()
print("=== C3: Zhang et al. 2022 (L&O 67, doi:10.1002/lno.12244) back-converted ===")
print("    Their limit is on RIVER water at calcite saturation state Omega,")
print("    not on soil drainage water. Basalt feedstock; 1 mol CO2 -> 1 mol HCO3.")
# Discharge: Dai & Trenberth (2002) global continental discharge 37,288 km3/yr;
# contiguous-US discharge ~1,900 km3/yr (order of magnitude only).
for label, Q_km3, lo, hi, mid in [
        ("global", 37288.0, 7.1, 21.3, 11.1),
        ("contiguous US", 1900.0, 0.26, 0.89, 0.435)]:
    Q_L = Q_km3 * 1e12
    for tag, gt in (("Omega=10 mean", mid), ("range low", lo), ("range high", hi)):
        mol = gt*1e15/44.01
        print(f"    {label:14s} {tag:14s} {gt:6.2f} GtCO2/yr / {Q_km3:8.0f} km3/yr"
              f"  ->  {mol/Q_L*1e3:6.2f} mmol/L added HCO3")

print()
print("=== What the repo's model implies, for comparison ===")
print("    implied [HCO3] p10/p50/p90 = 10.1 / 28.5 / 94.1 mmol/L (from audit)")
print("    repo's own ceiling  p10/p50/p90 = 0.029 / 0.422 / 4.219 mmol/L")
print()
for pco2u, lab in ((4000, "4,000 uatm (Isometric default)"),
                   (10000, "10,000 uatm (typical cropland growing season)")):
    c2 = alk_at_omega(pco2u*1e-6, 1.0, 15.0, 0.5, "calcite")*1e3
    c2b = alk_at_omega(pco2u*1e-6, 10.0, 15.0, 0.5, "calcite")*1e3
    print(f"    C2 ceiling at {lab}: {c2:.2f} (Omega=1) to {c2b:.2f} (Omega=10) mmol/L")
    print(f"      -> median model requirement 28.5 exceeds it by "
          f"{28.5/c2b:.1f}x (Omega=10) to {28.5/c2:.1f}x (Omega=1)")
print()
print("    versus the repo's stated area-weighted mean exceedance of 563x")
