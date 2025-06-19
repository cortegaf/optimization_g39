# ---------------------------------------------------------
#  ET constructor
#  genera ET[(z,d)]  con d = 1…365  (mm/día)               |
# ---------------------------------------------------------
import datetime as dt
import pandas as pd

def build_ET_dict(irr_zones, month_et):
    """
    irr_zones : lista de uga_id (irrigables) -> ['1001', '1002', …]
    month_et  : dict {1: mm, 2: mm, … 12: mm}  (mm/día)

    return     : dict {(z,d): mm}
    """
    # Pre-calculo: día calendario → mes (1–12)
    day_to_month = {
        d: (dt.date(2025, 1, 1) + dt.timedelta(days=d-1)).month   # 2025 = año no bisiesto
        for d in range(1, 366)
    }

    # Construye el diccionario completo
    ET = {}
    for z in irr_zones:
        for d in range(1, 366):
            m = day_to_month[d]
            # Si quisieras factor zona: multiplica aquí
            ET[z, d] = month_et[m]             # * ajuste_zona[z]   # <--
    return ET

def load_irrigation_zones(csv_file='zonas.csv'):
    """
    Carga todas las zonas de riego desde el archivo CSV
    """
    df = pd.read_csv(csv_file)
    # Filtra solo las zonas de tipo 'irr' (irrigables)
    irr_zones = df[df['type'] == 'irr']['uga_id'].astype(str).tolist()
    return irr_zones

# -------------------- EJEMPLO de uso ----------------------
if __name__ == "__main__":
    # Carga todas las zonas de riego desde el CSV
    all_zones = load_irrigation_zones()
    print(f"Total de zonas de riego: {len(all_zones)}")
    print(f"Primeras 10 zonas: {all_zones[:10]}")

    # tabla mm/día tomada de tu gráfica (redondeada)
    month_ET = {
        1: 6.0, 2: 5.3, 3: 4.0, 4: 3.0,
        5: 2.0, 6: 1.6, 7: 1.4, 8: 1.6,
        9: 2.0, 10: 3.0, 11: 4.3, 12: 5.9,
    }

    # Genera la matriz completa de ET para todas las zonas
    ET_dict = build_ET_dict(all_zones, month_ET)
    
    print(f"\nTamaño del diccionario ET: {len(ET_dict)} entradas")
    print(f"Zonas únicas en ET: {len(set(z for z, d in ET_dict.keys()))}")
    print(f"Días únicos en ET: {len(set(d for z, d in ET_dict.keys()))}")
    
    # ejemplo: cuánto es ET para zona '1001' el día 60 (1 marzo)?
    print(f"\nEjemplo - ET para zona '1001' el día 60: {ET_dict['1001', 60]} mm/día")
    print(f"Ejemplo - ET para zona '20001' el día 180: {ET_dict['20001', 180]} mm/día")
    
    # Verificar que tenemos datos para todas las zonas
    zones_in_et = set(z for z, d in ET_dict.keys())
    print(f"\nVerificación: ¿Todas las zonas están en ET? {set(all_zones) == zones_in_et}")