import math
from pathlib import Path
import os
import re
import json
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import numpy as np
import logging

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / 'data'
LOGS_DIR = ROOT_DIR / 'logs'
DOKLADNOSC_GPS_M = 30.0
OCZEKIWANA_ODL_OD_KONCA = 500.0
MAX_ODLEGLOSC_OD_PROSTEJ_TRASY_M = 350

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

def wyznacz_punkty_pomiarowe_pogody(linie: list[str]) -> list[tuple[float, float]]:
    wszystkie_przystanki = set()
    pattern_str = r"trasa_(" + "|".join(linie) + r")\.json"
    pattern = re.compile(pattern_str)
    for filename in os.listdir(DATA_DIR):
        if pattern.match(filename):
            with open(DATA_DIR / filename) as f:
                trasa = json.load(f)
                for wariant in trasa['warianty_tras']:
                    if len(wariant) <= 2:
                        continue
                    wszystkie_przystanki.update(trasa['warianty_tras'][wariant].keys())

    wspolrzedne = []
    with open(DATA_DIR / 'przystanki.json') as f:
        przystanki = json.load(f)
        for przystanek_id in wszystkie_przystanki:
            lat = przystanki[przystanek_id]['lat']
            lon = przystanki[przystanek_id]['lon']
            wspolrzedne.append([lat, lon])

    zakres_k_centroidow = range(10, 30)
    wyniki_sylwetek = {k: [] for k in zakres_k_centroidow}
    iteracji_usredniajacych = 20

    X = np.array(wspolrzedne)

    logger.info("Rozpoczynam proces wyboru optymalnych punktów pomiaru pogody...")
    for j in range(iteracji_usredniajacych):
        logger.debug(f"Próba {j+1}/{iteracji_usredniajacych}")
        for k in zakres_k_centroidow:
            kmeans = KMeans(n_clusters=k, n_init=20, random_state=67).fit(X)
            wynik_sylwetki = silhouette_score(X, kmeans.labels_)
            wyniki_sylwetek[k].append(wynik_sylwetki)

    srednie_sylwetki = {k: np.mean(sylwetki) for k, sylwetki in wyniki_sylwetek.items()}
    najlepsze_k = max(srednie_sylwetki, key=lambda k: srednie_sylwetki[k])
    logger.info(f"Optymalna liczba punktów pomiarowych pogody: {najlepsze_k}")
    kmeans = KMeans(n_clusters=najlepsze_k, n_init=20, random_state=67).fit(X)

    return [tuple(wspolrzedne.tolist()) for wspolrzedne in kmeans.cluster_centers_]