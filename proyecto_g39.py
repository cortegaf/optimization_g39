# ================================================================
#  Modelo municipal de riego + lavado (Gurobi 10.0.3)
# ================================================================
import gurobipy as gp
from gurobipy import GRB

# ---------------------------------------------------------------
# Cargamos todos los datos desde data_inputs.py
# ---------------------------------------------------------------
from data_inputs import (
    Z, D, Hn, B, W, S, Dproh, sigma_d, sigma_w, W_w,
    calle, parque, privado, vert, gris, tau,
    A_pot, A_gris, f, r_parque, Vmin,
    beta_i, c_pot, c_gris, lam, M
)

# ----------------------------------------------------------------
# 3) MODELO
# ----------------------------------------------------------------
m = gp.Model('Municipal_Riego_10_0')

# ------------------------- VARIABLES ----------------------------
x = m.addVars( [(i,d,h) for i in Z for d in D for h in Hn if calle[i]==0],
               vtype=GRB.BINARY, name='x')

qpot  = m.addVars(x.keys(),            lb=0.0, name='qpot')
qgris = m.addVars(x.keys(),            lb=0.0, name='qgris')

X = m.addVars( [(i,d,b) for i in Z for d in D for b in B if calle[i]==0],
               vtype=GRB.BINARY, name='X')

Qpot  = m.addVars(X.keys(),            lb=0.0, name='Qpot')
Qgris = m.addVars(X.keys(),            lb=0.0, name='Qgris')

y   = m.addVars( [(i,d)   for i in Z for d in D], vtype=GRB.BINARY, name='y')
vlav= m.addVars( [(i,d)   for i in Z if calle[i]==1 for d in D],
                  lb=0.0, name='vlav')

nweek= m.addVars( [(i,w)  for i in Z if calle[i]==0 for w in W],
                  vtype=GRB.INTEGER, lb=0, name='n')

sweek= m.addVars( [(i,w)  for i in Z if calle[i]==0 for w in W],
                  lb=0.0, name='s')

# --------------------- RESTRICCIONES ----------------------------
# (R1) Miércoles / domingos
m.addConstrs( X[i,d,b] == 0
              for i in Z if calle[i]==0
              for d in Dproh
              for b in B )

m.addConstrs( x[i,d,h] == 0
              for i in Z if calle[i]==0
              for d in Dproh
              for h in Hn )

# (R2) Privados 10-18 h (bloques 1-4)
m.addConstrs( X[i,d,b] == 0
              for i in Z if privado[i]==1
              for d in D
              for b in [1,2,3,4] )

# (R3) Sin vertiente, prohibido todo bloque
m.addConstrs( X[i,d,b] == 0
              for i in Z if vert[i]==0 and calle[i]==0
              for d in D
              for b in B )

# (R4) Balance potable
for s in S:
    lhs = gp.quicksum(qpot[i,d,h]
                      for i in Z if calle[i]==0
                      for d in D if sigma_d[d]==s
                      for h in Hn) \
        + gp.quicksum(Qpot[i,d,b]
                      for i in Z if calle[i]==0
                      for d in D if sigma_d[d]==s
                      for b in B) \
        + gp.quicksum(vlav[i,d]
                      for i in Z if calle[i]==1
                      for d in D if sigma_d[d]==s)
    m.addConstr(lhs <= A_pot[s], name=f'R4_{s}')

# (R5a) Balance grises
for s in S:
    lhs = gp.quicksum(qgris[i,d,h]
                      for i in Z if calle[i]==0
                      for d in D if sigma_d[d]==s
                      for h in Hn) \
        + gp.quicksum(Qgris[i,d,b]
                      for i in Z if calle[i]==0
                      for d in D if sigma_d[d]==s
                      for b in B)
    m.addConstr(lhs <= A_gris[s], name=f'R5a_{s}')

# (R5b) Infraestructura grises
m.addConstrs( qgris[i,d,h] == 0
              for i in Z if gris[i]==0 and calle[i]==0
              for d in D
              for h in Hn )
m.addConstrs( Qgris[i,d,b] == 0
              for i in Z if gris[i]==0 and calle[i]==0
              for d in D
              for b in B )

# (R6a-b) Big-M caudales
m.addConstrs( qpot[i,d,h] + qgris[i,d,h] <= M  * x[i,d,h]
              for (i,d,h) in x )
m.addConstrs( Qpot[i,d,b] + Qgris[i,d,b] <= 2*M* X[i,d,b]
              for (i,d,b) in X )

# (R6c) Enlace riego-actividad
m.addConstrs( y[i,d] >= x[i,d,h]
              for (i,d,h) in x )
m.addConstrs( y[i,d] >= X[i,d,b]
              for (i,d,b) in X )

# (R6d) Volumen lavado
m.addConstrs( vlav[i,d] == beta_i[i]*y[i,d]
              for i in Z if calle[i]==1
              for d in D )

# (R7) Definición n_{i,w}
m.addConstrs( nweek[i,w] ==
              gp.quicksum( y[i,d] for d in W_w[w] )
              for i in Z if calle[i]==0
              for w in W )

# (R8a) Frecuencia mínima general
m.addConstrs( nweek[i,w] >= f[tau[i], sigma_w[w]]
              for i in Z if calle[i]==0
              for w in W )

# (R8b) Frecuencia mínima parques
m.addConstrs( nweek[i,w] >= r_parque[tau[i], sigma_w[w]]
              for i in Z if parque[i]==1
              for w in W )

# (R8c) Volumen mínimo semanal
for i in Z:
    if calle[i]==0:
        for w in W:
            lhs = gp.quicksum(qpot[i,d,h]+qgris[i,d,h]
                              for d in W_w[w]
                              for h in Hn) \
                + gp.quicksum(Qpot[i,d,b]+Qgris[i,d,b]
                              for d in W_w[w]
                              for b in B)
            m.addConstr(lhs + sweek[i,w] >= Vmin[tau[i], sigma_w[w]],
                        name=f'R8c_{i}_{w}')

# (R9) Lavado cada 14 días
m.addConstrs(
    gp.quicksum(y[i,d_] for d_ in range(d-13, d+1)) >= 1
    for i in Z if calle[i]==1
    for d in range(14, 366)
)

# --------------------- FUNCIÓN OBJETIVO -------------------------
cost_riego = c_pot * gp.quicksum(qpot.values()) + \
             c_gris * gp.quicksum(qgris.values()) + \
             c_pot * gp.quicksum(Qpot.values()) + \
             c_gris * gp.quicksum(Qgris.values())

# Opción 1 — factor común
cost_lav = c_pot * gp.quicksum(vlav.values())
penal_def = lam * gp.quicksum(sweek.values())

m.setObjective( cost_riego + cost_lav + penal_def, GRB.MINIMIZE)

# ----------------------------------------------------------------
# 4) OPTIMIZACIÓN
# ----------------------------------------------------------------
m.Params.OutputFlag = 1             # 0 para silencio
m.optimize()

# ----------------------------------------------------------------
# 5) RESULTADOS BÁSICOS (ejemplo)
# ----------------------------------------------------------------
if m.Status == GRB.OPTIMAL:
    print(f"Costo óptimo = {m.ObjVal:,.2f} $/año")