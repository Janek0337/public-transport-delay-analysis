import pytest
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
    TEST_ID_KURSU = 0
    CZAS_OBECNY = 31290
    mock_przystanek1 = tracker.rozklady[linia][TEST_BRYGADA][TEST_ID_KURSU]['przystanki'][2]
    mock_przystanek2 = tracker.rozklady[linia][TEST_BRYGADA][TEST_ID_KURSU]['przystanki'][3]

    mock_przystanek1_id = mock_przystanek1['przystanek_id']
    mock_przystanek1_lat = tracker.przystanki[mock_przystanek1_id]['lat']
    mock_przystanek1_lon = tracker.przystanki[mock_przystanek1_id]['lon']

    mock_przystanek2_id = mock_przystanek2['przystanek_id']
    mock_przystanek2_lat = tracker.przystanki[mock_przystanek2_id]['lat']
    mock_przystanek2_lon = tracker.przystanki[mock_przystanek2_id]['lon']

    diff = (mock_przystanek2_lat - mock_przystanek1_lat) * 0.3

    wynik1 = tracker.przetworz_pozycje(linia, TEST_BRYGADA, mock_przystanek1_lat + diff, mock_przystanek1_lon, CZAS_OBECNY)
    assert(wynik1 == 2) # pierwszy pomiar nie powinien wniosków wyciągać

    diff2 = (mock_przystanek2_lat - mock_przystanek1_lat + 0.0001) * 0.3
    CZAS_OBECNY += 100
    wynik2 = tracker.przetworz_pozycje(linia, TEST_BRYGADA, mock_przystanek1_lat + diff2, mock_przystanek1_lon, CZAS_OBECNY)
    assert(wynik2 == 2) # pomiar z minimalnym poruszeniem, dryf GPS

    diff3 = (mock_przystanek2_lat - mock_przystanek1_lat) * 0.6
    diff3_lon = (mock_przystanek2_lon - mock_przystanek1_lon) * 0.6
    CZAS_OBECNY += 100
    wynik3 = tracker.przetworz_pozycje(linia, TEST_BRYGADA, mock_przystanek1_lat + diff3, mock_przystanek1_lon + diff3_lon, CZAS_OBECNY)
    assert(wynik3 == 0)
    stan = tracker.pojazdy[linia][TEST_BRYGADA]
    assert(stan['stan'] == 'W_TRASIE')
    assert(stan['id_kursu'] == TEST_ID_KURSU)

def test_ogromne_opoznienie(setup_dane: dict):
    tracker = setup_dane['tracker']
    linia = setup_dane['linie'][0]
    TEST_BRYGADA = "1"
    TEST_ID_KURSU = 0
    CZAS_OBECNY = 32450
    mock_przystanek1 = tracker.rozklady[linia][TEST_BRYGADA][TEST_ID_KURSU]['przystanki'][3]
    mock_przystanek2 = tracker.rozklady[linia][TEST_BRYGADA][TEST_ID_KURSU]['przystanki'][4]

    mock_przystanek1_id = mock_przystanek1['przystanek_id']
    mock_przystanek1_lat = tracker.przystanki[mock_przystanek1_id]['lat']
    mock_przystanek1_lon = tracker.przystanki[mock_przystanek1_id]['lon']

    mock_przystanek2_id = mock_przystanek2['przystanek_id']
    mock_przystanek2_lat = tracker.przystanki[mock_przystanek2_id]['lat']
    mock_przystanek2_lon = tracker.przystanki[mock_przystanek2_id]['lon']

    diff = (mock_przystanek2_lat - mock_przystanek1_lat) * 0.3

    wynik1 = tracker.przetworz_pozycje(linia, TEST_BRYGADA, mock_przystanek1_lat + diff, mock_przystanek1_lon, CZAS_OBECNY)
    assert(wynik1 == 2) # pierwszy pomiar nie powinien wniosków wyciągać

    diff3 = (mock_przystanek2_lat - mock_przystanek1_lat) * 0.6
    diff3_lon = (mock_przystanek2_lon - mock_przystanek1_lon) * 0.6
    CZAS_OBECNY += 100
    wynik3 = tracker.przetworz_pozycje(linia, TEST_BRYGADA, mock_przystanek1_lat + diff3, mock_przystanek1_lon + diff3_lon, CZAS_OBECNY)
    assert(wynik3 == 0)
    stan = tracker.pojazdy[linia][TEST_BRYGADA]
    assert(stan['stan'] == 'W_TRASIE')
    assert(stan['id_kursu'] == TEST_ID_KURSU)

def test_zjazd_na_petle(setup_dane: dict):
    tracker = setup_dane['tracker']
    linia = setup_dane['linie'][0]
    TEST_BRYGADA = "1"
    CZAS_OBECNY = 31600 # Zbliża się do końca kursu 0 (koniec 31620)
    
    przedostatni = tracker.rozklady[linia][TEST_BRYGADA][0]['przystanki'][3]
    ostatni = tracker.rozklady[linia][TEST_BRYGADA][0]['przystanki'][4]
    
    lat_p, lon_p = tracker.przystanki[przedostatni['przystanek_id']]['lat'], tracker.przystanki[przedostatni['przystanek_id']]['lon']
    lat_o, lon_o = tracker.przystanki[ostatni['przystanek_id']]['lat'], tracker.przystanki[ostatni['przystanek_id']]['lon']

    tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat_p + 0.0001, lon_p, CZAS_OBECNY)
    wynik = tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat_p + (lat_o - lat_p)*0.8, lon_p + (lon_o - lon_p)*0.8, CZAS_OBECNY + 30)
    
    assert wynik == 0
    assert tracker.pojazdy[linia][TEST_BRYGADA]['id_kursu'] == 0

def test_autobus_jedzie_szybko(setup_dane: dict):
    tracker = setup_dane['tracker']
    linia = setup_dane['linie'][0]
    TEST_BRYGADA = "1"
    CZAS_OBECNY = 31300
    
    przystanek1 = tracker.rozklady[linia][TEST_BRYGADA][0]['przystanki'][1]
    przystanek2 = tracker.rozklady[linia][TEST_BRYGADA][0]['przystanki'][2]
    
    lat_1, lon_1 = tracker.przystanki[przystanek1['przystanek_id']]['lat'], tracker.przystanki[przystanek1['przystanek_id']]['lon']
    lat_2, lon_2 = tracker.przystanki[przystanek2['przystanek_id']]['lat'], tracker.przystanki[przystanek2['przystanek_id']]['lon']

    # PING 1: Tuż przed przystankiem 1
    tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat_1 - 0.0005, lon_1, CZAS_OBECNY)
    
    # PING 2: za przystanek 1, mocno w stronę przystanku 2
    # Dystans do przystanku 1 teraz rośnie, ale do 2 maleje.
    wynik = tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat_1 + (lat_2 - lat_1)*0.5, lon_1 + (lon_2 - lon_1)*0.5, CZAS_OBECNY + 30)
    
    assert wynik == 0
    assert tracker.pojazdy[linia][TEST_BRYGADA]['stan'] == 'W_TRASIE'

def test_pojazd_widmo_zly_czas(setup_dane: dict):
    tracker = setup_dane['tracker']
    linia = setup_dane['linie'][0]
    TEST_BRYGADA = "1"
    
    # godzina 3 w nocy, nic nie jeździ
    CZAS_OBECNY = 10800 
    
    lat, lon = 52.251688, 20.912509
    
    tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat, lon, CZAS_OBECNY)
    wynik = tracker.przetworz_pozycje(linia, TEST_BRYGADA, lat + 0.01, lon + 0.01, CZAS_OBECNY + 30)
    
    assert wynik == 1 
    assert tracker.pojazdy[linia][TEST_BRYGADA]['stan'] == 'INICJALIZACJA'