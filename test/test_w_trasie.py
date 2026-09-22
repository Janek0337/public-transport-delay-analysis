import json
import pandas as pd
import pytest
from pytest import approx

from src.TrackerZTM import TrackerZTM
from src.kalkulator_przestrzenny import Kalkulator_Przestrzenny
from src import utils


@pytest.fixture(scope="function", autouse=True)
def setup_dane():
    linie = ["523"]
    tracker = TrackerZTM(linie)
    
    with open('test/mock_rozklad.json', 'r') as f:
        jsonik = json.load(f)
        mock_brygady = jsonik['brygady']
        mock_rozklad = {linie[0]: mock_brygady}
        tracker.rozklady = mock_rozklad
    
    with open('test/mock_przystanki.json', 'r') as f:
        jsonik = json.load(f)
        tracker.przystanki = jsonik

    with open('test/mock_mapowanie.json', 'r') as f:
        mapowanie_testowe = json.load(f)

    tracker.kalkulator = Kalkulator_Przestrzenny()
    tracker.warianty_shapes = {
        linie[0]: {
            trasa: {"shape_id": shape_id} for trasa, shape_id in mapowanie_testowe.items()
        }
    }

    shapes_df = pd.read_csv('test/mock_shapes.txt')
    shapes_df.sort_values(by=['shape_id', 'shape_pt_sequence'], inplace=True)
    
    tracker.geometrie_tras = {}
    for shape_id, grupa in shapes_df.groupby('shape_id'):
        punkty = list(zip(grupa['shape_pt_lon'], grupa['shape_pt_lat']))
        tracker.geometrie_tras[shape_id] = tracker.kalkulator.buduj_trase(punkty)

    yield {'tracker': tracker, 'linie': linie, 'mapowanie': mapowanie_testowe}


@pytest.fixture(scope="function", autouse=True)
def zamroz_stale(monkeypatch):
    monkeypatch.setattr(utils, 'OCZEKIWANA_ODL_OD_KONCA', 100)
    monkeypatch.setattr(utils, 'MAX_ODLEGLOSC_OD_PROSTEJ_TRASY_M', 50)
    monkeypatch.setattr(utils, 'DOKLADNOSC_GPS_M', 30)


def test_normalna_jazda(setup_dane: dict):
    tracker = setup_dane['tracker']
    linia = setup_dane['linie'][0]
    TEST_BRYGADA = "1"
    
    kurs = tracker.rozklady[linia][TEST_BRYGADA][0]
    przystanek_1 = kurs['przystanki'][1]
    przystanek_2 = kurs['przystanki'][2]
    
    id_1 = przystanek_1['przystanek_id']
    id_2 = przystanek_2['przystanek_id']
    
    lat_1, lon_1 = tracker.przystanki[id_1]['lat'], tracker.przystanki[id_1]['lon']
    lat_2, lon_2 = tracker.przystanki[id_2]['lat'], tracker.przystanki[id_2]['lon']
    
    tracker.pojazdy[linia][TEST_BRYGADA] = {
        'stan': 'W_TRASIE',
        'historia_gps': [],
        'id_kursu': 0,
        'poprzedni_przystanek': przystanek_1,
        'nastpeny_przystanek': przystanek_2,
        'ostatnie_metry': [],
        'ostatni_czas_zapisu': 600,
        'shape_id': setup_dane['mapowanie']['TP-OLS']
    }

    lat_polowa = (lat_1 + lat_2) / 2.0
    lon_polowa = (lon_1 + lon_2) / 2.0
    
    czas_startu = przystanek_1['czas']
    opoznienie_zakladane = 20
    roznica_czasu_odcinka = przystanek_2['czas'] - przystanek_1['czas']
    czas_w_polowie = czas_startu + (roznica_czasu_odcinka / 2.0)
    czas_gps = czas_w_polowie + opoznienie_zakladane
    
    oczekiwany_metr = (przystanek_1['metr'] + przystanek_2['metr']) / 2.0

    wynik = tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat_polowa, lon_polowa, czas_gps)
    assert isinstance(wynik, tuple)
    
    opoznienie, metr, nazwa_trasy = wynik
    
    assert opoznienie == approx(opoznienie_zakladane, abs=6)
    assert metr == approx(oczekiwany_metr, abs=30)


def test_za_nastepnym_przystankiem(setup_dane: dict):
    tracker = setup_dane['tracker']
    linia = setup_dane['linie'][0]
    TEST_BRYGADA = "1"
    
    kurs = tracker.rozklady[linia][TEST_BRYGADA][0]
    przystanek_1 = kurs['przystanki'][1]
    przystanek_2 = kurs['przystanki'][2]
    przystanek_3 = kurs['przystanki'][3]
    
    id_2 = przystanek_2['przystanek_id']
    id_3 = przystanek_3['przystanek_id']
    
    lat_2, lon_2 = tracker.przystanki[id_2]['lat'], tracker.przystanki[id_2]['lon']
    lat_3, lon_3 = tracker.przystanki[id_3]['lat'], tracker.przystanki[id_3]['lon']
    
    tracker.pojazdy[linia][TEST_BRYGADA] = {
        'stan': 'W_TRASIE',
        'historia_gps': [],
        'id_kursu': 0,
        'poprzedni_przystanek': przystanek_1,
        'nastpeny_przystanek': przystanek_2,
        'ostatnie_metry': [],
        'ostatni_czas_zapisu': 600,
        'shape_id': setup_dane['mapowanie']['TP-OLS']
    }

    lat_polowa = (lat_3 + lat_2) / 2.0
    lon_polowa = (lon_3 + lon_2) / 2.0
    
    czas_startu = przystanek_2['czas']
    opoznienie_zakladane = 20
    roznica_czasu_odcinka = przystanek_3['czas'] - przystanek_2['czas']
    czas_w_polowie = czas_startu + (roznica_czasu_odcinka / 2.0)
    czas_gps = czas_w_polowie + opoznienie_zakladane

    oczekiwany_metr = (przystanek_2['metr'] + przystanek_3['metr']) / 2.0

    wynik = tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat_polowa, lon_polowa, czas_gps)
    assert isinstance(wynik, tuple)
    
    opoznienie, metr, nazwa_trasy = wynik
    assert opoznienie == approx(opoznienie_zakladane, abs=5)
    assert metr == approx(oczekiwany_metr, abs=30)


def test_przed_poprzednim_przystankiem(setup_dane: dict):
    tracker = setup_dane['tracker']
    linia = setup_dane['linie'][0]
    TEST_BRYGADA = "1"
    
    kurs = tracker.rozklady[linia][TEST_BRYGADA][0]
    przystanek_1 = kurs['przystanki'][1]
    przystanek_2 = kurs['przystanki'][2]
    przystanek_3 = kurs['przystanki'][3]
    
    id_1 = przystanek_1['przystanek_id']
    id_2 = przystanek_2['przystanek_id']
    
    lat_1, lon_1 = tracker.przystanki[id_1]['lat'], tracker.przystanki[id_1]['lon']
    lat_2, lon_2 = tracker.przystanki[id_2]['lat'], tracker.przystanki[id_2]['lon']
    
    tracker.pojazdy[linia][TEST_BRYGADA] = {
        'stan': 'W_TRASIE',
        'historia_gps': [],
        'id_kursu': 0,
        'poprzedni_przystanek': przystanek_2,
        'nastpeny_przystanek': przystanek_3,
        'ostatnie_metry': [],
        'ostatni_czas_zapisu': 600,
        'shape_id': setup_dane['mapowanie']['TP-OLS']
    }

    lat_polowa = (lat_1 + lat_2) / 2.0
    lon_polowa = (lon_1 + lon_2) / 2.0
    
    czas_startu = przystanek_1['czas']
    opoznienie_zakladane = 20
    roznica_czasu_odcinka = przystanek_2['czas'] - przystanek_1['czas']
    czas_w_polowie = czas_startu + (roznica_czasu_odcinka / 2.0)
    czas_gps = czas_w_polowie + opoznienie_zakladane

    oczekiwany_metr = (przystanek_1['metr'] + przystanek_2['metr']) / 2.0

    wynik = tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat_polowa, lon_polowa, czas_gps)
    assert isinstance(wynik, tuple)
    
    opoznienie, metr, nazwa_trasy = wynik
    assert opoznienie == approx(opoznienie_zakladane, abs=5)
    assert metr == approx(oczekiwany_metr, abs=30)


def test_przy_petli(setup_dane: dict):
    tracker = setup_dane['tracker']
    linia = setup_dane['linie'][0]
    TEST_BRYGADA = "1"
    
    kurs = tracker.rozklady[linia][TEST_BRYGADA][0]
    przystanek_1 = kurs['przystanki'][-2]
    przystanek_2 = kurs['przystanki'][-1]
    
    id_2 = przystanek_2['przystanek_id']
    lat_2, lon_2 = tracker.przystanki[id_2]['lat'], tracker.przystanki[id_2]['lon']
    
    tracker.pojazdy[linia][TEST_BRYGADA] = {
        'stan': 'W_TRASIE',
        'historia_gps': [],
        'id_kursu': 0,
        'poprzedni_przystanek': przystanek_1,
        'nastpeny_przystanek': przystanek_2,
        'ostatnie_metry': [],
        'ostatni_czas_zapisu': 600,
        'shape_id': setup_dane['mapowanie']['TP-OLS']
    }

    lat_petla = lat_2
    lon_petla = lon_2 + 0.0001
    
    czas_przyjazdu_z_rozkladu = przystanek_2['czas']
    opoznienie_zakladane = 20
    czas_gps = czas_przyjazdu_z_rozkladu + opoznienie_zakladane

    oczekiwany_metr = przystanek_2['metr']

    wynik = tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat_petla, lon_petla, czas_gps)
    
    assert isinstance(wynik, tuple)
    opoznienie, metr, nazwa_trasy = wynik
    
    assert opoznienie == approx(opoznienie_zakladane, abs=5)
    assert metr == approx(oczekiwany_metr, abs=50)
    
    assert tracker.pojazdy[linia][TEST_BRYGADA]['stan'] == 'NA_PETLI'
    assert tracker.pojazdy[linia][TEST_BRYGADA]['id_kursu'] == 0


def test_zgubiony_autobus(setup_dane: dict):
    tracker = setup_dane['tracker']
    linia = setup_dane['linie'][0]
    TEST_BRYGADA = "1"
    
    kurs = tracker.rozklady[linia][TEST_BRYGADA][0]
    przystanek_1 = kurs['przystanki'][1]
    
    tracker.pojazdy[linia][TEST_BRYGADA] = {
        'stan': 'W_TRASIE',
        'historia_gps': [],
        'id_kursu': 0,
        'poprzedni_przystanek': przystanek_1,
        'nastpeny_przystanek': kurs['przystanki'][2],
        'ostatnie_metry': [],
        'ostatni_czas_zapisu': 600,
        'shape_id': setup_dane['mapowanie']['TP-OLS']
    }

    lat_awaria = tracker.przystanki[przystanek_1['przystanek_id']]['lat'] + 1.0
    lon_awaria = tracker.przystanki[przystanek_1['przystanek_id']]['lon'] + 1.0
    czas_gps = przystanek_1['czas'] + 60

    wynik = tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat_awaria, lon_awaria, czas_gps)
    
    assert wynik == 2
    assert tracker.pojazdy[linia][TEST_BRYGADA]['poprzedni_przystanek'] == przystanek_1


def test_autobus_jedzie_w_zla_strone(setup_dane: dict):
    tracker = setup_dane['tracker']
    linia = setup_dane['linie'][0]
    TEST_BRYGADA = "1"
    
    kurs = tracker.rozklady[linia][TEST_BRYGADA][0]
    przystanek_1 = kurs['przystanki'][1]
    przystanek_2 = kurs['przystanki'][2]
    
    tracker.pojazdy[linia][TEST_BRYGADA] = {
        'stan': 'W_TRASIE',
        'historia_gps': [],
        'id_kursu': 0,
        'poprzedni_przystanek': przystanek_1,
        'nastpeny_przystanek': przystanek_2,
        'ostatnie_metry': [],
        'ostatni_czas_zapisu': 600,
        'shape_id': setup_dane['mapowanie']['TP-OLS']
    }

    lat1 = tracker.przystanki[przystanek_1['przystanek_id']]['lat']
    lon1 = tracker.przystanki[przystanek_1['przystanek_id']]['lon']

    lat3 = tracker.przystanki[przystanek_2['przystanek_id']]['lat']
    lon3 = tracker.przystanki[przystanek_2['przystanek_id']]['lon']

    lat2 = (lat1 + lat3) / 2.0
    lon2 = (lon1 + lon3) / 2.0

    czas_gps = przystanek_1['czas'] + 60
    wynik = tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat3, lon3, czas_gps)
    assert tracker.pojazdy[linia][TEST_BRYGADA]['stan'] == 'W_TRASIE'

    czas_gps = przystanek_1['czas'] + 70
    wynik = tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat2, lon2, czas_gps)
    assert tracker.pojazdy[linia][TEST_BRYGADA]['stan'] == 'W_TRASIE'

    czas_gps = przystanek_1['czas'] + 80
    wynik = tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat1, lon1, czas_gps)
    
    assert wynik == 2
    assert tracker.pojazdy[linia][TEST_BRYGADA]['stan'] == 'INICJALIZACJA'