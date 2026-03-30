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