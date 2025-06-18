
# ---------------------------------------------------------------------------
# 0) LIBRERÍAS
# ---------------------------------------------------------------------------
import calendar
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
    """Llena sigma_d, sigmaw, Ww y Dproh de forma consistente."""
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
#    ─────────────────────────
#    * Z: lista de UGAs (IDs)
#    * calle, parque, privado: atributos binarios
#    * vert, gris: atributos binarios
#    * tau: tipo de vegetación (1=césped, 2=arbusto, 3=mixto)
#    * area: superficie en m²
#    * beta_i: volumen de lavado en m³/evento
# ----------------------------------------------------------------------------
Z: List[int] = []   # Lista de UGAs
calle: Dict[int, int] = {}   # Atributos binarios
parque: Dict[int, int] = {}   # Atributos binarios
privado: Dict[int, int] = {}   # Atributos binarios
vert: Dict[int, int] = {}   # Atributos binarios
gris: Dict[int, int] = {}   # Atributos binarios
tau: Dict[int, int] = {}   # Tipo de vegetación
area: Dict[int, float] = {}   # Superficie (m²)
beta_i: Dict[int, float] = {}   # Volumen lavado (m³)

# ----------------------------------------------------------------------------
# 3) PARÁMETROS HIDROLÓGICOS Y ECONÓMICOS
#    ──────────────────────────────────
#    * A_pot, A_gris: dotaciones mensuales (m³)
#    * f: frecuencia mínima de riego (riegos/semana)
#    * r_parque: frecuencia reforzada en parques
#    * Vmin: volumen mínimo semanal (m³)
#    * c_pot, c_gris: costos unitarios (USD/m³)
#    * lam: penalización por déficit (USD/m³)
#    * M: límite hidráulico (m³/h)
# ----------------------------------------------------------------------------
A_pot  : Dict[int, float]          = {}   # Dotación potable mensual (m³)
A_gris : Dict[int, float]          = {}   # Dotación gris mensual (m³)
f                    : Dict[Tuple[int,int], int]    = defaultdict(int)    # Frecuencia mínima
r_parque             : Dict[Tuple[int,int], int]    = defaultdict(int)    # Frecuencia parques
Vmin                 : Dict[Tuple[int,int], float]  = defaultdict(float)  # Volumen mínimo
c_pot  : float = 0.0    # Costo agua potable (USD/m³)
c_gris : float = 0.0    # Costo agua gris (USD/m³)
lam    : float = 0.0    # Penalización déficit (USD/m³)
M      : float = 0.0    # Límite hidráulico (m³/h)

# ---------------------------------------------------------------------------
# 4) VERIFICACIÓN RÁPIDA (opcional)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"UGAs: {len(Z)}")
    print(f"M = {M} m³/h   |   c_pot = {c_pot} USD/m³   |   λ = {lam}")