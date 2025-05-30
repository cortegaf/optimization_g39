import osmnx as ox
import geopandas as gpd

place = "Las Condes, Santiago Metropolitan Region, Chile"

# 1) Extrae solo vegetación "real" (ya lo tenías)
tags_green = {
    'leisure': ['park','garden','playground'],
    'landuse': ['grass','meadow','orchard'],
    'natural': ['grassland','wood']
}
gdf_green = ox.features_from_place(place, tags_green)
gdf_green = gdf_green[gdf_green.geometry.type.isin(['Polygon','MultiPolygon'])]

# 2) Excluye edificios, caminos, parkings…
tags_excl = {
    'building': True,
    'highway': ['pedestrian','footway','path'],
    'landuse': ['residential','industrial','parking']
}
gdf_excl = ox.features_from_place(place, tags_excl)
gdf_excl = gdf_excl[gdf_excl.geometry.type.isin(['Polygon','MultiPolygon'])]

# 3) Resta geométrica para limpiar
gdf_clean = gpd.overlay(gdf_green, gdf_excl, how='difference')

# 4) Asegúrate de tener el atributo `name` (si no viene, puedes usar tags 'leisure_name' o similar)
#    y calcula área en m²
gdf_clean['area_m2'] = gdf_clean.geometry.to_crs(epsg=32719).area  # CRS UTM para medir en metros

# 5) Filtra los dos parques grandes por nombre
parques_objetivo = ['Parque Araucano', 'Parque Juan Pablo II']
parques_grandes = gdf_clean[gdf_clean['name'].isin(parques_objetivo)].copy()
parques_restantes = gdf_clean[~gdf_clean['name'].isin(parques_objetivo)].copy()

# 6) Asigna un flag o tipo para tu dataset.py
parques_grandes['uga_type']     = 'parque_grande'
parques_restantes['uga_type']   = 'parque_pequeño'

# 7) (Opcional) Reindexa para que las UGAs tengan IDs únicos
parques_grandes = parques_grandes.reset_index(drop=True).reset_index().rename(columns={'index':'uga_id'})
parques_restantes = parques_restantes.reset_index(drop=True).reset_index().rename(columns={'index':'uga_id'})

# 8) Exporta a CSV o Shapefile para tu pipeline de datos
parques_grandes.to_file("ugas_parques_grandes.shp")
parques_restantes.to_file("ugas_parques_pequenos.shp")