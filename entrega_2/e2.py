# dataset_builder.py
# -----------------
# Genera todos los conjuntos y diccionarios necesarios para el modelo Gurobi
# a partir de OpenStreetMap para Las Condes, Santiago, y del calendario 2025.

import osmnx as ox
import geopandas as gpd
import pandas as pd
import calendar
from collections import defaultdict

def build_calendar(year=2025):
    # 1) Calendario base
    D = list(range(1, 366))                     # días 1…365
    Hn = list(range(22, 24)) + list(range(0, 10))# horas nocturnas
    B  = [1,2,3,4,5,6]                          # bloques diurnos
    W  = list(range(1, 53))                     # semanas ISO
    S  = list(range(1, 13))                     # meses 1…12

    sigma_d = {}           # día → mes
    sigma_w = {}           # semana → mes (primer día)
    W_w     = defaultdict(list)  # semana → lista de días
    Dproh   = []           # miércoles/domingos

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
                    if date.weekday() in (2, 6):  # mié=2, dom=6
                        Dproh.append(d)
            if iso_w not in sigma_w and W_w[iso_w]:
                sigma_w[iso_w] = m

    assert d_counter == 365, "Error: calendario incompleto"
    Dproh = sorted(set(Dproh))
    return D, Dproh, Hn, B, W, S, sigma_d, sigma_w, dict(W_w)

def build_ugas(place="Las Condes, Santiago Metropolitan Region, Chile"):
    # 2) Descarga y filtra vegetación real
    tags_green = {
        'leisure': ['park','garden','playground'],
        'landuse': ['grass','meadow','orchard'],
        'natural': ['grassland','wood']
    }
    gdf_green = ox.features_from_place(place, tags_green)
    gdf_green = gdf_green[gdf_green.geometry.type.isin(['Polygon','MultiPolygon'])]

    # 3) Descarga y filtra polígonos a excluir (edificios, caminos, parkings…)
    tags_excl = {
        'building': True,
        'highway': ['pedestrian','footway','path'],
        'landuse': ['residential','industrial','parking']
    }
    gdf_excl = ox.features_from_place(place, tags_excl)
    gdf_excl = gdf_excl[gdf_excl.geometry.type.isin(['Polygon','MultiPolygon'])]

    # 4) Resta geométrica para limpiar vegetación
    gdf_clean = gpd.overlay(gdf_green, gdf_excl, how='difference')
    gdf_clean = gdf_clean[gdf_clean.geometry.type.isin(['Polygon','MultiPolygon'])]

    # 5) Calcula área en m² (CRS métrico UTM 19S / EPSG:32719)
    gdf_clean = gdf_clean.to_crs(epsg=32719)
    gdf_clean['area_m2'] = gdf_clean.geometry.area
    gdf_clean = gdf_clean.to_crs(epsg=4326)

    # 6) Separa parques grandes por nombre
    parques_objetivo = ['Parque Araucano', 'Parque Juan Pablo II']
    gdf_clean['name'] = gdf_clean['name'].fillna('')
    parques_grandes   = gdf_clean[gdf_clean['name'].isin(parques_objetivo)].copy()
    parques_pequenos  = gdf_clean[~gdf_clean['name'].isin(parques_objetivo)].copy()

    # 7) Asigna IDs únicos
    parques_grandes   = parques_grandes.reset_index(drop=True)
    parques_pequenos  = parques_pequenos.reset_index(drop=True)
    parques_grandes  ['uga_id'] = parques_grandes.index     # 0…N1-1
    parques_pequenos ['uga_id'] = parques_pequenos.index + len(parques_grandes)

    # 8) Construye un único GeoDataFrame de UGAs
    gdf_ugas = pd.concat([parques_grandes, parques_pequenos], ignore_index=True)

    # 9) Construye los conjuntos para el modelo
    Z       = list(gdf_ugas['uga_id'])
    calle   = {row.uga_id: int(row.geometry.geom_type=='LineString' or row.geometry.geom_type=='MultiLineString')
               for _,row in gdf_ugas.iterrows()}  # aquí asumimos que las calles son líneas
    # Pero si tus UGAs solo incluyen polígonos, marca calle=1 solo para los que sean calle:
    # por ejemplo: gdf_ugas['uga_type']=='calle' etc.
    parque  = {row.uga_id: int(row['name'] in parques_objetivo) for _,row in gdf_ugas.iterrows()}
    privado = {row.uga_id: 0 for _,row in gdf_ugas.iterrows()}  # ajustar si hay privadas
    vert    = {row.uga_id: 1 for _,row in gdf_ugas.iterrows()}  # puedes refinar según datos OSM
    gris    = {row.uga_id: int(row['name']=='Parque Araucano') for _,row in gdf_ugas.iterrows()}  # ejemplo
    tau     = {row.uga_id: 1 for _,row in gdf_ugas.iterrows()}  # 1=césped, ajustar si conviene
    area    = {row.uga_id: row['area_m2'] for _,row in gdf_ugas.iterrows()}
    beta_i  = {row.uga_id: 0. if parque[row.uga_id]==1 else 4. for _,row in gdf_ugas.iterrows()}

    return Z, calle, parque, privado, vert, gris, tau, area, beta_i

def build_hidro_eco():
    A_pot  : Dict[int, float]          = {}   # Dotación potable mensual (m³)
    A_gris : Dict[int, float]          = {}   # Dotación gris mensual (m³)
    f                    : Dict[Tuple[int,int], int]    = defaultdict(int)    # Frecuencia mínima
    r_parque             : Dict[Tuple[int,int], int]    = defaultdict(int)    # Frecuencia parques
    Vmin                 : Dict[Tuple[int,int], float]  = defaultdict(float)  # Volumen mínimo
    c_pot  : float = 0.0    # Costo agua potable (USD/m³)
    c_gris : float = 0.0    # Costo agua gris (USD/m³)
    lam    : float = 0.0    # Penalización déficit (USD/m³)
    M      : float = 0.0    # Límite hidráulico (m³/h)
    min_tau_month : Dict[Tuple[int,int], int] = defaultdict(int)

    A_pot  = {s: 0.0 for s in S}
    A_gris = {s: 0.0 for s in S}
    for s in S:
        # demanda base mensual (factor estacional simple)
        factor = 1.3 if s in (1,2,12) else 0.9 if s in (6,7) else 1.0
        A_pot[s]  = round( sum(area[i] for i in Z)*4*factor/12 , 1 )
        A_gris[s] = round( A_pot[s]*0.4 , 1 )          # 40 % potencial grises

    f = defaultdict(int); r_parque = defaultdict(int); Vmin = defaultdict(float)
    for t in [1,2,3]:
        for s in S:
            base_freq = 2 if s in (1,2,12) else 1
            f[(t,s)] = base_freq
            r_parque[(t,s)] = base_freq + 1            # un riego extra
            # ET₀ veraniega 6 mm d⁻¹ ≈ 42 mm sem; Suponemos 20 % de reposición:
            Vmin[(t,s)] = round( 0.0002 * base_freq , 3 )  # m³ por m²; ≈ 0.1-0.2

    beta_i = {i: (5.0 if calle[i] else 0.0) for i in Z}

    c_pot  = 0.45        # $/m³ tarifa 2024-25 (aguas Andinas)  [oai_citation:10‡USGS](https://pubs.water.usgs.gov/SIR20075156?utm_source=chatgpt.com)
    c_gris = 0.12        # $/m³ costo interno de reutilización  [oai_citation:11‡Chelan PUD](https://www.chelanpud.org/conservationhome/water-conservation/water-use-calculator?utm_source=chatgpt.com)
    lam    = 270      # $/m³ déficit (>> c_pot)

    M = 121.5

    for t in [1,2,3]:
        for m in S:
            minutes = [3, 6, 5]
            if m in [1, 12]:
                minutes = [6, 10, 5]
            elif m in [2, 11]:
                minutes = [5, 8, 8]
            elif m == 3:
                minutes = [3, 6, 7]
            min_tau_month[(t, m)] = minutes[t-1]

    return A_pot, A_gris, f, r_parque, Vmin, c_pot, c_gris, lam, M, min_tau_month

# Calendario
D, Dproh, Hn, B, W, S, sigma_d, sigma_w, W_w = build_calendar()

# UGAs
Z, calle, parque, privado, vert, gris, tau, area, beta_i = build_ugas()

# Consumo
A_pot, A_gris, f, r_parque, Vmin, c_pot, c_gris, lam, M, min_tau_month = build_hidro_eco()

# Imprime resumen
print("Días (D):", len(D))
print("Días sin riego (Dproh):", Dproh[:5], "…")
print("Horas nocturnas (Hn):", Hn)
print("Bloques diurnos (B):", B)
print("Semanas (W):", W[:5], "…")
print("Meses (S):", S)
print("UGAs (Z):", Z)
print("Atributos ejemplo:", {k:calle[k] for k in Z[:3]}, {k:parque[k] for k in Z[:3]})