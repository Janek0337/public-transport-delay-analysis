import json
import logging
from typing import List, Tuple, TypedDict

import pandas as pd
from src import utils

from src.kalkulator_przestrzenny import Kalkulator_Przestrzenny

logger = logging.getLogger(__name__)

GpsPoint = Tuple[float, float, int] # lat, lon, czas_s
class StanPojazdu(TypedDict):
    stan: str
    historia_gps: List[GpsPoint]
    id_kursu: int
    nastpeny_przystanek: dict | None
    poprzedni_przystanek: dict | None
    ostatnie_metry: list
    ostatni_czas_zapisu: int
    shape_id: str | None

BrygadaInfo = dict[str, StanPojazdu] # numer_brygady: StanPojazdu
LinieInfo = dict[str, BrygadaInfo] # numer_linii: BrygadaInfo

def stworz_nowy_stan(lat: float, lon: float, czas: int) -> StanPojazdu:
    return {
        'stan': 'INICJALIZACJA',
        'historia_gps': [(lat, lon, czas)],
        'id_kursu': -1,
        'nastpeny_przystanek': None,
        'poprzedni_przystanek': None,
        'ostatnie_metry': [],
        'ostatni_czas_zapisu': -1,
        'shape_id': None
    }

class TrackerZTM:
    pojazdy: LinieInfo
    rozklady: dict[str, dict[str, List]] # linia: {nr_brygady: [lista kursów]}
    przystanki: dict[str, dict] # id_przystanku: {nazwa, lat, lon}
    kalkulator: Kalkulator_Przestrzenny

    def __init__(self, linie: list):
        self.pojazdy = dict()
        self.rozklady = dict()
        self.przystanki = dict()
        self.kalkulator = Kalkulator_Przestrzenny()
        self.geometrie_tras = {} 
        self.warianty_shapes = {}

        for linia in linie:
            with open(utils.DATA_DIR / f'rozklad_{linia}.json', encoding='utf-8') as f:
                wczytany_json = json.load(f)
                self.rozklady[wczytany_json['linia']] = wczytany_json['brygady']
                self.pojazdy[linia] = dict()

            plik_mapowania = utils.DATA_DIR / f'trasy_{linia}_z_shapes.json'
            if plik_mapowania.exists():
                with open(plik_mapowania, encoding='utf-8') as f:
                    self.warianty_shapes[linia] = json.load(f).get('warianty_tras', {})
            
            surowe_geometrie = self._wczytaj_geometrie_z_plikow(linia)
            for shape_id, punkty in surowe_geometrie.items():
                self.geometrie_tras[shape_id] = self.kalkulator.buduj_trase(punkty)
        with open(utils.DATA_DIR / 'przystanki.json', encoding='utf-8') as f:
                self.przystanki = json.load(f)

    # o jednym położeniu jednej brygaday
    def przetworz_pozycje(self, linia: str, brygada: str, lat: float, lon: float, czas_gps: int) -> int | tuple:
        """
        Główna metoda wywoływana co 15 sekund dla każdego autobusu z API.
        zwraca:
        (opóźnienie, metr, nazwa_trasy) - gdy uda się określić opóźnienie
        1 - nie ma takiego pojazdu w rozkladzie, błąd
        2 - kalibracja, czekaj
        """

        # to nie jest poprawna wartość brygady dla tej linii
        if brygada not in self.rozklady[linia]:
            return 1

        # to jest nieznany jeszcze autobus (niezainicjowany)
        if brygada not in self.pojazdy[linia]:
            self.pojazdy[linia][brygada] = stworz_nowy_stan(lat, lon, czas_gps)
            logging.info(f"{linia}/{brygada}: oczekiwanie na więcej pingów")
            return 2 # przerywamy i czekamy na kolejne pingi

        pojazd = self.pojazdy[linia][brygada]

        if pojazd["stan"] == "INICJALIZACJA":

            if len(pojazd['historia_gps']) < 1:
                pojazd["historia_gps"].append((lat, lon, czas_gps))
                return 2

            # jesli pojazd nie ruszyl sie znaczoco to czekamy az sie ruszy
            if not utils.czy_pojazd_sie_ruszyl(pojazd['historia_gps'][0][0], pojazd['historia_gps'][0][1], lat, lon):
                logging.info(f"{linia}/{brygada}: Brak ruchu, oczekiwanie na dalsze pomiary do inicjalizacji")
                return 2
            
            # dodajemy nowy punkt do historii (to jest drugi punkt)
            pojazd["historia_gps"].append((lat, lon, czas_gps))
            
            rozklad_id = self._znajdz_rozklad(czas_gps, linia, brygada, lat, lon)
            if rozklad_id == -1:
                pojazd["historia_gps"].pop()
                logging.info(f"{linia}/{brygada}: Nie znaleziono trasy dla tego kursu")
                return 1
            elif rozklad_id == -2:
                pojazd["historia_gps"].pop()
                logging.info(f"{linia}/{brygada}: Inicjalizacja w pobliżu pętli, nie robię tego")
                return 2
            przystanek_A, przystanek_B = self._znajdz_miedzy_ktorymi_przystankami_trasy_pojazd(linia, brygada, rozklad_id, lat, lon)
            
            pojazd['id_kursu'] = rozklad_id
            nazwa_kursu = self.rozklady[linia][brygada][rozklad_id]['trasa']
            shape_info = self.warianty_shapes.get(linia, {}).get(nazwa_kursu, {})
            pojazd['shape_id'] = shape_info.get("shape_id")

            pojazd['stan'] = 'W_TRASIE'
            pojazd['historia_gps'] = []
            logger.info(f"{linia}/{brygada}: Udana inicjalizacja, przypisano kurs_id: {rozklad_id}")

            pojazd['poprzedni_przystanek'] = przystanek_A
            pojazd['nastpeny_przystanek'] = przystanek_B

            return 0

        elif pojazd["stan"] == "W_TRASIE":
            if pojazd['ostatni_czas_zapisu'] == czas_gps:
                logger.info(f"Brak nowych informacji o pojeździe {linia}/{brygada}, pomijam")
                return 2
            pojazd['ostatni_czas_zapisu'] = czas_gps
            id_kursu = pojazd['id_kursu']

            shape_id = pojazd.get('shape_id')
            if not shape_id or shape_id not in self.geometrie_tras:
                logger.warning(f"{linia}/{brygada}: Brak geometrii dla trasy (zjazd?). Ignoruję pomiar.")
                return 2

            linestr_trasy = self.geometrie_tras[shape_id]
            wynik_rzutowania = self.kalkulator.lokalizuj_pojazd(lat, lon, linestr_trasy)

            if wynik_rzutowania is None:
                logger.warning(f"{linia}/{brygada} wyrzucony z pomiaru (odległość od kształtu GTFS przekracza dopuszczalny limit)")
                return 2

            obecny_metr_trasy, odl_od_trasy = wynik_rzutowania

            przystanki_kursu = self.rozklady[linia][brygada][id_kursu]['przystanki']
            przystanek_A, przystanek_B = None, None
            proporcja_przebytej_drogi = 0.0

            for i in range(len(przystanki_kursu) - 1):
                p1 = przystanki_kursu[i]
                p2 = przystanki_kursu[i+1]
                if p1['metr'] <= obecny_metr_trasy <= p2['metr']:
                    przystanek_A = p1
                    przystanek_B = p2
                    if p2['metr'] > p1['metr']:
                        proporcja_przebytej_drogi = (obecny_metr_trasy - p1['metr']) / (p2['metr'] - p1['metr'])
                    break

            if not przystanek_A or not przystanek_B:
                if obecny_metr_trasy < przystanki_kursu[0]['metr']:
                    przystanek_A = przystanki_kursu[0]
                    przystanek_B = przystanki_kursu[1]
                    proporcja_przebytej_drogi = 0.0
                else:
                    przystanek_A = przystanki_kursu[-2]
                    przystanek_B = przystanki_kursu[-1]
                    proporcja_przebytej_drogi = 1.0

            pojazd['poprzedni_przystanek'] = przystanek_A
            pojazd['nastpeny_przystanek'] = przystanek_B

            # sprawdzenie trendu ruchu, czy zgodny z kierunkiem wybranej trasy
            # i czy jesli sie nie rusza to czy nie jest przypadkiem zawieszony na pętli
            pojazd['ostatnie_metry'].append(obecny_metr_trasy)
            id_kursu = pojazd['id_kursu']
            if len(pojazd['ostatnie_metry']) > 1:
                roznica1 = pojazd['ostatnie_metry'][-1] - pojazd['ostatnie_metry'][-2]
                if abs(roznica1) < utils.DOKLADNOSC_GPS_M:

                    id_pierwszego_przystanku = self.rozklady[linia][brygada][id_kursu]['przystanki'][0]['przystanek_id']
                    id_ostatniego_przystanku = self.rozklady[linia][brygada][id_kursu]['przystanki'][-1]['przystanek_id']

                    lat_pierwszego = self.przystanki[id_pierwszego_przystanku]['lat']
                    lon_pierwszego = self.przystanki[id_pierwszego_przystanku]['lon']

                    lat_ostatniego = self.przystanki[id_ostatniego_przystanku]['lat']
                    lon_ostatniego = self.przystanki[id_ostatniego_przystanku]['lon']

                    if (utils.oblicz_odleglosc(lat, lon, lat_pierwszego, lon_pierwszego) < utils.OCZEKIWANA_ODL_OD_KONCA or
                        utils.oblicz_odleglosc(lat, lon, lat_ostatniego, lon_ostatniego) < utils.OCZEKIWANA_ODL_OD_KONCA):
                        logging.warning(f'{linia}/{brygada}: zgubił się na pętli. Reinicjalizuję')
                        czysty_stan = stworz_nowy_stan(lat, lon, czas_gps)
                        self.pojazdy[linia][brygada] = czysty_stan
                        return 2

                    pojazd['ostatnie_metry'].pop()
                else:
                    if len(pojazd['ostatnie_metry']) == 3:            
                        if roznica1 < 0:
                            roznica2 = pojazd['ostatnie_metry'][-2] - pojazd['ostatnie_metry'][-3]
                            if roznica2 < 0:
                                logging.info(f"{linia}/{brygada}: Trend ruchu przeciwny do wybranej trasy, reinicjalizacja")
                                czysty_stan = stworz_nowy_stan(lat, lon, czas_gps)
                                self.pojazdy[linia][brygada] = czysty_stan
                                return 2
                        pojazd['ostatnie_metry'].pop(0)

            czas1, czas2 = przystanek_A['czas'], przystanek_B['czas']
            czas_oczekiwany_rozkladowy = czas1 + proporcja_przebytej_drogi*(czas2 - czas1)
            opoznienie = czas_gps - czas_oczekiwany_rozkladowy

            if opoznienie > 3600 or opoznienie < -600:
                logger.warning(f"{linia}/{brygada}: Nienaturalne opóźnienie ({int(opoznienie/60)}min). Pojazd do reinicjalizacji")
                czysty_stan = stworz_nowy_stan(lat, lon, czas_gps)
                self.pojazdy[linia][brygada] = czysty_stan
                return 2

            # sprawdzamy czy nie jest już na pętli
            czas_ostatniego_przystanku = self.rozklady[linia][brygada][id_kursu]['czas_konca']
            if przystanek_B['czas'] == czas_ostatniego_przystanku:
                lat_b = self.przystanki[przystanek_B['przystanek_id']]['lat']
                lon_b = self.przystanki[przystanek_B['przystanek_id']]['lon']
                
                odleglosc_od_konca = utils.oblicz_odleglosc(lat_b, lon_b, lat, lon)
                if odleglosc_od_konca < utils.OCZEKIWANA_ODL_OD_KONCA or proporcja_przebytej_drogi >= 0.9:
                    pojazd['stan'] = "NA_PETLI"
                    logger.info(f"{linia}/{brygada}: Zjazd na pętlę. Zakończono kurs {id_kursu}.")
            
            nazwa_kursu = self.rozklady[linia][brygada][id_kursu]['trasa']
            return (opoznienie, obecny_metr_trasy, nazwa_kursu)

        elif pojazd["stan"] == "NA_PETLI":
            nowy_kurs_id = pojazd['id_kursu'] + 1 
            
            while nowy_kurs_id < len(self.rozklady[linia][brygada]) and len(self.rozklady[linia][brygada][nowy_kurs_id]['przystanki']) < 2:
                nowy_kurs_id += 1

            if nowy_kurs_id >= len(self.rozklady[linia][brygada]):
                return 0 
                
            czas_poczatku_nastpenej_trasy = self.rozklady[linia][brygada][nowy_kurs_id]['czas_startu']
            
            if czas_gps >= czas_poczatku_nastpenej_trasy:
                pojazd['stan'] = 'W_TRASIE'
                pojazd['id_kursu'] = nowy_kurs_id

                nazwa_kursu = self.rozklady[linia][brygada][nowy_kurs_id]['trasa']
                shape_info = self.warianty_shapes.get(linia, {}).get(nazwa_kursu, {})
                pojazd['shape_id'] = shape_info.get("shape_id")

                pojazd['poprzedni_przystanek'] = self.rozklady[linia][brygada][nowy_kurs_id]['przystanki'][0]
                pojazd['nastpeny_przystanek'] = self.rozklady[linia][brygada][nowy_kurs_id]['przystanki'][1]
                pojazd['ostatnie_metry'] = []
                logger.info(f"{linia}/{brygada}: Rusza w nowy kurs {nowy_kurs_id}")
                return 0
            logger.info(f"{linia}/{brygada}: Stoi na pętli")
            return 0

    def _znajdz_rozklad(self, czas_teraz: int, linia: str, brygada: str, lat_sz: float, lon_sz: float) -> int:

        okno_w_przod = utils.czas_na_sekundy('00:45:00')
        okno_w_tyl = utils.czas_na_sekundy('00:10:00')

        kandydaci = []
        for idx, kurs in enumerate(self.rozklady[linia][brygada]):
            if (czas_teraz >= kurs['czas_startu'] - okno_w_tyl 
            and czas_teraz <= kurs['czas_konca'] + okno_w_przod
            and not len(kurs['przystanki']) <= 2):
                kandydaci.append((idx, kurs))

        if len(kandydaci) == 0:
            return -1 
        
        pojazd = self.pojazdy[linia][brygada]
        lat1, lon1 = pojazd['historia_gps'][-2][0], pojazd['historia_gps'][-2][1] 
        lat2, lon2 = pojazd['historia_gps'][-1][0], pojazd['historia_gps'][-1][1] 
        
        for idx, kurs in kandydaci:
            id_start = kurs['przystanki'][0]['przystanek_id']
            id_koniec = kurs['przystanki'][-1]['przystanek_id']
            
            lat_s, lon_s = self.przystanki[id_start]['lat'], self.przystanki[id_start]['lon']
            lat_k, lon_k = self.przystanki[id_koniec]['lat'], self.przystanki[id_koniec]['lon']
            
            # jeśli jest w promieniu 200m od startu lub końca potencjalnej trasy to nie rozważamy go
            if (utils.oblicz_odleglosc(lat_sz, lon_sz, lat_s, lon_s) < utils.OCZEKIWANA_ODL_OD_KONCA or
                utils.oblicz_odleglosc(lat_sz, lon_sz, lat_k, lon_k) < utils.OCZEKIWANA_ODL_OD_KONCA):
                return -2

            nazwa_kursu = kurs['trasa']
            shape_info = self.warianty_shapes.get(linia, {}).get(nazwa_kursu, {})
            shape_id = shape_info.get("shape_id")

            if not shape_id or shape_id not in self.geometrie_tras:
                continue 

            linestr_trasy = self.geometrie_tras[shape_id]
            wynik1 = self.kalkulator.lokalizuj_pojazd(lat1, lon1, linestr_trasy)
            wynik2 = self.kalkulator.lokalizuj_pojazd(lat2, lon2, linestr_trasy)

            if wynik1 is None or wynik2 is None:
                continue

            dystans1, _ = wynik1
            dystans2, _ = wynik2

            if dystans2 > dystans1 + 5.0:
                return idx 

        return -1

    def _wczytaj_geometrie_z_plikow(self, linia: str) -> dict:
        try:
            trips = pd.read_csv(utils.DATA_DIR / 'trips.txt', usecols=['route_id', 'shape_id'], dtype=str)
            unikalne_shape_id = trips[trips['route_id'] == linia]['shape_id'].dropna().unique()
            
            if len(unikalne_shape_id) == 0:
                return {}

            shapes = pd.read_csv(utils.DATA_DIR / 'shapes.txt', usecols=['shape_id', 'shape_pt_lat', 'shape_pt_lon', 'shape_pt_sequence'])
            shapes_linii = shapes[shapes['shape_id'].isin(unikalne_shape_id)].copy()
            shapes_linii.sort_values(by=['shape_id', 'shape_pt_sequence'], inplace=True)
            
            geometria_tras = {}
            for shape_id, grupa in shapes_linii.groupby('shape_id'):
                geometria_tras[shape_id] = list(zip(grupa['shape_pt_lon'], grupa['shape_pt_lat']))
                
            return geometria_tras
            
        except FileNotFoundError as e:
            logger.error(f"Brak plików GTFS w DATA_DIR! Kolektor zadziałał poprawnie? {e}")
            return {}

    def _znajdz_trzy_kolejne_najblizsze_przystanki_na_trasie(self, linia: str, brygada: str, id_kursu: int, lat_sz: float, lon_sz: float) -> list:
        """ DEPRECATED """
        lista_przystankow_kursu = self.rozklady[linia][brygada][id_kursu]['przystanki']

        najblizszy_przystanek = min(
            lista_przystankow_kursu, 
            key=lambda x: utils.oblicz_odleglosc(
                lat_sz, lon_sz,
                self.przystanki[x['przystanek_id']]['lat'], 
                self.przystanki[x['przystanek_id']]['lon']
            )
        )

        przystanek_1_id = najblizszy_przystanek['przystanek_id']
        id_przystankow = [przystanek_1_id]

        rzeczywisty_indeks = lista_przystankow_kursu.index(najblizszy_przystanek)

        if rzeczywisty_indeks + 1 < len(lista_przystankow_kursu):
            przystanek_2_id = lista_przystankow_kursu[rzeczywisty_indeks + 1]['przystanek_id']
            id_przystankow.append(przystanek_2_id)
            if rzeczywisty_indeks + 2 < len(lista_przystankow_kursu):
                przystanek_3_id = lista_przystankow_kursu[rzeczywisty_indeks + 2]['przystanek_id']
                id_przystankow.append(przystanek_3_id)

        return id_przystankow

    def _znajdz_miedzy_ktorymi_przystankami_trasy_pojazd(self, linia: str, brygada: str,
                                                         id_kursu: int, lat_sz: float, lon_sz: float) -> tuple[dict, dict]:
        lista_przystankow_kursu = self.rozklady[linia][brygada][id_kursu]['przystanki']

        for i in range(len(lista_przystankow_kursu)):
            if i+1 < len(lista_przystankow_kursu):
                id_A = lista_przystankow_kursu[i]['przystanek_id']
                id_B = lista_przystankow_kursu[i+1]['przystanek_id']

                lat_a, lon_a = self.przystanki[id_A]['lat'], self.przystanki[id_A]['lon']
                lat_b, lon_b = self.przystanki[id_B]['lat'], self.przystanki[id_B]['lon']

                if self._sprawdz_zawartosc_w_odcinku(lat_a, lon_a, lat_b, lon_b, lat_sz, lon_sz):
                    return (lista_przystankow_kursu[i], lista_przystankow_kursu[i+1])
                
        return (dict(), dict())
                
    def _sprawdz_zawartosc_w_odcinku(self, lat_a: float, lon_a: float, lat_b: float, lon_b:  float, lat_c: float, lon_c: float) -> bool:
        dA = utils.oblicz_odleglosc(lat_c, lon_c, lat_a, lon_a)
        dB = utils.oblicz_odleglosc(lat_c, lon_c, lat_b, lon_b)
        dC = utils.oblicz_odleglosc(lat_b, lon_b, lat_a, lon_a)

        return dA + dB <= dC + utils.MAX_ODLEGLOSC_OD_PROSTEJ_TRASY_M
    
    def _oblicz_proporcje_przebytej_trasy(self, przystanek_A: dict, przystanek_B: dict, lat_sz: float, lon_sz: float) -> float:
        """ DEPRECATED """
        lat_a, lon_a = self.przystanki[przystanek_A['przystanek_id']]['lat'], self.przystanki[przystanek_A['przystanek_id']]['lon']
        lat_b, lon_b = self.przystanki[przystanek_B['przystanek_id']]['lat'], self.przystanki[przystanek_B['przystanek_id']]['lon']
        
        dC = utils.oblicz_odleglosc(lat_a, lon_a, lat_b, lon_b)
        if dC == 0:
            return 0.0
        
        dA = utils.oblicz_odleglosc(lat_a, lon_a, lat_sz, lon_sz)
        dB = utils.oblicz_odleglosc(lat_b, lon_b, lat_sz, lon_sz)

        proporcja = (dA**2 + dC**2 - dB**2 ) / (2 * dC**2)

        return max(0.0, min(1.0, proporcja))