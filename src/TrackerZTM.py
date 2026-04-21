from typing import TypedDict, Optional, Tuple, List
from src import utils
import json
import logging

logger = logging.getLogger(__name__)

GpsPoint = Tuple[float, float, int] # lat, lon, czas_s
class StanPojazdu(TypedDict):
    stan: str
    historia_gps: List[GpsPoint]
    id_kursu: int
    nastpeny_przystanek: dict | None
    poprzedni_przystanek: dict | None
    ostatnie_metry: list

BrygadaInfo = dict[str, StanPojazdu] # numer_brygady: StanPojazdu
LinieInfo = dict[str, BrygadaInfo] # numer_linii: BrygadaInfo

def stworz_nowy_stan(lat: float, lon: float, czas: int) -> StanPojazdu:
    return {
        'stan': 'INICJALIZACJA',
        'historia_gps': [(lat, lon, czas)],
        'id_kursu': -1,
        'nastpeny_przystanek': None,
        'poprzedni_przystanek': None,
        'ostatnie_metry': []
    }

class TrackerZTM:
    pojazdy: LinieInfo
    rozklady: dict[str, dict[str, List]] # linia: {nr_brygady: [lista kursów]}
    przystanki: dict[str, dict] # id_przystanku: {nazwa, lat, lon}

    def __init__(self, linie: list):
        self.pojazdy = dict()
        self.rozklady = dict()
        self.przystanki = dict()
        for linia in linie:
            with open(utils.DATA_DIR / f'rozklad_{linia}.json') as f:
                wczytany_json = json.load(f)
                self.rozklady[wczytany_json['linia']] = wczytany_json['brygady']
                self.pojazdy[linia] = dict()

        with open(utils.DATA_DIR / 'przystanki.json') as f:
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
            
            if (not bool(przystanek_A) or not bool(przystanek_B)):
                pojazd["historia_gps"].pop()
                logger.info(f"{linia}/{brygada}: Nie znaleziono pasującego do kursu położenia w rozkładzie")
                return 2

            pojazd['id_kursu'] = rozklad_id
            pojazd['stan'] = 'W_TRASIE'
            pojazd['historia_gps'] = []
            logger.info(f"{linia}/{brygada}: Udana inicjalizacja, przypisano kurs_id: {rozklad_id}")

            pojazd['poprzedni_przystanek'] = przystanek_A
            pojazd['nastpeny_przystanek'] = przystanek_B

            return 0

        elif pojazd["stan"] == "W_TRASIE":
            przystanek_A, przystanek_B = pojazd['poprzedni_przystanek'], pojazd['nastpeny_przystanek']
            if not przystanek_A or not przystanek_B:
                return 2
            
            lat_a, lon_a = self.przystanki[przystanek_A['przystanek_id']]['lat'], self.przystanki[przystanek_A['przystanek_id']]['lon']
            lat_b, lon_b = self.przystanki[przystanek_B['przystanek_id']]['lat'], self.przystanki[przystanek_B['przystanek_id']]['lon']
            
            if not self._sprawdz_zawartosc_w_odcinku(lat_a, lon_a, lat_b, lon_b, lat, lon):
                przystanek_A, przystanek_B = self._znajdz_miedzy_ktorymi_przystankami_trasy_pojazd(linia, brygada, pojazd['id_kursu'], lat, lon)

                if (not bool(przystanek_A) or not bool(przystanek_B)):
                    nast_kurs_id = pojazd['id_kursu'] + 1
                    while nast_kurs_id < len(self.rozklady[linia][brygada]) and len(self.rozklady[linia][brygada][nast_kurs_id]['przystanki']) < 2:
                        nast_kurs_id += 1
                        
                    if nast_kurs_id < len(self.rozklady[linia][brygada]):
                        czas_startu_nast = self.rozklady[linia][brygada][nast_kurs_id]['czas_startu']
                        if czas_gps >= czas_startu_nast - 300:
                            
                            pA_nast, pB_nast = self._znajdz_miedzy_ktorymi_przystankami_trasy_pojazd(linia, brygada, nast_kurs_id, lat, lon)
                            if bool(pA_nast):
                                pojazd['id_kursu'] = nast_kurs_id
                                pojazd['poprzedni_przystanek'] = pA_nast
                                pojazd['nastpeny_przystanek'] = pB_nast
                                logger.info(f"{linia}/{brygada}: Przeskoczył na kurs {nast_kurs_id} omijając strefę pętli")
                                return 2
                    logger.warning(f"{linia}/{brygada} nie jest między oczekiwanymi przystankami")
                    return 2
            
                pojazd['poprzedni_przystanek'] = przystanek_A
                pojazd['nastpeny_przystanek'] = przystanek_B

            proporcja_przebytej_drogi = self._oblicz_proporcje_przebytej_trasy(przystanek_A, przystanek_B, lat, lon)

            metr1, metr2 = przystanek_A['metr'], przystanek_B['metr']
            przebyty_odcinek = proporcja_przebytej_drogi*(metr2 - metr1)
            obecny_metr_trasy = metr1 + przebyty_odcinek

            # sprawdzenie trendu ruchu, czy zgodny z kierunkiem wybranej trasy i czy jesli sie nie rusza to czy nie jest przypadkiem zawieszony na pętli
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
            return -1 # brak rozkladu
        
        for idx, kurs in kandydaci:
            if len(kurs['przystanki']) > 0:
                id_start = kurs['przystanki'][0]['przystanek_id']
                id_koniec = kurs['przystanki'][-1]['przystanek_id']
                
                lat_s, lon_s = self.przystanki[id_start]['lat'], self.przystanki[id_start]['lon']
                lat_k, lon_k = self.przystanki[id_koniec]['lat'], self.przystanki[id_koniec]['lon']
                
                # jeśli jest w promieniu 200m od startu lub końca potencjalnej trasy to nie rozważamy go
                if utils.oblicz_odleglosc(lat_sz, lon_sz, lat_s, lon_s) < utils.OCZEKIWANA_ODL_OD_KONCA or utils.oblicz_odleglosc(lat_sz, lon_sz, lat_k, lon_k) < utils.OCZEKIWANA_ODL_OD_KONCA:
                    return -2

        if len(kandydaci) == 1:
            return kandydaci[0][0]
        
        przy_petli = None
        for idx, kurs in kandydaci:
            kolejne_id_najblizszych = self._znajdz_trzy_kolejne_najblizsze_przystanki_na_trasie(linia, brygada, idx, lat_sz, lon_sz)

            if len(kolejne_id_najblizszych) == 1:
                przy_petli = idx
                continue

            id_celu = kolejne_id_najblizszych[1]
            lat_celu = self.przystanki[id_celu]['lat']
            lon_celu = self.przystanki[id_celu]['lon']

            pojazd = self.pojazdy[linia][brygada]
            historia = pojazd['historia_gps']

            lat_A, lon_A = historia[0][0], historia[0][1]
            lat_B, lon_B = historia[1][0], historia[1][1]

            odl_A = utils.oblicz_odleglosc(lat_A, lon_A , lat_celu, lon_celu)
            odl_B = utils.oblicz_odleglosc(lat_B, lon_B , lat_celu, lon_celu)

            if odl_A > odl_B:
                return idx
            
            # to nie jest kurs, który za 2 przystanki ma zajezdnie
            if len(kolejne_id_najblizszych) == 3:
                id_celu_2 = kolejne_id_najblizszych[2]
                lat_celu_2 = self.przystanki[id_celu_2]['lat']
                lon_celu_2 = self.przystanki[id_celu_2]['lon']

                odl_A_cel2 = utils.oblicz_odleglosc(lat_A, lon_A, lat_celu_2, lon_celu_2)
                odl_B_cel2 = utils.oblicz_odleglosc(lat_B, lon_B, lat_celu_2, lon_celu_2)

                if odl_A_cel2 > odl_B_cel2:
                    return idx
        
        # zostal ten jeden kurs co dojezdza do zajezdni
        if przy_petli is not None:
            return przy_petli
        
        logging.warning(f"{linia}/{brygada}: żadna trasa nie pasuje do tego pojazdu")
        return -1

    def _znajdz_trzy_kolejne_najblizsze_przystanki_na_trasie(self, linia: str, brygada: str, id_kursu: int, lat_sz: float, lon_sz: float) -> list:
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

    def _znajdz_miedzy_ktorymi_przystankami_trasy_pojazd(self, linia: str, brygada: str, id_kursu: int, lat_sz: float, lon_sz: float) -> tuple[dict, dict]:
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
        
        lat_a, lon_a = self.przystanki[przystanek_A['przystanek_id']]['lat'], self.przystanki[przystanek_A['przystanek_id']]['lon']
        lat_b, lon_b = self.przystanki[przystanek_B['przystanek_id']]['lat'], self.przystanki[przystanek_B['przystanek_id']]['lon']
        
        dC = utils.oblicz_odleglosc(lat_a, lon_a, lat_b, lon_b)
        if dC == 0:
            return 0.0
        
        dA = utils.oblicz_odleglosc(lat_a, lon_a, lat_sz, lon_sz)
        dB = utils.oblicz_odleglosc(lat_b, lon_b, lat_sz, lon_sz)

        proporcja = (dA**2 + dC**2 - dB**2 ) / (2 * dC**2)

        return proporcja
