from shapely.geometry import Point, LineString
from pyproj import Transformer
from src.utils import MAX_ODLEGLOSC_OD_PROSTEJ_TRASY_M

class Kalkulator_Przestrzenny:
    transformer: Transformer

    def __init__(self) -> None:
        self.transformer = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)

    def buduj_trase(self, punkty: list[tuple[float, float]]) -> LineString:
        """ Punkty w formacie (lon, lat) """
        punkty_xy = [self.transformer.transform(pt[0], pt[1]) for pt in punkty]
        linestr = LineString(punkty_xy)
        return linestr

    def lokalizuj_pojazd(self, lat: float, lon: float, linestr_trasy: LineString) -> tuple[float, float] | None:
        x, y = self.transformer.transform(lon, lat)
        pojazd_pkt = Point(x, y)
        odl_od_trasy = linestr_trasy.distance(pojazd_pkt)
        if odl_od_trasy > MAX_ODLEGLOSC_OD_PROSTEJ_TRASY_M:
            return None
        dystans = linestr_trasy.project(pojazd_pkt)
        return (dystans, odl_od_trasy)