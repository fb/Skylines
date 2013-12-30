import os
import datetime

import pytest
import mock
from geoalchemy2.shape import from_shape
from shapely.geometry import LineString

from skylines import model
from skylines.lib import achievements, files
from skylines.lib.xcsoar_ import analysis


HERE = os.path.dirname(__file__)
DATADIR = os.path.join(HERE, '..', 'data')


def test_get_achievement():
    a = achievements.get_achievement('triangle-50')
    assert a is not None
    assert (repr(a) ==
            "<Achievement triangle-50: 'Triangle of more than 50 km'>")


def test_triangle_achievement():
    a = achievements.TriangleAchievement('test', distance=100)

    assert a.title == 'Triangle of more than 100 km'

    assert a.is_achieved(mock.Mock(triangle_distance=120))
    assert a.is_achieved(mock.Mock(triangle_distance=100))
    assert not a.is_achieved(mock.Mock(triangle_distance=90))


def test_duration_achievement():
    a = achievements.DurationAchievement('test', duration=3)

    assert a.title == 'Flight duration of more than 3 h'

    assert a.is_achieved(mock.Mock(duration=4))
    assert a.is_achieved(mock.Mock(duration=3))
    assert not a.is_achieved(mock.Mock(duration=2.5))


def test_get_flight_achievements_inprominent():
    hours = lambda h: datetime.timedelta(0, h * 60 * 60)
    flight = mock.Mock(olc_triangle_distance=10000,
                       olc_classic_distance=10000,
                       duration=hours(2.6),
                       phases=[],
                       igc_file=None)
    achieved = achievements.get_flight_achievements(flight)
    assert len(achieved) == 0


@pytest.mark.usefixtures("db")
class TestFlightMetrics(object):
    def test_duration(self):
        c = achievements.FlightMetrics(self.flight_100km)
        assert c.duration == 3.39

    def test_triangle_distance(self):
        c = achievements.FlightMetrics(self.flight_100km)
        assert c.triangle_distance == 57

    def test_final_glide_distance(self):
        c = achievements.FlightMetrics(self.flight_100km)
        assert c.final_glide_distance == 36

    def test_altitude_gain(self):
        c = achievements.FlightMetrics(self.flight_100km)
        assert c.altitude_gain == 981

    def test_circling_percentage(self):
        c = achievements.FlightMetrics(self.flight_100km)
        assert c.circling_percentage == 30

    def test_time_below_400_m(self):
        with self.level_ground(100):
            c = achievements.FlightMetrics(self.flight_100km)
            assert c.time_below_400_m == 121

    def level_ground(self, elevation):
        # Patch get_elevations_for_flight to return constant ground elevation
        from skylines.lib.xcsoar_ import flight_path

        def get_constant_elevation(flight):
            path = flight_path(flight.igc_file)
            return ((fix.seconds_of_day, elevation) for fix in path)
        return mock.patch.object(achievements, "get_elevations_for_flight",
                                 side_effect=get_constant_elevation)

    @staticmethod
    def mock_db():
        def airport_by_location(loc, *args, **kw):
            L = model.Location
            LOCS = [(L(54.47745, 24.991717), model.Airport(name="Paluknys"))]

            for aploc, airport in LOCS:
                if loc.geographic_distance(aploc) < 1000:  # what units is this?
                    return airport

            return None

        mock.patch("skylines.model.Airport.by_location",
                   side_effect=airport_by_location).start()

    @staticmethod
    def mock_flask_config():
        app_mock = mock.Mock()
        app_mock.config = {"SKYLINES_FILES_PATH": DATADIR}
        mock.patch.object(files, "current_app", app_mock).start()
        mock.patch.object(analysis, "current_app", app_mock).start()

    @staticmethod
    def create_flight(igcfile):
        igc = model.IGCFile(filename=igcfile,
                            md5=str(hash(igcfile)),
                            # owner=cls.pilot,
                            date_utc=datetime.datetime(2013, 7, 7, 13, 0))
        flight = model.Flight()
        flight.igc_file = igc

        success = analysis.analyse_flight(flight, full=2048,
                                          triangle=6144, sprint=512)
        assert success, "IGC file analysis failed"

        return flight

    @classmethod
    @pytest.yield_fixture(scope='class', autouse=True)
    def setup_mocks(cls, db_schema):
        cls.mock_flask_config()
        cls.mock_db()

        cls.flight_100km = cls.create_flight("100km.igc")

        yield

        mock.patch.stopall()


@pytest.mark.usefixtures("db")
class TestPilotMetrics(object):
    def setup(self):
        # Create a pilot
        self.pilot = model.User(first_name='Michael', last_name='Sommer')
        model.db.session.add(self.pilot)

        self.follower = model.User(first_name='Sebastian', last_name='Kawa')
        model.db.session.add(self.follower)

    def create_sample_igc_file(self, fname):
        igc = model.IGCFile(filename=fname,
                            md5=str(hash(fname)),
                            owner=self.pilot,
                            date_utc=datetime.datetime(2013, 12, 31, 13, 0))
        return igc

    def create_sample_flight(self, igc_file):
        flight = model.Flight()
        flight.igc_file = igc_file
        flight.pilot = self.pilot

        flight.timestamps = []

        coordinates = [(0, 0), (1, 1)]
        linestring = LineString(coordinates)
        flight.locations = from_shape(linestring, srid=4326)

        flight.takeoff_time = datetime.datetime(2013, 12, 30, 13, 0)
        flight.landing_time = datetime.datetime(2013, 12, 30, 18, 0)
        flight.date_local = datetime.date(2013, 12, 30)
        return flight

    def test_total_distance_has_flights(self):
        # When user has no flights, distance is 0 (not None)
        c = achievements.PilotMetrics(self.pilot)
        assert c.total_distance == 0

        igc = self.create_sample_igc_file('f1.igc')
        flight = self.create_sample_flight(igc)
        flight.olc_classic_distance = 89999

        model.db.session.add(flight)
        model.db.session.flush()

        c1 = achievements.PilotMetrics(self.pilot)
        assert c1.total_distance == 89.999

        # Make sure users are not getting scores from other pilots
        c2 = achievements.PilotMetrics(self.follower)
        assert c2.total_distance == 0

        # Copilots gets total distance counted too
        flight.co_pilot = self.follower
        model.db.session.flush()

        c3 = achievements.PilotMetrics(self.follower)
        assert c3.total_distance == 89.999
