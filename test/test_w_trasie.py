import pytest
from pytest import approx
from src.TrackerZTM import TrackerZTM
import json

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

    yield {'tracker': tracker, 'linie': linie}


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
        'nastpeny_przystanek': przystanek_2
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
    
    assert opoznienie == approx(opoznienie_zakladane, abs=1)
    assert metr == approx(oczekiwany_metr, abs=1)

    id_kursu = tracker.pojazdy[linia][TEST_BRYGADA]['id_kursu']
    nazwa_kursu = tracker.rozklady[linia][TEST_BRYGADA][id_kursu]['trasa']
    assert nazwa_trasy == nazwa_kursu

def test_za_nastepnym_przystankiem(setup_dane: dict):
    tracker = setup_dane['tracker']
    linia = setup_dane['linie'][0]
    TEST_BRYGADA = "1"
    
    kurs = tracker.rozklady[linia][TEST_BRYGADA][0]
    przystanek_1 = kurs['przystanki'][1]
    przystanek_2 = kurs['przystanki'][2]
    przystanek_3 = kurs['przystanki'][3]
    
    id_1 = przystanek_1['przystanek_id']
    id_2 = przystanek_2['przystanek_id']
    id_3 = przystanek_3['przystanek_id']
    
    lat_1, lon_1 = tracker.przystanki[id_1]['lat'], tracker.przystanki[id_1]['lon']
    lat_2, lon_2 = tracker.przystanki[id_2]['lat'], tracker.przystanki[id_2]['lon']
    lat_3, lon_3 = tracker.przystanki[id_3]['lat'], tracker.przystanki[id_3]['lon']
    
    tracker.pojazdy[linia][TEST_BRYGADA] = {
        'stan': 'W_TRASIE',
        'historia_gps': [],
        'id_kursu': 0,
        'poprzedni_przystanek': przystanek_1,
        'nastpeny_przystanek': przystanek_2
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
    
    assert opoznienie == approx(opoznienie_zakladane, abs=1)
    assert metr == approx(oczekiwany_metr, abs=1)

    id_kursu = tracker.pojazdy[linia][TEST_BRYGADA]['id_kursu']
    nazwa_kursu = tracker.rozklady[linia][TEST_BRYGADA][id_kursu]['trasa']
    assert nazwa_trasy == nazwa_kursu

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
    id_3 = przystanek_3['przystanek_id']
    
    lat_1, lon_1 = tracker.przystanki[id_1]['lat'], tracker.przystanki[id_1]['lon']
    lat_2, lon_2 = tracker.przystanki[id_2]['lat'], tracker.przystanki[id_2]['lon']
    lat_3, lon_3 = tracker.przystanki[id_3]['lat'], tracker.przystanki[id_3]['lon']
    
    tracker.pojazdy[linia][TEST_BRYGADA] = {
        'stan': 'W_TRASIE',
        'historia_gps': [],
        'id_kursu': 0,
        'poprzedni_przystanek': przystanek_2,
        'nastpeny_przystanek': przystanek_3
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
    
    assert opoznienie == approx(opoznienie_zakladane, abs=1)
    assert metr == approx(oczekiwany_metr, abs=1)

    id_kursu = tracker.pojazdy[linia][TEST_BRYGADA]['id_kursu']
    nazwa_kursu = tracker.rozklady[linia][TEST_BRYGADA][id_kursu]['trasa']
    assert nazwa_trasy == nazwa_kursu

def test_przy_petli(setup_dane: dict):
    tracker = setup_dane['tracker']
    linia = setup_dane['linie'][0]
    TEST_BRYGADA = "1"
    
    kurs = tracker.rozklady[linia][TEST_BRYGADA][0]
    przystanek_1 = kurs['przystanki'][-2]
    przystanek_2 = kurs['przystanki'][-1]
    
    id_1 = przystanek_1['przystanek_id']
    id_2 = przystanek_2['przystanek_id']
    
    lat_1, lon_1 = tracker.przystanki[id_1]['lat'], tracker.przystanki[id_1]['lon']
    lat_2, lon_2 = tracker.przystanki[id_2]['lat'], tracker.przystanki[id_2]['lon']
    
    tracker.pojazdy[linia][TEST_BRYGADA] = {
        'stan': 'W_TRASIE',
        'historia_gps': [],
        'id_kursu': 0,
        'poprzedni_przystanek': przystanek_1,
        'nastpeny_przystanek': przystanek_2
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
    
    assert opoznienie == approx(opoznienie_zakladane, abs=2)
    assert metr == approx(oczekiwany_metr, abs=10)
    
    assert tracker.pojazdy[linia][TEST_BRYGADA]['stan'] == 'NA_PETLI'
    assert tracker.pojazdy[linia][TEST_BRYGADA]['id_kursu'] == 0

def test_zgubiony_autobus(setup_dane: dict):
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
        'nastpeny_przystanek': przystanek_2
    }

    # autobus gdzieś niewiadomo gdzie totalnie 1 stopień lat i lon gdzie indziej (ok. 71km)
    lat_awaria = tracker.przystanki[przystanek_1['przystanek_id']]['lat'] + 1.0
    lon_awaria = tracker.przystanki[przystanek_1['przystanek_id']]['lon'] + 1.0
    
    czas_gps = przystanek_1['czas'] + 60

    wynik = tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat_awaria, lon_awaria, czas_gps)
    
    assert wynik == 2
    assert tracker.pojazdy[linia][TEST_BRYGADA]['poprzedni_przystanek'] == przystanek_1