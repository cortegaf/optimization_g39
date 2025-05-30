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
    gdf_green = ox.geometries_from_place(place, tags_green)
    gdf_green = gdf_green[gdf_green.geometry.type.isin(['Polygon','MultiPolygon'])]

    # 3) Descarga y filtra polígonos a excluir (edificios, caminos, parkings…)
    tags_excl = {
        'building': True,
        'highway': ['pedestrian','footway','path'],
        'landuse': ['residential','industrial','parking']
    }
    gdf_excl = ox.geometries_from_place(place, tags_excl)
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

if __name__=="__main__":
    # Calendario
    D, Dproh, Hn, B, W, S, sigma_d, sigma_w, W_w = build_calendar()

    # UGAs
    Z, calle, parque, privado, vert, gris, tau, area, beta_i = build_ugas()

    # Imprime resumen
    print("Días (D):", len(D))
    print("Días sin riego (Dproh):", Dproh[:5], "…")
    print("Horas nocturnas (Hn):", Hn)
    print("Bloques diurnos (B):", B)
    print("Semanas (W):", W[:5], "…")
    print("Meses (S):", S)
    print("UGAs (Z):", Z)
    print("Atributos ejemplo:", {k:calle[k] for k in Z[:3]}, {k:parque[k] for k in Z[:3]})