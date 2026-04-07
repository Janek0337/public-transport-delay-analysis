import logging
from src.logger_setup import setup_logger
from dotenv import load_dotenv, find_dotenv
import os
import src.kolektor_danych as kolektor_danych
from src.TrackerZTM import TrackerZTM
import time

def main():

    logger = logging.getLogger(__name__)
    setup_logger(True)

    logger.info("Start")

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
    linie = ['523']
    for linia in linie:
        kolektor_danych.stworz_trase_linii(API_KEY, linia)
        kolektor_danych.stworz_rozklad_linii(API_KEY, linia)

    tracker = TrackerZTM(linie)
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
            wynik_przetwarzania = tracker.przetworz_pozycje(linia, brygada, lat, lon, czas_gps)
            if isinstance(wynik_przetwarzania, int):
                if wynik_przetwarzania == 2:
                    #logging.info(f"Pojazd {linia}/{brygada} oczekuje na dalsze pomiary...")
                    continue
                if wynik_przetwarzania == 1:
                    #logging.warning(f"Problem ze znalezieniem pojazdu {linia}/{brygada}")
                    continue
            
            if isinstance(wynik_przetwarzania, tuple):
                opoznienie, metr, nazwa_trasy = wynik_przetwarzania
                znak = "+" if opoznienie >= 0 else "-"
                abs_opoznienie = abs(int(opoznienie))
                minuty, sekundy = divmod(abs_opoznienie, 60)

                logging.info(f"Pojazd {linia}/{brygada} | Trasa: {nazwa_trasy} | Metr: {metr}m | Status: {znak}{minuty}m {sekundy}s")

        time.sleep(max(0, 16 - (time.time() - czas_start)))

    logger.info("Finished")

if __name__ == "__main__":
    main()