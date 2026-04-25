import csv
import logging
import os
import time
from datetime import datetime

from dotenv import find_dotenv, load_dotenv

import src.kolektor_danych as kolektor_danych
import src.utils as utils
from src.logger_setup import setup_logger
from src.TrackerZTM import TrackerZTM
from src.utils import OUTPUT_DIR
from src.WeatherTracker import WeatherTracker


def main():
    logger = logging.getLogger(__name__)
    setup_logger(True)
    logger.info("===== Rozpoczęcie pomiarów =====")

    dotenv_path = find_dotenv()
    load_dotenv(dotenv_path)
    API_KEY = os.getenv('API_KEY')
    if API_KEY is None:
        logging.error("Nie znaleziono klucza api w pliku .env")
        exit(1)
    if API_KEY == "":
        logging.error("Klucz api w pliku .env jets pusty")
        exit(1)

    kolektor_danych.stworz_baze_polozen_przystankow(API_KEY)
    linie = ['114', '116', '135', '138', '148', '157', '158', '185', '187', '189', '500', '504', '509', '517', '523']
    for linia in linie:
        kolektor_danych.stworz_trase_linii(API_KEY, linia)
        kolektor_danych.stworz_rozklad_linii(API_KEY, linia)

    tracker = TrackerZTM(linie)

    punkty_pogodowe = utils.wyznacz_punkty_pomiarowe_pogody(linie)
    pogoda = WeatherTracker(punkty_pogodowe)

    naglowki = [
    'czas_str', 'timestamp', 'linia', 'brygada', 'nazwa_trasy', 'lat', 'lon', 
    'metr', 'opoznienie_str', 'opoznienie', 'temperatura', 
    'czy_dzien', 'opad_deszczu', 'opad_sniegu', 'poryw_wiatru'
    ]

    data_dzisiaj = datetime.today().strftime('%Y-%m-%d')
    nazwa_pliku_wyjsciowego = OUTPUT_DIR / f'{data_dzisiaj}_out.csv'
    plik_istnieje = os.path.isfile(nazwa_pliku_wyjsciowego)
    BUFOR_STANOW = dict()

    with open(nazwa_pliku_wyjsciowego , mode='a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=naglowki, delimiter=';')
        if not plik_istnieje:
            writer.writeheader()
        try:
            while True:
                logging.info("Pobieram dane o położeniu...")
                czas_start = time.time()
                lista_polozen = kolektor_danych.zbierz_obecne_polozenie(API_KEY, linie)
                for pojazd in lista_polozen:
                    linia = pojazd['linia']
                    brygada = pojazd['brygada']
                    lat = pojazd['lat']
                    lon = pojazd['lon']
                    czas_gps = pojazd['czas']
                    czas_str = pojazd['czas_str']
                    oznaczenie_kursu = f'{linia}/{brygada}'
                    wynik_przetwarzania = tracker.przetworz_pozycje(linia, brygada, lat, lon, czas_gps, czas_str)

                    if isinstance(wynik_przetwarzania, tuple):
                        opoznienie, metr, nazwa_trasy = wynik_przetwarzania
                        znak = "+" if opoznienie >= 0 else "-"
                        abs_opoznienie = abs(int(opoznienie))
                        minuty, sekundy = divmod(abs_opoznienie, 60)

                        pogoda_tu = pogoda.pogoda_dla_punktu(lat, lon)
                        rekord = {
                            'czas_str': czas_str,
                            'timestamp': int(time.time()),
                            'linia': linia,
                            'brygada': brygada,
                            'nazwa_trasy': nazwa_trasy,
                            'lat': lat,
                            'lon': lon,
                            'metr': f'{metr:.2f}',
                            'opoznienie_str': f'{znak}{minuty:02d}:{sekundy:02d}',
                            'opoznienie': f'{opoznienie:.0f}',
                            'temperatura': pogoda_tu.temperatura,
                            'czy_dzien': pogoda_tu.czy_dzien,
                            'opad_deszczu': pogoda_tu.opad_deszczu,
                            'opad_sniegu': pogoda_tu.opad_sniegu,
                            'poryw_wiatru': pogoda_tu.poryw_wiatru
                        }
                        logging.info(f"Pojazd {linia}/{brygada} | Trasa: {nazwa_trasy} | Metr: {metr:.2f}m | Status: {znak}{minuty}m {sekundy}s")

                        if oznaczenie_kursu not in BUFOR_STANOW:
                            BUFOR_STANOW[oznaczenie_kursu] = [rekord]
                        else:
                            BUFOR_STANOW[oznaczenie_kursu].append(rekord)
                            if len(BUFOR_STANOW[oznaczenie_kursu]) == 6:
                                writer.writerows(BUFOR_STANOW[oznaczenie_kursu])
                                BUFOR_STANOW[oznaczenie_kursu] = []

                    elif wynik_przetwarzania in (1, 2):
                        # błąd/reinicjalizacja
                        BUFOR_STANOW[oznaczenie_kursu] = []

                    elif wynik_przetwarzania == 0:
                        # koniec kursu
                        if oznaczenie_kursu in BUFOR_STANOW and BUFOR_STANOW[oznaczenie_kursu]:
                            writer.writerows(BUFOR_STANOW[oznaczenie_kursu])
                            BUFOR_STANOW[oznaczenie_kursu] = []
                    
                time.sleep(max(0, 16 - (time.time() - czas_start)))

        except KeyboardInterrupt:
            f.flush()
            for _, rekordy in BUFOR_STANOW.items():
                if rekordy:
                    writer.writerows(rekordy)
            logger.info("===== Zakończenie pomiarów =====")

if __name__ == "__main__":
    main()