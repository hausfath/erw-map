"""The Maher & Chamberlain high-q flux ceiling, in tCO2/ha/yr.

Key point the repo's item 0 misses: the concentration ceiling and D_w are NOT
independent free parameters. In M&C the flux is

    F = C * q = C_eq * q * (tau*D_w) / (q + tau*D_w)

so as q -> infinity,  F -> C_eq * tau * D_w.  That is a flux ceiling in
mol m^-2 yr^-1 set jointly by C_eq and D_w. Imposing an explicit concentration
ceiling AND separately choosing D_w double-specifies the same physics --
but it also means the observed field CDR range is a joint constraint on
(C_eq, tau, D_w), which is exactly the leverage item 0's sub-problems 2 and 3
need.

Units: C_eq in mol/L, D_w in m/yr.
  F [mol/m2/yr] = C_eq [mol/L] * 1000 [L/m3] * D_w [m/yr]
  -> tCO2/ha/yr = F * 1e4 [m2/ha] * 44.01 [g/mol] / 1e6
"""
import numpy as np

def flux_tco2_ha(C_eq_mmol, D_w, tau=1.0):
    return C_eq_mmol * 1e-3 * 1000.0 * tau * D_w * 1e4 * 44.01 / 1e6

CEQ = [1.0, 3.0, 6.5]     # mmol/L: low; calcite Omega=1 at 4000 uatm; Omega=10
DW  = [0.001, 0.01, 0.03, 0.1, 0.3]
TAU = [("no tau", 1.0), ("tau = e^2", np.e**2)]

print("High-q flux ceiling  F_max = C_eq * tau * D_w,  in tCO2/ha/yr")
print("(this is the MAXIMUM the M&C framework permits at ANY drainage rate,")
print(" for ANY grind, at ANY kinetic rate -- surface area drops out here)")
for tname, tau in TAU:
    print(f"\n  {tname}  (tau = {tau:.2f})")
    print("    D_w (m/yr) |" + "".join(f"  C_eq={c:4.1f} mmol/L" for c in CEQ))
    print("    " + "-"*11 + "+" + "-"*20*len(CEQ))
    for d in DW:
        row = "".join(f"  {flux_tco2_ha(c, d, tau):16.3f}" for c in CEQ)
        print(f"    {d:10.3f} |{row}")

print()
print("Interpretation table: which (tau, D_w) combinations land inside the")
print("range that ERW field trials actually report, taking C_eq = 3.0 mmol/L")
print("(calcite Omega=1 at 4,000 uatm, Ca:Mg charge 1:1):")
print()
for tname, tau in TAU:
    for d in DW:
        f = flux_tco2_ha(3.0, d, tau)
        print(f"  {tname:10s} D_w={d:6.3f} -> {f:7.3f} tCO2/ha/yr")

print()
print("Also: the transport efficiency the repo codes, at its own median q.")
q_med = 0.0749   # m/yr, measured from the build
for tname, tau in TAU:
    for d in (0.03, 0.3):
        eta = q_med / (q_med + tau*d)
        print(f"  {tname:10s} D_w={d:5.3f} -> eta_transport = {eta:.3f} at q = "
              f"{q_med*1000:.0f} mm/yr")
