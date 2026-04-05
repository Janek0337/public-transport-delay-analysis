from typing import TypedDict, Optional, Tuple, List
from src import utils
import json
import logging

logger = logging.getLogger(__name__)

GpsPoint = Tuple[float, float, int] # lat, lon, czas_s
class StanPojazdu(TypedDict):
    stan: str
    historia_gps: List[GpsPoint]
    id_kursu: Optional[int]
    nastpeny_przystanek: dict | None
    poprzedni_przystanek: dict | None

BrygadaInfo = dict[str, StanPojazdu] # numer_brygady: StanPojazdu
LinieInfo = dict[str, BrygadaInfo] # numer_linii: BrygadaInfo

def stworz_nowy_stan(lat: float, lon: float, czas: int) -> StanPojazdu:
    return {
        'stan': 'INICJALIZACJA',
        'historia_gps': [(lat, lon, czas)],
        'id_kursu': None,
        'nastpeny_przystanek': None,
        'poprzedni_przystanek': None
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
        0 - sukces
        1 - nie ma takiego pojazdu w rozkladzie
        2 - kalibracja, czekaj
        """

        # to nie jest poprawna wartość brygady dla tej linii
        if brygada not in self.rozklady[linia]:
            return 1

        # to jest nieznany jeszcze autobus (niezainicjowany)
        if brygada not in self.pojazdy[linia]:
            self.pojazdy[linia][brygada] = stworz_nowy_stan(lat, lon, czas_gps)
            return 2 # przerywamy i czekamy na kolejne pingi

        pojazd = self.pojazdy[linia][brygada]

        if pojazd["stan"] == "INICJALIZACJA":

            # jesli pojazd nie ruszyl sie znaczoco to czekamy az sie ruszy
            if not utils.czy_pojazd_sie_ruszyl(pojazd['historia_gps'][0][0], pojazd['historia_gps'][0][1], lat, lon):
                return 2
            
            # dodajemy nowy punkt do historii (to jest drugi punkt)
            pojazd["historia_gps"].append((lat, lon, czas_gps))
            
            rozklad_id = self._znajdz_rozklad(czas_gps, linia, brygada, lat, lon)
            if rozklad_id == -1:
                return 1
            
            pojazd['id_kursu'] = rozklad_id
            pojazd['stan'] = 'W_TRASIE'
            pojazd['historia_gps'] = []
            logger.info(f"Linia {linia}, brygada {brygada}: kurs_id: {rozklad_id}")

            przystanek_A, przystanek_B = self._znajdz_miedzy_ktorymi_przystankami_trasy_pojazd(linia, brygada, pojazd['id_kursu'], lat, lon)
            pojazd['poprzedni_przystanek'] = przystanek_A
            pojazd['nastpeny_przystanek'] = przystanek_B

            return 0

        elif pojazd["stan"] == "W_TRASIE":
            przystanek_A, przystanek_B = pojazd['poprzedni_przystanek'], pojazd['nastpeny_przystanek']
            if przystanek_A is None or przystanek_B is None:
                return 2
            
            lat_a, lon_a = self.przystanki[przystanek_A['przystanek_id']]['lat'], self.przystanki[przystanek_A['przystanek_id']]['lon']
            lat_b, lon_b = self.przystanki[przystanek_B['przystanek_id']]['lat'], self.przystanki[przystanek_B['przystanek_id']]['lon']
            
            if not self._sprawdz_zawartosc_w_odcinku(lat_a, lon_a, lat_b, lon_b, lat, lon):
                przystanek_A, przystanek_B = self._znajdz_miedzy_ktorymi_przystankami_trasy_pojazd(linia, brygada, pojazd['id_kursu'], lat, lon)
                pojazd['poprzedni_przystanek'] = przystanek_A
                pojazd['nastpeny_przystanek'] = przystanek_B

            proporcja_przebytej_drogi = self._oblicz_proporcje_przebytej_trasy(przystanek_A, przystanek_B, lat, lon)

            metr1, metr2 = przystanek_A['metr'], przystanek_B['metr']
            przebyty_odcinek = proporcja_przebytej_drogi*(metr2 - metr1)
            obecny_metr_trasy = metr1 + przebyty_odcinek

            czas1, czas2 = przystanek_A['czas'], przystanek_B['czas']
            czas_oczekiwany_rozkladowy = czas1 + proporcja_przebytej_drogi*(czas2 - czas1)
            opoznienie = czas_gps - czas_oczekiwany_rozkladowy

            # sprawdzamy czy nie jest już na pętli
            id_kursu = pojazd['id_kursu']
            czas_ostatniego_przystanku = self.rozklady[linia][brygada][id_kursu]['czas_konca']
            if przystanek_B['czas'] == czas_ostatniego_przystanku:
                if utils.oblicz_odleglosc(lat_b, lon_b, lat, lon) < utils.DOKLADNOSC_GPS_M:
                    pojazd['stan'] = "NA_PETLI"
                    logger.info(f"Linia {linia}/{brygada}: Zjazd na pętlę. Zakończono kurs {id_kursu}.")
            
            return (obecny_metr_trasy, opoznienie)

        elif pojazd["stan"] == "NA_PETLI":
            nowy_kurs_id = pojazd['id_kursu'] + 1 
            
            if nowy_kurs_id >= len(self.rozklady[linia][brygada]):
                return 0 
                
            czas_poczatku_nastpenej_trasy = self.rozklady[linia][brygada][nowy_kurs_id]['czas_startu']
            
            if czas_gps >= czas_poczatku_nastpenej_trasy:
                pojazd['stan'] = 'W_TRASIE'
                pojazd['id_kursu'] = nowy_kurs_id
                pojazd['poprzedni_przystanek'] = self.rozklady[linia][brygada][nowy_kurs_id]['przystanki'][0]
                pojazd['nastpeny_przystanek'] = self.rozklady[linia][brygada][nowy_kurs_id]['przystanki'][1]
                logger.info(f"Linia {linia}/{brygada}: Rusza w nowy kurs {nowy_kurs_id}.")
                return 0
            
            return 0

    def _znajdz_rozklad(self, czas_teraz: int, linia: str, brygada: str, lat_sz: float, lon_sz: float) -> int:

        okno_w_przod = utils.czas_na_sekundy('01:00:00')
        okno_w_tyl = utils.czas_na_sekundy('00:10:00')

        kandydaci = []
        for kurs in self.rozklady[linia][brygada]:
            if (czas_teraz >= kurs['czas_startu'] - okno_w_tyl 
            and czas_teraz <= kurs['czas_konca'] + okno_w_przod):
                kandydaci.append(kurs)

        if len(kandydaci) == 0:
            return -1 # BRAK TAKIEGO ROZKŁADU
        elif len(kandydaci) == 1:
            return kandydaci[0]['id_kursu']
        
        # jeśli jest > 1 kurs (zazwyczaj 2)
        przy_petli = None
        for kurs in kandydaci:
            przystanki = kurs['przystanki']
            
            # ten kurs jest z/do zajezdni
            if len(przystanki) < 2:
                continue

            kolejne_id_najblizszych = self._znajdz_trzy_kolejne_najblizsze_przystanki_na_trasie(linia, brygada, kurs['id_kursu'], lat_sz, lon_sz)

            # najblizszy przystanek jest ostatni, najwyzej zostanie na koncu jak do zadnego innego kursu nie bedzie pasowac
            if len(kolejne_id_najblizszych) == 1:
                przy_petli = kurs
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
                return kurs['id_kursu']
            
            # to nie jest kurs, który za 2 przystanki ma zajezdnie
            if len(kolejne_id_najblizszych) == 3:
                id_celu_2 = kolejne_id_najblizszych[2]
                lat_celu_2 = self.przystanki[id_celu_2]['lat']
                lon_celu_2 = self.przystanki[id_celu_2]['lon']

                odl_A_cel2 = utils.oblicz_odleglosc(lat_A, lon_A, lat_celu_2, lon_celu_2)
                odl_B_cel2 = utils.oblicz_odleglosc(lat_B, lon_B, lat_celu_2, lon_celu_2)

                if odl_A_cel2 > odl_B_cel2:
                    return kurs['id_kursu']
        
        # zostal ten jeden kurs co dojezdza do zajezdni
        if przy_petli is not None:
            return przy_petli['id_kursu']
        
        logging.warning(f"Żadna trasa nie pasuje do tego, co robi ten autobus!\nLinia: {linia}, Brygada: {brygada}")
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

        nr_kolejnosci_najblizszego = najblizszy_przystanek['nr_kolejnosci']

        if nr_kolejnosci_najblizszego + 1 < len(lista_przystankow_kursu):
            przystanek_2_id = lista_przystankow_kursu[nr_kolejnosci_najblizszego + 1]['przystanek_id']
            id_przystankow.append(przystanek_2_id)
            if nr_kolejnosci_najblizszego + 2 < len(lista_przystankow_kursu):
                przystanek_3_id = lista_przystankow_kursu[nr_kolejnosci_najblizszego + 2]['przystanek_id']
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
                
        logging.info(f"Linia {linia}, brygada {brygada}: nie znaleziono przypasowania okna.")
        return ("-1", "-1")
                
    def _sprawdz_zawartosc_w_odcinku(self, lat_a: float, lon_a: float, lat_b: float, lon_b:  float, lat_c: float, lon_c: float) -> bool:
        BUFOR_ROZNICY_M = 100
        dA = utils.oblicz_odleglosc(lat_c, lon_c, lat_a, lon_a)
        dB = utils.oblicz_odleglosc(lat_c, lon_c, lat_b, lon_b)
        dC = utils.oblicz_odleglosc(lat_b, lon_b, lat_a, lon_a)

        return dA + dB <= dC + BUFOR_ROZNICY_M
    
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
