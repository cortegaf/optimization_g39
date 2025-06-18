#!/usr/bin/env python3
# ----------------------------------------------
#  Las Condes water MILP – stand-alone script
#  run with:  python solve_model.py --out results/
# ----------------------------------------------
import argparse, yaml, pandas as pd, gurobipy as gp
from gurobipy import GRB
from pathlib import Path

# ------------------------------------------------------------------
# 1. CLI and file paths
# ------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--data", default="data", help="folder with .csv/.yaml")
parser.add_argument("--out",  default="results", help="output folder")
args = parser.parse_args()
data_dir = Path(args.data)
out_dir  = Path(args.out);  out_dir.mkdir(exist_ok=True)

# ------------------------------------------------------------------
# 2. Load dataset
# ------------------------------------------------------------------
ugas  = pd.read_csv(data_dir / "zonas.csv")
pars  = yaml.safe_load(open(data_dir / "params.yaml"))

# sets ----------------------------------------------------------------
G = ugas.query("type=='irr'").uga_id.tolist()
L = ugas.query("type=='lav'").uga_id.tolist()
P = ugas.query("uga_group=='P'").uga_id.tolist()
N = ugas.query("uga_group=='N'").uga_id.tolist()

D  = range(1, pars["D"]+1)
H  = range(pars["H"])
H_noc  = pars["H_noc"]
D_proh = pars["D_proh"]

# parameters ----------------------------------------------------------
A   = ugas.set_index("uga_id")["A_m2"].to_dict()
beta_z = {z: pars["beta_m_m3pkm"] * pars["L_turno_km"] for z in L}

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
        m.addConstr(
            omega[z,d+1] ==
            omega[z,d] +
            pars["eta"]*1000/A[z] * gp.quicksum(I[z,d,h] for h in H)
            - pars["ET_{z,d}"] if False else 0  # TODO: replace by real ET
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
        m.addConstr(ell[z,d] <= min(beta_z[z], pars["C_cam"]) * wwash[z,d])

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
m.Params.OutputFlag = 1
m.optimize()

# ------------------------------------------------------------------
# 4. Save some outputs
# ------------------------------------------------------------------
out_csv = out_dir / "ell_solution.csv"
ell_df = pd.DataFrame(
    [(z,d,ell[z,d].X) for z in L for d in D],
    columns=["uga_id","day","ell_m3"])
ell_df.to_csv(out_csv, index=False)
print(f"lavado solution -> {out_csv}")