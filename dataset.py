# ---------------------------------------------------------------------------
# data_inputs_template.py
# ---------------------------------------------------------------------------
"""
Plantilla de **datos de entrada** para el modelo de riego/lavado
municipal en Las Condes.

1.  Mantiene EXACTAMENTE los nombres de conjuntos, parámetros y
    estructuras que espera `proyecto_g39.py`.
2.  TODAS las tablas se rellenan a partir de listas-base que el
    usuario puede sustituir por cifras reales (catastros SIG,
    inventario de parques, tarifas oficiales, etc.).
3.  La plantilla genera un ejemplo reproducible con la función
    `build_example()`.  
    - Si se comenta esa llamada y se cargan datos externos en
    su lugar, el script actúa simplemente como contenedor.

Cada bloque va acompañado de un **comentario** que explica dónde
buscar la información real (catastro de áreas verdes Las Condes,
tarifas Aguas Andinas 2025-2030, series ET₀ de la DGA, etc.) y
el formato esperado.
"""

# ---------------------------------------------------------------------------
# 0) LIBRERÍAS
# ---------------------------------------------------------------------------
import calendar, random
from collections import defaultdict
from typing import List, Dict, Tuple

# ----------------------------------------------------------------------------
# 1) CONJUNTOS CALENDARIO
#    ────────────────
#    * D   : días 1-365
#    * Hn  : horas nocturnas [22,23]∪[0-9]
#    * B   : bloques diurnos 2 h   b=1..6
#    * W   : semanas ISO 1..52
#    * S   : meses 1..12
#    * σd  : día→mes
#    * σw  : semana→mes
#    * Ww  : semana→lista de días
#    * Dproh : miércoles y domingos (restricción municipal)
# ----------------------------------------------------------------------------
D         : List[int]              = list(range(1, 366))
Hn        : List[int]              = list(range(22, 24)) + list(range(0, 10))
B         : List[int]              = [1, 2, 3, 4, 5, 6]
W         : List[int]              = list(range(1, 53))
S         : List[int]              = list(range(1, 13))
sigma_d   : Dict[int, int]         = {}        # d → mes
sigma_w   : Dict[int, int]         = {}        # w → mes
W_w       : Dict[int, List[int]]   = defaultdict(list)
Dproh     : List[int]              = []        # miércoles / domingos

def _build_calendar(year: int = 2025) -> None:
    """Llena σd, σw, Ww y Dproh de forma consistente."""
    cal = calendar.Calendar()
    d_counter = 0
    for m in S:
        for week in cal.monthdatescalendar(year, m):
            iso_w = week[0].isocalendar()[1]
            if iso_w not in W:
                continue
            for date in week:
                if date.year == year and date.month == m:
                    d_counter += 1
                    d = d_counter
                    sigma_d[d] = m
                    W_w[iso_w].append(d)
                    if date.weekday() in (2, 6):   # mié, dom
                        Dproh.append(d)
            if iso_w not in sigma_w:
                sigma_w[iso_w] = m
    assert d_counter == 365, "Año incompleto"

_build_calendar()

# ----------------------------------------------------------------------------
# 2) CONJUNTOS DE UGA y ATRIBUTOS
# ----------------------------------------------------------------------------
Z                      : List[int]            = []   # se crea en build_example
calle, parque, privado : Dict[int, int]       = {}
vert, gris             : Dict[int, int]       = {}
tau                    : Dict[int, int]       = {}   # 1=césped,2=arbusto,3=mixto
area                   : Dict[int, float]     = {}   # m² de cada UGA
beta_i                 : Dict[int, float]     = {}   # m³/evento de lavado

# ----------------------------------------------------------------------------
# 3) PARÁMETROS HIDROLÓGICOS Y ECONÓMICOS
# ----------------------------------------------------------------------------
A_pot  : Dict[int, float]          = {}   # m³/mes agua potable
A_gris : Dict[int, float]          = {}   # m³/mes aguas grises
f                    : Dict[Tuple[int,int], int]    = defaultdict(int)
r_parque             : Dict[Tuple[int,int], int]    = defaultdict(int)
Vmin                 : Dict[Tuple[int,int], float]  = defaultdict(float)
c_pot : float = 0.0
c_gris: float = 0.0
lam    : float = 0.0
M      : float = 0.0

# ----------------------------------------------------------------------------
# 4) CONSTRUCTOR DE EJEMPLO (para test rápido)
#    Sustituya esta función por un cargador de su base real
# ----------------------------------------------------------------------------
def build_example(seed: int = 123, n_uga: int = 30) -> None:
    """
    Genera un conjunto sintético de *n_uga* unidades de gestión de agua
    usando rangos razonables para Las Condes.
    """
    global Z, calle, parque, privado, vert, gris, tau, area, beta_i
    global A_pot, A_gris, f, r_parque, Vmin, c_pot, c_gris, lam, M

    random.seed(seed)
    Z = list(range(n_uga))

    # Distribución aproximada (60 % parques, 25 % privados, 15 % calles)
    tipo = random.choices(
        ["parque", "privado", "calle"],
        weights=[0.6, 0.25, 0.15], k=n_uga)

    calle   = {i: 1 if tipo[i]=="calle"   else 0 for i in Z}
    parque  = {i: 1 if tipo[i]=="parque"  else 0 for i in Z}
    privado = {i: 1 if tipo[i]=="privado" else 0 for i in Z}

    # Vertiente: existe en 70 % de parques/calles y 15 % de privados
    vert = {i: 1 if ((not privado[i] and random.random()<0.7)
                     or (privado[i] and random.random()<0.15)) else 0
            for i in Z}

    # Red gris: 60 % parques, 10 % privados
    gris = {i: 1 if ((parque[i] and random.random()<0.6)
                     or (privado[i] and random.random()<0.1)) else 0
            for i in Z}

    # Vegetación
    tau  = {i: random.choice([1, 2, 3]) if not calle[i] else 0 for i in Z}

    # Superficie (m²) rango típico Las Condes
    area = {i: (random.randint(1_000, 12_000) if parque[i] else     # parques
                random.randint(120, 800)      if privado[i] else    # predios
                random.randint(250, 1_200)) for i in Z}             # bermas

    # Lavado (m³) – camión aljibe 5 000 L para calles
    beta_i = {i: 5.0 if calle[i] else 0.0 for i in Z}

    # ——— DOTACIONES ——————————————————————————————
    #  meta anual potable ≈ 7 000 m³/ha   (Las Condes 2024 – ORD DIPLA)
    total_area = sum(area.values()) / 10_000          # ha
    annual_pot = total_area * 7000                    # m³/año
    # 40 % potencial reaprovechable como gris
    annual_grey = annual_pot * 0.4

    for s in S:
        # Factor estacional sencillo (dic-feb 1.25 / jun-jul 0.8)
        est = 1.25 if s in (12,1,2) else 0.8 if s in (6,7) else 1.0
        A_pot[s]  = round(annual_pot  * est / 12 , 1)
        A_gris[s] = round(annual_grey * est / 12 , 1)

    # ——— REQUISITOS SEMANALES ————————————————————
    for t in [1,2,3]:
        for s in S:
            base_f = 2 if s in (12,1,2) else 1
            f[(t,s)] = base_f
            r_parque[(t,s)] = base_f + 1       # parque exige +1
            # volumen: 4 mm x área UGA típica 400 m² → 1.6 m³, repartido
            Vmin[(t,s)] = 1.6 / 52

    # ——— COSTOS (pesos 2025 CLP) ——————————————
    # tarifa Aguas Andinas tramo G1 (≈ \$970 CLP/m³ → 1 USD≃900 CLP)
    c_pot  = round(970/900 , 3)      # ≈ 1.08 USD/m³
    # estimación costo interno de gris 250 CLP/m³
    c_gris = round(250/900 , 3)      # ≈ 0.28 USD/m³
    lam    = 10 * c_pot             # penaliza fuerte

    # ——— BIG-M ———————————————————————————————
    # 3–9 m³ h⁻¹ según superficie mayor
    M = round(min(9, max(3, 0.002 * max(area.values()))), 1)

# Construye inmediatamente un set de prueba de 30 UGA
# (comentar la siguiente línea para usar datos externos)
build_example()

# ---------------------------------------------------------------------------
# 5) DEBUG RÁPIDO (opcional)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"UGAs: {len(Z)} | parques={sum(parque.values())} "
          f"calles={sum(calle.values())} privados={sum(privado.values())}")
    print(f"M = {M} m³/h   |   c_pot = {c_pot} USD/m³   |   λ = {lam}")