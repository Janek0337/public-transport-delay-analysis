import requests
import json
import math
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)
BASE_URL = "https://api.um.warszawa.pl/api/action/"

def stworz_trase_linii(linia: int, api_key: str):
    endpoint = "public_transport_routes"
    URL = BASE_URL + endpoint

    params = {
        'apikey': api_key,
    }

    try:
        res = requests.get(url=URL, params=params)
        res.raise_for_status()
        data = res.json()
        
    except Exception as e:
        logger.error(f"Błąd API przy pobieraniu trasy linii {linia}: {e}")
        return 1

    trasa_linii = data['result'][str(linia)]
    dobra_trasa = {'linia': linia}

    for trasa in trasa_linii:
        dobra_trasa[trasa] = dict()
        for nr_przystanku in trasa_linii[trasa]:
            id_przystanku = trasa_linii[trasa][nr_przystanku]['nr_zespolu']
            nmr_zespolu = trasa_linii[trasa][nr_przystanku]['nr_przystanku']
            odl = trasa_linii[trasa][nr_przystanku]['odleglosc']
            dobra_trasa[trasa][nr_przystanku] = {
                'przystanek_id': f"{id_przystanku}_{nmr_zespolu}",
                'odleglosc': odl
            }

    sciezka = DATA_DIR / f"trasa_{linia}.json"
    with open(sciezka, 'w', encoding='utf-8') as f:
        json.dump(dobra_trasa, f, ensure_ascii=False, indent=4)

    return 0


def stworz_rozklad_linii(linia: int, api_key: str):
    endpoint = "dbtimetable_get"
    URL = BASE_URL + endpoint
    ID_ENDPOINT_ROZKLADOW = 'e923fa0e-d96c-43f9-ae6e-60518c9f3238'

    sciezka = DATA_DIR / f"trasa_{linia}.json"
    with open(sciezka, "r") as f:
        json_tras = json.load(f)
        final_json = {'linia': linia, 'brygady': dict()}
        
        unikalne_przystanki_id = set()
        for trasa in json_tras:
            if trasa == 'linia':
                continue
            for przystanek in json_tras[trasa].values():
                unikalne_przystanki_id.add(przystanek['przystanek_id'])

        for przystanek_id in unikalne_przystanki_id:

            przystanek_info = przystanek_id.split('_')
            params = {
                'id': ID_ENDPOINT_ROZKLADOW,
                'apikey': api_key,
                'busstopId': przystanek_info[0],
                'busstopNr': przystanek_info[1],
                'line': linia
            }
            try:
                res = requests.get(url=URL, params=params)
                res.raise_for_status()
                data = res.json()

            except Exception as e:
                logger.error(f"Błąd API przy tworzeniu rozkładu jazdy linii {linia}: {e}")
                return 1

            rozklad_przystanku = {'przystanek_id': przystanek_id,
                                'line': linia,
                                'rozklad': []
                                }
            
            kursy = data['result']
            if not isinstance(kursy, list):
                logger.debug(f"Pominęto przystanek {przystanek_id} (brak rozkładu)")
                continue

            for kurs in kursy:
                stop_info = dict()

                for kvp in kurs:
                    if kvp['key'] == 'brygada':
                        stop_info['brygada'] = kvp['value']
                    if kvp['key'] == 'trasa':
                        stop_info['trasa'] = kvp['value']
                    if kvp['key'] == 'czas':
                        stop_info['czas'] = kvp['value']
                
                rozklad_przystanku['rozklad'].append(stop_info)

            for stop in rozklad_przystanku['rozklad']:
                nr_brygady = stop['brygada']
                if nr_brygady not in final_json['brygady']:
                    final_json['brygady'][nr_brygady] = []

                final_json['brygady'][nr_brygady].append(
                    {'przystanek_id': przystanek_id,
                    'czas': stop['czas'],
                    'trasa': stop['trasa']
                    }
                    )
                
    for brygada in final_json['brygady']:
        final_json['brygady'][brygada].sort(key=lambda x: x['czas'])
                
    sciezka_out = DATA_DIR / f"rozklad_{linia}.json"
    with open(sciezka_out, 'w', encoding="utf-8") as out:
        json.dump(final_json, out, ensure_ascii=False, indent=4)

    return 0


def stworz_baze_polozen_przystankow(api_key: str):
    endpoint = "dbtimetable_get"
    PRZYSTANKI_URL = BASE_URL + endpoint
    ID_ENDPOINTU_PRZYSTANKOW = 'ab75c33d-3a26-4342-b36a-6e5fef0a3ac3'
    params = {
        'id': ID_ENDPOINTU_PRZYSTANKOW,
        'apikey': api_key,
    }

    try:
        res = requests.get(url=PRZYSTANKI_URL, params=params)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        logger.error(f"Błąd API przy pobieraniu listy położeń przystanków: {e}")
        return 1

    przystanki = dict()
    for przystanek in data['result']:
        dobry_przystanek = dict()
        for kvp in przystanek['values']:
            if kvp['key'] == 'zespol':
                zespol = kvp['value']
            if kvp['key'] == 'slupek':
                slupek = kvp['value']
            if kvp['key'] == 'szer_geo':
                dobry_przystanek['lat'] = float(kvp['value'])
            if kvp['key'] == 'dlug_geo':
                dobry_przystanek['lon'] = float(kvp['value'])
            if kvp['key'] == 'nazwa_zespolu':
                dobry_przystanek['nazwa_przystanku'] = kvp['value']
            
        przystanek_id = f"{zespol}_{slupek}"
        przystanki[przystanek_id] = dobry_przystanek

    sciezka = DATA_DIR / 'przystanki.json'
    with open(sciezka, 'w', encoding='utf-8') as f:
        json.dump(przystanki, f, ensure_ascii=False, indent=4)
    
    return 0

def zbierz_obecne_polozenie(api_key: str, linie: list) -> list[dict]:
    endpoint = 'busestrams_get'
    BUS_LOC_RESOURCE_ID = 'f2e5503e-927d-4ad3-9500-4ab9e55deb59'
    BUS_LOC_URL = BASE_URL + endpoint
    type = 1 # 1 dla autobusu, 2 tramwaj

    params = {
        'resource_id': BUS_LOC_RESOURCE_ID,
        'apikey': api_key,
        'type': type
    }

    try:
        res = requests.post(url=BUS_LOC_URL, params=params)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        logger.error(f"Błąd API przy pobieraniu aktualnego położenia pojazdów: {e}")
        return []

    wynik = [{'linia': x['Lines'],
            'lat': x['Lat'],
            'lon': x['Lon'],
            'brygada': x['Brigade'],
            'czas': x['Time']
            } for x in data['result'] if x['Lines'] in linie]

    with open('polozenie.json', 'w') as f:
        json.dump(wynik, f, indent=4)

    return wynik