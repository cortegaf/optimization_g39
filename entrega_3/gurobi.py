#!/usr/bin/env python3
# ----------------------------------------------
#  Las Condes water MILP – stand-alone script
#  run with:  python solve_model.py --out results/
# ----------------------------------------------
import argparse, yaml, pandas as pd, gurobipy as gp
from gurobipy import GRB
from pathlib import Path
from construccion_et import build_ET_dict, load_irrigation_zones

# ------------------------------------------------------------------
# 1. CLI and file paths
# ------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--data", default=".", help="folder with .csv/.yaml")
parser.add_argument("--out",  default="results", help="output folder")
parser.add_argument("--nosolve", action="store_true",
                    help="omitir optimización y cargar solution.sol si existe")
args = parser.parse_args()
data_dir = Path(args.data)
out_dir  = Path(args.out);  out_dir.mkdir(exist_ok=True)

# ------------------------------------------------------------------
# 2. Load dataset
# ------------------------------------------------------------------
ugas  = pd.read_csv(data_dir / "zonas.csv")
pars  = yaml.safe_load(open(data_dir / "params.yaml"))

# sets ----------------------------------------------------------------
G = ugas.query("type=='irr'").uga_id.astype(str).tolist()
L = ugas.query("type=='lav'").uga_id.astype(str).tolist()
P = ugas.query("uga_group=='P'").uga_id.astype(str).tolist()
N = ugas.query("uga_group=='N'").uga_id.astype(str).tolist()

D  = range(1, pars["D"]+1)
H  = range(pars["H"])
H_noc  = pars["H_noc"]
D_proh = pars["D_proh"]

# parameters ----------------------------------------------------------
# Filtrar solo zonas de riego y crear diccionario de áreas
irr_ugas = ugas[ugas['type'] == 'irr'].copy()
# Convertir uga_id a string para que coincida con G
irr_ugas['uga_id'] = irr_ugas['uga_id'].astype(str)
A = irr_ugas.set_index("uga_id")["A_m2"].astype(float).to_dict()
beta_z = {z: pars["beta_m_m3pkm"] * pars["L_turno_km"] for z in L}

# Cargar el diccionario ET para todas las zonas y días
month_ET = {
    1: 6.0, 2: 5.3, 3: 4.0, 4: 3.0,
    5: 2.0, 6: 1.6, 7: 1.4, 8: 1.6,
    9: 2.0, 10: 3.0, 11: 4.3, 12: 5.9,
}
ET_dict = build_ET_dict(G, month_ET)

M      = pars["M_m3ph"]   # might be None
alpha  = pars["alpha"]
betaW  = pars["beta"]
gamma  = pars["gamma"]
delta  = pars["delta"]

# ------------------------------------------------------------------
# 3. Create model
# ------------------------------------------------------------------
m = gp.Model("LC_water")

# -- VARIABLES -------------------------------------------------------
omega = m.addVars(G, D, name="omega", lb=0)
y     = m.addVars(G, D, H, vtype=GRB.BINARY, name="y")
vpot  = m.addVars(G, D, H, name="vpot",  lb=0)
vpozo = m.addVars(P, D, H, name="vpozo", lb=0)
I     = m.addVars(G, D, H, name="I",     lb=0)
u     = m.addVars(G, D, name="u",        lb=0)

ell   = m.addVars(L, D, name="ell",  lb=0)
wwash = m.addVars(L, D, vtype=GRB.BINARY, name="w")

# -- R1: no irrigation on D_proh ------------------------------------
for z in G:
    for d in D_proh:
        for h in H:
            m.addConstr(y[z,d,h]==0)
            m.addConstr(vpot[z,d,h]==0)
            if z in P:
                m.addConstr(vpozo[z,d,h]==0)

# -- R2: night-only irrigation --------------------------------------
for z in G:
    for d in D:
        for h in set(H)-set(H_noc):
            m.addConstr(y[z,d,h]==0)

# -- R3: source compatibility ---------------------------------------
for z in N:
    for d in D:
        for h in H:
            m.addConstr(vpozo.get((z,d,h),0)==0)
for z in P:
    for d in D:
        for h in H:
            m.addConstr(vpot[z,d,h]==0)

# -- R4: total flow + Big-M -----------------------------------------
M_val = M or 1e4  # fallback if user forgot to set
for z in G:
    for d in D:
        for h in H:
            m.addConstr(I[z,d,h]==vpot[z,d,h]+vpozo.get((z,d,h),0))
            m.addConstr(I[z,d,h]<=M_val*y[z,d,h])

# -- R5: moisture balance -------------------------------------------
for z in G:
    for d in D[:-1]:
        # Usar el diccionario ET_dict para obtener ET[z,d+1]
        et_value = ET_dict[z, d+1]  # ET para la zona z en el día d+1
        m.addConstr(
            omega[z,d+1] ==
            omega[z,d] +
            pars["eta"]*1000/A[z] * gp.quicksum(I[z,d,h] for h in H)
            - et_value  # ET real desde el diccionario
            + u[z,d]
        )

# -- R6: bounds ------------------------------------------------------
for z in G:
    for d in D:
        m.addConstr(omega[z,d] >= pars["omega^{min}_z"] - u[z,d])
        m.addConstr(omega[z,d] <= pars["omega^{max}_z"])

# -- R7: washing capacity -------------------------------------------
for d in D:
    m.addConstr(gp.quicksum(wwash[z,d] for z in L) <= 1)
    for z in L:
        m.addConstr(ell[z,d] <= min(beta_z[z], pars["C_cam_m3"]) * wwash[z,d])

# -- R8: 14-day coverage --------------------------------------------
for z in L:
    for d in range(14, pars["D"]+1):
        m.addConstr(gp.quicksum(ell[z,dd] for dd in range(d-13, d+1)) >= beta_z[z])

# -- OBJECTIVE -------------------------------------------------------
obj  = alpha*u.sum()  if alpha is not None else 0
obj += betaW*I.sum()  if betaW is not None else 0
obj += gamma*y.sum()  if gamma is not None else 0
obj += delta*ell.sum() if delta is not None else 0
m.setObjective(obj, GRB.MINIMIZE)

# ------------------------------------------------------------------
# 3.b  Ejecutar o cargar solución
# ------------------------------------------------------------------
if args.nosolve:
    # salta el solve; intenta cargar una solución previa
    sol_path = out_dir / "solution.sol"
    if not sol_path.exists():
        raise FileNotFoundError(f"No se encontró {sol_path}. Corre el script sin --nosolve primero.")
    m.read(str(sol_path))
    print("✓ solución previa cargada desde", sol_path)
else:
    m.Params.OutputFlag = 1
    m.optimize()
    # guarda artefactos para futuros análisis
    m.write(str(out_dir / "model.mps"))
    m.write(str(out_dir / "solution.sol"))
# ------------------------------------------------------------------
# 4. Save some outputs
# ------------------------------------------------------------------
out_csv = out_dir / "ell_solution.csv"
ell_df = pd.DataFrame(
    [(z,d,ell[z,d].X) for z in L for d in D],
    columns=["uga_id","day","ell_m3"])
ell_df.to_csv(out_csv, index=False)
print(f"lavado solution -> {out_csv}")

# ------------------------------------------------------------------
# 5. Guardar TODAS las variables con su valor óptimo
# ------------------------------------------------------------------
import pandas as pd

# m.getVars() devuelve una lista ordenada de todos los objetos Var.
rows = []
for v in m.getVars():
    # v.VarName podría ser algo como  "I[1001,24,5]"
    rows.append({"var": v.VarName, "value": v.X})

df_vars = pd.DataFrame(rows)

csv_all = out_dir / "vars_solucion_optima.csv"
df_vars.to_csv(csv_all, index=False)
print(f"✓ CSV completo con variables → {csv_all}")

# ==============================================================
#  POST-ANÁLISIS: volumen diario por tipo de agua (365 días)
#  --------------------------------------------------------------
#  • potable  : ΣzΣh vpot[z,d,h]
#  • pozo     : ΣzΣh vpozo[z,d,h]
#  • lavado   : Σℓ ell[ℓ,d]
#  ==============================================================
import pandas as pd, matplotlib.pyplot as plt

records = []
for d in D:                                  # D = range(1,366)
    pot  = sum(vpot[z,d,h].X  for z in G  for h in H)          # m³/d
    pozo = sum(vpozo[z,d,h].X for z in P  for h in H)          # m³/d
    wash = sum(ell[l,d].X     for l in L)                      # m³/d
    records.append({"day": d, "potable": pot,
                    "pozo": pozo, "lavado": wash})

df_vol = pd.DataFrame(records).set_index("day")

# -------- 1) guarda CSV ----------------------------------------
csv_vol = out_dir / "vol_diario_por_fuente.csv"
df_vol.to_csv(csv_vol)
print(f"✓ CSV diario por fuente → {csv_vol}")

# -------- 2) gráfico barrido apilado ---------------------------
plt.figure(figsize=(10,4))
df_vol.plot(kind="bar", stacked=True, width=1.0, ax=plt.gca(),
            color={"potable":"steelblue",
                   "pozo":"seagreen",
                   "lavado":"darkorange"})
plt.xlabel("Día del año (1–365)")
plt.ylabel("Volumen [m³]")
plt.title("Volumen diario por tipo de agua – Las Condes")
plt.legend(title="Fuente", ncol=3, loc="upper right", fontsize=8)
plt.tight_layout()

png = out_dir / "vol_diario_por_fuente.png"
plt.savefig(png, dpi=150)
print(f"✓ Gráfico guardado en {png}")
plt.show()