import io
import zipfile
import requests
import src.utils as utils
import pandas as pd
import logging
import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

retry_strategy = Retry(
    total=7,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=['GET']
)

adapter = HTTPAdapter(max_retries=retry_strategy)

session = requests.Session()
session.mount("https://", adapter)

logger = logging.getLogger(__name__)

def pobierz_dane_gtfs():
    url = "https://cdn.zbiorkom.live/gtfs/warsaw.zip"
    extract_to = utils.DATA_DIR

    try:
        logging.info(f'Pobieram dane GTFS...')
        response = session.get(url=url)
        response.raise_for_status()
        
    except Exception as e:
        logger.error(f"Błąd przy pobieraniu danych GTFS: {e}")
        return 1

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        all_files = archive.namelist()
        to_save = ['trips.txt', 'shapes.txt', 'stop_times.txt']
        for file in all_files:
            if file in to_save:
                archive.extract(file, path=extract_to)
    logger.info('Sukces, udało się pobrać dane z GTFS')
    return 0


def pobierz_geometrie_linii(linia: str) -> dict:
    try:
        trips = pd.read_csv(utils.DATA_DIR / 'trips.txt', usecols=['route_id', 'shape_id'])
        unikalne_shape_id = trips[trips['route_id'] == linia]['shape_id'].dropna().unique()
        
        if len(unikalne_shape_id) == 0:
            logger.warning(f"Brak przypisanych kształtów (shape_id) dla linii {linia}")
            return {}

        shapes = pd.read_csv(utils.DATA_DIR / 'shapes.txt', usecols=['shape_id', 'shape_pt_lat', 'shape_pt_lon', 'shape_pt_sequence'])
        shapes_linii = shapes[shapes['shape_id'].isin(unikalne_shape_id)].copy()
        shapes_linii.sort_values(by=['shape_id', 'shape_pt_sequence'], inplace=True)
        
        geometria_tras = {}
        for shape_id, grupa in shapes_linii.groupby('shape_id'):
            # WAZNE! zwraca (lon, lat) a nie (lat, lon) bo sie przyda pozniej tak
            geometria_tras[shape_id] = list(zip(grupa['shape_pt_lon'], grupa['shape_pt_lat']))
            
        logger.info(f"Załadowano {len(geometria_tras)} wariantów tras dla linii {linia}")
        return geometria_tras
        
    except FileNotFoundError as e:
        logger.error(f"Brak pliku GTFS: {e}")
        return {}

def mapuj_trasy_na_shapes(linia: str):
    plik_tras = utils.DATA_DIR / f"trasa_{linia}.json"
        
    with open(plik_tras, 'r', encoding='utf-8') as f:
        dane_ztm = json.load(f)
        
    warianty_ztm = dane_ztm.get("warianty_tras", {})

    trips = pd.read_csv(utils.DATA_DIR / "trips.txt", usecols=['route_id', 'trip_id', 'shape_id'], dtype=str)
    stop_times = pd.read_csv(
        utils.DATA_DIR / "stop_times.txt", 
        usecols=['trip_id', 'stop_id', 'stop_sequence'], 
        dtype={'trip_id': str, 'stop_id': str}
    )

    trips_linii = trips[trips['route_id'] == linia]
    trip_ids = trips_linii['trip_id'].unique()
    
    stop_linii = stop_times[stop_times['trip_id'].isin(trip_ids)].copy()
    
    # ujednolicenie z 2130_01 do 213001 bo tak w gtfs
    stop_linii['stop_id_clean'] = stop_linii['stop_id'].str.replace('_', '')
    stop_linii = stop_linii.sort_values(by=['trip_id', 'stop_sequence'])

    # usuniecie brzegowego "przystanku" R bo to zajezdnia
    udane_mapowanie = True
    for nazwa_wariantu, dane_wariantu in warianty_ztm.items():
        posortowane_przystanki_ztm = sorted(
            dane_wariantu.items(), 
            key=lambda x: int(x[1]['nr_kolejnosci'])
        )
        
        sekwencja_ztm_zespoly = [przystanek_id.split('_')[0] for przystanek_id, _ in posortowane_przystanki_ztm]
        
        while sekwencja_ztm_zespoly and 'R' in sekwencja_ztm_zespoly[0]:
            sekwencja_ztm_zespoly.pop(0)
        while sekwencja_ztm_zespoly and 'R' in sekwencja_ztm_zespoly[-1]:
            sekwencja_ztm_zespoly.pop(-1)
            
        if len(sekwencja_ztm_zespoly) < 2:
            continue
            
        pierwszy_ztm = sekwencja_ztm_zespoly[0]
        ostatni_ztm = sekwencja_ztm_zespoly[-1]
        
        znaleziono_shape = None

        for trip_id, grupa in stop_linii.groupby('trip_id'):
            sekwencja_gtfs_zespoly = [stop[:-2] for stop in grupa['stop_id_clean']]
            
            while sekwencja_gtfs_zespoly and 'R' in sekwencja_gtfs_zespoly[0]:
                sekwencja_gtfs_zespoly.pop(0)
            while sekwencja_gtfs_zespoly and 'R' in sekwencja_gtfs_zespoly[-1]:
                sekwencja_gtfs_zespoly.pop(-1)
                
            if len(sekwencja_gtfs_zespoly) < 2: 
                continue
            
            pierwszy_gtfs = sekwencja_gtfs_zespoly[0]
            ostatni_gtfs = sekwencja_gtfs_zespoly[-1]
            
            if pierwszy_ztm == pierwszy_gtfs and ostatni_ztm == ostatni_gtfs:
                shape_id_wiersz = trips_linii[trips_linii['trip_id'] == trip_id]
                znaleziono_shape = shape_id_wiersz['shape_id'].values[0]
                break

        if znaleziono_shape:
            dane_ztm["warianty_tras"][nazwa_wariantu]["shape_id"] = znaleziono_shape
        else:
            udane_mapowanie = False
            logging.warning(f"Brak dopasowania kształtu trasy dla {linia}/{nazwa_wariantu}")

    plik_wyjsciowy = utils.DATA_DIR / f"trasy_{linia}_z_shapes.json"
    with open(plik_wyjsciowy, 'w', encoding='utf-8') as f:
        json.dump(dane_ztm, f, indent=4, ensure_ascii=False)

    if udane_mapowanie:
        logger.info(f'Udane mapowanie tras na ich kształty dla linii {linia}')    
    else:
        logger.warning(f'Zakończono mapowanie tras dla linii {linia}')