import math
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / 'data'
DOKLADNOSC_GPS_M = 30.0
OCZEKIWANA_ODL_OD_KONCA = 150.0

def oblicz_odleglosc(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    lon1_rad = math.radians(lon1)
    lon2_rad = math.radians(lon2)

    delta_lat = abs(lat2_rad - lat1_rad)
    delta_lon = abs(lon2_rad - lon1_rad)

    srednia_lat = (lat1_rad + lat2_rad) / 2.0
    x = delta_lon * math.cos(srednia_lat)
    y = delta_lat
    dystans = R * math.sqrt(x**2 + y**2)

    return round(dystans)

def czas_na_sekundy(czas_str: str) -> int:
    
    czas_str = czas_str.split(' ')[-1] # jeśli z datą to odcinam
    godziny, minuty, sekundy = map(int, czas_str.split(':'))

    wynik = sekundy + 60*minuty + 3600*godziny
    return wynik

def czy_pojazd_sie_ruszyl(lat1: float, lon1: float, lat2: float, lon2: float) -> bool:
        return oblicz_odleglosc(lat1, lon1, lat2, lon2) > DOKLADNOSC_GPS_M

def oblicz_proporcje_przybytej_drogi(lat_a: float, lon_a: float, lat_b: float, lon_b: float, lat_sz: float, lon_sz: float) -> float:
        d_a = oblicz_odleglosc(lat_a, lon_a, lat_sz, lon_sz)
        d_b = oblicz_odleglosc(lat_b, lon_b, lat_sz, lon_sz)
        przebyte = d_a / (d_a + d_b)
        return przebyte