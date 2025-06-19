#!/usr/bin/env python3.10
# -------------------------------------------------------------
#  Optimizacion de uso de agua en Las Condes - Modelo MILP
# -------------------------------------------------------------
import gurobipy as gp
from gurobipy import GRB
import pandas as pd
import matplotlib.pyplot as plt
from params_and_sets import G, L, P, N, D, H, H_noc, D_proh, A, beta_z, pars, ET_dict
import numpy as np
import seaborn as sns

# -------------------------------------------------------------
# 1. Construccion del modelo de optimizacion
# -------------------------------------------------------------
m = gp.Model("Modelo_Hidrico_Las_Condes")

# -------------------- VARIABLES ------------------------------
omega = m.addVars(G, D, name="omega", lb=0)
y     = m.addVars(G, D, H, vtype=GRB.BINARY, name="y")
vpot  = m.addVars(G, D, H, name="vpot",  lb=0)
vpozo = m.addVars(P, D, H, name="vpozo", lb=0)
I     = m.addVars(G, D, H, name="I",     lb=0)
u     = m.addVars(G, D, name="u",        lb=0)

ell   = m.addVars(L, D, name="ell",  lb=0)
wwash = m.addVars(L, D, vtype=GRB.BINARY, name="w")

# ------------- RESTRICCIONES DEL MODELO ---------------------
# R1: No regar en dias prohibidos
for z in G:
    for d in D_proh:
        for h in H:
            m.addConstr(y[z,d,h]==0)
            m.addConstr(vpot[z,d,h]==0)
            if z in P:
                m.addConstr(vpozo[z,d,h]==0)

# R2: Riego solo en horario nocturno permitido
for z in G:
    for d in D:
        for h in set(H)-set(H_noc):
            m.addConstr(y[z,d,h]==0)

# R3: Compatibilidad de fuentes de agua
for z in N:
    for d in D:
        for h in H:
            m.addConstr(vpozo.get((z,d,h),0)==0)
for z in P:
    for d in D:
        for h in H:
            m.addConstr(vpot[z,d,h]==0)

# R4: Caudal total y restriccion Big-M
M_val = pars['M_m3ph'] or 1e4
for z in G:
    for d in D:
        for h in H:
            m.addConstr(I[z,d,h]==vpot[z,d,h]+vpozo.get((z,d,h),0))
            m.addConstr(I[z,d,h]<=M_val*y[z,d,h])

# R5: Balance de humedad en el suelo
for z in G:
    for d in list(D)[:-1]:
        et_value = ET_dict[z, d+1] #este valor de ET es el real y ya incluye el kc multiplicado por el et_o.
        m.addConstr(
            omega[z,d+1] ==
            omega[z,d] +
            pars['eta']*1000/A[z] * gp.quicksum(I[z,d,h] for h in H)
            - et_value
            + u[z,d]
        )

# R6: Limites de humedad
for z in G:
    for d in D:
        m.addConstr(omega[z,d] >= pars['omega^{min}_z'] - u[z,d])
        m.addConstr(omega[z,d] <= pars['omega^{max}_z'])

# R7: Capacidad de lavado
for d in D:
    m.addConstr(gp.quicksum(wwash[z,d] for z in L) <= 1)
    for z in L:
        m.addConstr(ell[z,d] <= min(beta_z[z], pars['C_cam_m3']) * wwash[z,d])

# R8: Cobertura de lavado en 14 dias
for z in L:
    for d in range(14, pars['D']+1):
        m.addConstr(gp.quicksum(ell[z,dd] for dd in range(d-13, d+1)) >= beta_z[z])

# ------------------- FUNCIoN OBJETIVO ------------------------
obj  = pars['alpha']*u.sum()  if pars['alpha'] is not None else 0
obj += pars['beta']*I.sum()   if pars['beta'] is not None else 0
obj += pars['gamma']*y.sum()  if pars['gamma'] is not None else 0
obj += pars['delta']*ell.sum() if pars['delta'] is not None else 0
m.setObjective(obj, GRB.MINIMIZE)

# -------------------------------------------------------------
# 3. Resolucion del modelo
# -------------------------------------------------------------
m.Params.OutputFlag = 1
m.Params.MIPGap = 0.003  # Se detiene cuando el gap es menor o igual a 0.3%
m.optimize()

# -------------------------------------------------------------
# 4. Guardar resultados principales en archivos CSV
# -------------------------------------------------------------

# 4.1 Solucion de lavado
ell_df = pd.DataFrame(
    [(z, d, ell[z, d].X) for z in L for d in D],
    columns=["uga_id", "day", "ell_m3"]
)
ell_df.to_csv("ell_solution.csv", index=False)
print("Solucion de lavado guardada en ell_solution.csv")

# 4.2 Todas las variables optimas
df_vars = pd.DataFrame([
    {"var": v.VarName, "value": v.X} for v in m.getVars()
])
df_vars.to_csv("vars_solucion_optima.csv", index=False)
print("CSV completo de variables guardado en vars_solucion_optima.csv")

# 4.3 Volumen diario por fuente
records = []
for d in D:
    pot  = sum(vpot[z, d, h].X  for z in G for h in H)
    pozo = sum(vpozo[z, d, h].X for z in P for h in H)
    wash = sum(ell[l, d].X      for l in L)
    records.append({"day": d, "potable": pot, "pozo": pozo, "lavado": wash})

df_vol = pd.DataFrame(records).set_index("day")
df_vol.to_csv("vol_diario_por_fuente.csv")
print("CSV diario por fuente guardado en vol_diario_por_fuente.csv")

# -------------------------------------------------------------
# 5. Análisis por zona
# -------------------------------------------------------------

# 5.1 Agua total aplicada por zona de riego (top 10)
agua_por_zona = pd.DataFrame([
    {'uga_id': z, 'agua_total': sum(I[z, d, h].X for d in D for h in H)}
    for z in G
])
agua_por_zona = agua_por_zona.sort_values('agua_total', ascending=False)
plt.figure(figsize=(10, 4))
plt.bar(agua_por_zona['uga_id'][:10], agua_por_zona['agua_total'][:10])
plt.xlabel('Zona de riego (uga_id)')
plt.ylabel('Agua total aplicada [m³]')
plt.title('Top 10 zonas de riego con mayor consumo anual de agua')
plt.tight_layout()
plt.savefig('top10_agua_total_por_zona.png', dpi=150)
plt.show()

# 5.2 Días con déficit de humedad por zona (top 10)
deficit_por_zona = pd.DataFrame([
    {'uga_id': z, 'dias_deficit': sum(omega[z, d].X <= pars['omega^{min}_z'] + 1e-3 for d in D)}
    for z in G
])
deficit_por_zona = deficit_por_zona.sort_values('dias_deficit', ascending=False)
plt.figure(figsize=(10, 4))
plt.bar(deficit_por_zona['uga_id'][:10], deficit_por_zona['dias_deficit'][:10])
plt.xlabel('Zona de riego (uga_id)')
plt.ylabel('Días con déficit de humedad')
plt.title('Top 10 zonas con más días de déficit de humedad')
plt.tight_layout()
plt.savefig('top10_deficit_por_zona.png', dpi=150)
plt.show()

# 5.3 Lavados por zona de lavado (top 10)
lavados_por_zona = pd.DataFrame([
    {'uga_id': l, 'lavados': sum(wwash[l, d].X for d in D)}
    for l in L
])
lavados_por_zona = lavados_por_zona.sort_values('lavados', ascending=False)
plt.figure(figsize=(8, 4))
plt.bar(lavados_por_zona['uga_id'][:10], lavados_por_zona['lavados'][:10])
plt.xlabel('Zona de lavado (uga_id)')
plt.ylabel('Cantidad de lavados en el año')
plt.title('Top 10 zonas de lavado con más lavados')
plt.tight_layout()
plt.savefig('top10_lavados_por_zona.png', dpi=150)
plt.show()

# 5.4 Humedad final por zona
humedad_final = pd.DataFrame([
    {'uga_id': z, 'humedad_final': omega[z, D[-1]].X}
    for z in G
])
plt.figure(figsize=(10, 4))
plt.bar(humedad_final['uga_id'][:10], humedad_final['humedad_final'][:10])
plt.xlabel('Zona de riego (uga_id)')
plt.ylabel('Humedad final [mm]')
plt.title('Humedad final en las 10 primeras zonas al terminar el año')
plt.tight_layout()
plt.savefig('top10_humedad_final_por_zona.png', dpi=150)
plt.show()

# -------------------------------------------------------------
# 6. Análisis por grupo
# -------------------------------------------------------------

# Ejemplo: crear el diccionario grupo_por_zona desde params_and_sets.py si no existe
# (puedes generarlo desde zonas.csv y pegarlo en params_and_sets.py)
grupo_por_zona = {}
for z in G:
    if z in N:
        grupo_por_zona[z] = 'N'
    elif z in P:
        grupo_por_zona[z] = 'P'
    else:
        grupo_por_zona[z] = 'Otro'

# 1. Agua total aplicada por grupo de zonas de riego
agua_por_grupo = {}
for z in G:
    grupo = grupo_por_zona[z]
    agua = sum(I[z, d, h].X for d in D for h in H)
    agua_por_grupo[grupo] = agua_por_grupo.get(grupo, 0) + agua

plt.figure(figsize=(6,4))
plt.bar(agua_por_grupo.keys(), agua_por_grupo.values())
plt.xlabel('Grupo de zonas de riego')
plt.ylabel('Agua total aplicada [m³]')
plt.title('Consumo anual de agua por grupo de zonas')
plt.tight_layout()
plt.savefig('agua_total_por_grupo.png', dpi=150)
plt.show()

# 2. Días con déficit de humedad por grupo

deficit_por_grupo = {}
for z in G:
    grupo = grupo_por_zona[z]
    dias_deficit = sum(omega[z, d].X <= pars['omega^{min}_z'] + 1e-3 for d in D)
    deficit_por_grupo[grupo] = deficit_por_grupo.get(grupo, 0) + dias_deficit

plt.figure(figsize=(6,4))
plt.bar(deficit_por_grupo.keys(), deficit_por_grupo.values())
plt.xlabel('Grupo de zonas de riego')
plt.ylabel('Total días con déficit de humedad')
plt.title('Días con déficit de humedad por grupo de zonas')
plt.tight_layout()
plt.savefig('deficit_por_grupo.png', dpi=150)
plt.show()

# 3. Lavados por grupo de zonas de lavado
# (Si tienes grupos para L, puedes adaptar esto. Aquí se agrupa todo como "Lavado")
lavados_total = sum(sum(wwash[l, d].X for d in D) for l in L)
plt.figure(figsize=(4,4))
plt.bar(['Lavado'], [lavados_total])
plt.xlabel('Grupo de zonas de lavado')
plt.ylabel('Cantidad de lavados en el año')
plt.title('Cantidad total de lavados')
plt.tight_layout()
plt.savefig('lavados_total.png', dpi=150)
plt.show()

# 4. Promedio diario de agua aplicada (todas las zonas)
agua_diaria = [sum(I[z, d, h].X for z in G for h in H) for d in D]
plt.figure(figsize=(8,4))
plt.plot(range(1, len(D)+1), agua_diaria)
plt.xlabel('Día del año')
plt.ylabel('Agua total aplicada [m³]')
plt.title('Agua total aplicada por día (todas las zonas)')
plt.tight_layout()
plt.savefig('agua_promedio_diaria.png', dpi=150)
plt.show()

# 5. Boxplot de agua aplicada por grupo
# Prepara los datos para el boxplot
data = []
for z in G:
    grupo = grupo_por_zona[z]
    agua = sum(I[z, d, h].X for d in D for h in H)
    data.append({'grupo': grupo, 'agua': agua})
df_box = pd.DataFrame(data)
plt.figure(figsize=(6,4))
sns.boxplot(x='grupo', y='agua', data=df_box)
plt.xlabel('Grupo de zonas de riego')
plt.ylabel('Agua total aplicada [m³]')
plt.title('Distribución de agua aplicada por grupo')
plt.tight_layout()
plt.savefig('boxplot_agua_por_grupo.png', dpi=150)
plt.show()

# -------------------------------------------------------------
# 7. Análisis temporal
# -------------------------------------------------------------

# 7.2 Gráfico de volúmenes diarios por fuente
plt.figure(figsize=(10, 4))
df_vol.plot(kind="bar", stacked=True, width=1.0, ax=plt.gca(),
            color={"potable": "steelblue", "pozo": "seagreen", "lavado": "darkorange"})
plt.xlabel("Día del año (1–365)")
plt.ylabel("Volumen [m³]")
plt.title("Volumen diario por tipo de agua – Las Condes")
plt.legend(title="Fuente", ncol=3, loc="upper right", fontsize=8)
plt.tight_layout()
plt.savefig("vol_diario_por_fuente.png", dpi=150)
plt.show()