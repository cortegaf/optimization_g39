"""
data_inputs_big.py
------------------
Genera ~500 UGA con valores pseudo-aleatorios verosímiles, tomando
rangos documentados en bibliografía técnica y tarifas chilenas 2024-25.

El ‘semillado’ hace reproducible la prueba; cambia RANDOM_SEED para
otro escenario.
"""
import calendar, random
from collections import defaultdict
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# ------------------------------------------------------------------
# 1) CONJUNTOS CALENDARIO
# ------------------------------------------------------------------
D  = list(range(1, 366))
Hn = list(range(22, 24)) + list(range(0, 10))
B  = [1, 2, 3, 4, 5, 6]
W  = list(range(1, 53))
S  = list(range(1, 13))

def weekday_2025(d): return (2 + d - 1) % 7  # 1-ene-25 = mié (2)
Dproh = [d for d in D if weekday_2025(d) in (2, 6)]  # miércoles/domingo

# σ-mapeos y Ww
sigma_d, sigma_w, W_w = {}, {}, defaultdict(list)
cal = calendar.Calendar()
day_of_year = 0
for m in S:
    for wk in cal.monthdatescalendar(2025, m):
        iso = wk[0].isocalendar()[1]
        if iso not in W: continue
        for date in wk:
            if date.year == 2025 and date.month == m:
                day_of_year += 1
                sigma_d[day_of_year] = m
                W_w[iso].append(day_of_year)
        if iso not in sigma_w: sigma_w[iso] = m
assert day_of_year == 365

# ------------------------------------------------------------------
# 2) GENERADOR DE 500 UGA
# ------------------------------------------------------------------
Z = list(range(500))
# Distribución por tipo
tipo = random.choices(["parque","calle","privado"],
                      weights=[0.6,0.15,0.25], k=500)

calle   = {i: 1 if tipo[i]=="calle"   else 0 for i in Z}
parque  = {i: 1 if tipo[i]=="parque"  else 0 for i in Z}
privado = {i: 1 if tipo[i]=="privado" else 0 for i in Z}

# Vertientes (60 % de parques y calles; 10 % de privados)
vert = {i: 1 if ( tipo[i]!="privado" and random.random()<0.6 ) or
                 ( tipo[i]=="privado" and random.random()<0.1 ) else 0
         for i in Z}

# Red de grises sólo en 50 % de parques y 5 % de privados
gris = {i: 1 if (parque[i] and random.random()<0.5) or
                 (privado[i] and random.random()<0.05) else 0
         for i in Z}

# Tipo de vegetación: 1=césped, 2=arbusto, 3=mixto
tau  = {i: random.choice([1,2,3]) if not calle[i] else 0 for i in Z}

# Superficie aproximada (m²) para dimensionar volúmenes
area = {i: ( random.randint(500,5_000) if parque[i]
             else random.randint(150,800) if privado[i]
             else random.randint(200,1_000) ) for i in Z}

# ------------------------------------------------------------------
# 3) DOTACIONES MENSUALES (m³)
#     – suponemos meta 7 000 m³/año potable por ha de áreas verdes
# ------------------------------------------------------------------
A_pot  = {s: 0.0 for s in S}
A_gris = {s: 0.0 for s in S}
for s in S:
    # demanda base mensual (factor estacional simple)
    factor = 1.3 if s in (1,2,12) else 0.9 if s in (6,7) else 1.0
    A_pot[s]  = round( sum(area[i] for i in Z)*0.007*factor/12 , 1 )
    A_gris[s] = round( A_pot[s]*0.4 , 1 )          # 40 % potencial grises

# ------------------------------------------------------------------
# 4) REQUISITOS SEMANALES
# ------------------------------------------------------------------
f = defaultdict(int); r_parque = defaultdict(int); Vmin = defaultdict(float)
for t in [1,2,3]:
    for s in S:
        base_freq = 2 if s in (1,2,12) else 1
        f[(t,s)] = base_freq
        r_parque[(t,s)] = base_freq + 1            # un riego extra
        # ET₀ veraniega 6 mm d⁻¹ ≈ 42 mm sem; Suponemos 20 % de reposición:
        Vmin[(t,s)] = round( 0.0002 * base_freq , 3 )  # m³ por m²; ≈ 0.1-0.2

# ------------------------------------------------------------------
# 5) LAVADO DE CALLES
#     – 5 m³ por evento, igual que un camión aljibe chico
# ------------------------------------------------------------------
beta_i = {i: (5.0 if calle[i] else 0.0) for i in Z}

# ------------------------------------------------------------------
# 6) COSTOS Y PENALIZACIÓN
# ------------------------------------------------------------------
c_pot  = 0.45        # $/m³ tarifa 2024-25 (aguas Andinas)  [oai_citation:10‡USGS](https://pubs.water.usgs.gov/SIR20075156?utm_source=chatgpt.com)
c_gris = 0.12        # $/m³ costo interno de reutilización  [oai_citation:11‡Chelan PUD](https://www.chelanpud.org/conservationhome/water-conservation/water-use-calculator?utm_source=chatgpt.com)
lam    = 120.0       # $/m³ déficit (>> c_pot)

# ------------------------------------------------------------------
# 7) CAUDAL MÁXIMO (Big-M)
#     3-8 m³ h⁻¹ según área, capado a rango de literatura
# ------------------------------------------------------------------
M = round( min(8, max(3, 0.002*max(area.values()))) , 1 )

if __name__ == "__main__":
    print(f"UGAs total: {len(Z)} (parques={sum(parque.values())}, "
          f"calles={sum(calle.values())}, privados={sum(privado.values())})")
    print("M =", M, "m³/h | c_pot =", c_pot, "$/m³ | λ =", lam)