import openmeteo_requests
import requests_cache
from retry_requests import retry
from src.utils import oblicz_odleglosc
import time
import logging

logger = logging.getLogger(__name__)

class StanPogody:
    def __init__(self, lat, lon, temperatura, opad_deszczu, czy_dzien, opad_sniegu, poryw_wiatru):
        self.lat = lat
        self.lon = lon
        self.temperatura = temperatura
        self.opad_deszczu = opad_deszczu
        self.czy_dzien = czy_dzien
        self.opad_sniegu = opad_sniegu
        self.poryw_wiatru = poryw_wiatru

class WeatherTracker:
    def __init__(self, punkty_pomiarowe: list[tuple[float, float]]):
        self.dokladnosc = 1e7
        self.url = "https://api.open-meteo.com/v1/forecast"
        self.stacje_pomiarowe = [(int(x[0]*self.dokladnosc), int(x[1]*self.dokladnosc)) for x in punkty_pomiarowe]
        self.cechy_pogody = ["temperature_2m", "rain", "showers", "is_day", "snowfall", "wind_gusts_10m"]
        self.warunki = self.make_call()
        self.ostatni_update = time.time()
        self.update_co_sekund = 30 * 60
        
    def make_call(self) -> dict[tuple, StanPogody]:
        logger.info(f"Pobieram informacje o pogodzie...")
        cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
        retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
        openmeteo = openmeteo_requests.Client(session = retry_session)

        params = {
            "latitude": [x[0]/self.dokladnosc for x in self.stacje_pomiarowe],
            "longitude": [x[1]/self.dokladnosc for x in self.stacje_pomiarowe],
            "current": self.cechy_pogody,
            "timezone": "Europe/Berlin",
        }
        responses = openmeteo.weather_api(self.url, params=params)

        stany_pogody = dict()
        for _, location in enumerate(responses):
            lat = location.Latitude()
            lon = location.Longitude()
            # The order of variables needs to be the same as requested.
            current = location.Current()
            temperature = current.Variables(0).Value()
            rain = current.Variables(1).Value()
            shower = current.Variables(2).Value()
            is_day = current.Variables(3).Value()
            snowfall = current.Variables(4).Value()
            wind_gust = current.Variables(5).Value()

            stany_pogody[(int(lat*self.dokladnosc), int(lon*self.dokladnosc))] = StanPogody(lat, lon, int(round(temperature)),
                                round(rain + shower, 1), int(round(is_day)), round(snowfall, 1), int(round(wind_gust)))

        return stany_pogody
    
    def pogoda_dla_punktu(self, lat, lon) -> StanPogody:
        obecny_czas = time.time()
        if obecny_czas - self.ostatni_update > self.update_co_sekund:
            self.warunki = self.make_call()
            self.ostatni_update = obecny_czas

        najblizszy_punkt = min(self.warunki,
                                key=lambda punkt: oblicz_odleglosc(lat, lon, punkt[0]/self.dokladnosc, punkt[1]/self.dokladnosc))
        return self.warunki[najblizszy_punkt]