import os
import datetime
from contextlib import contextmanager

import mock
from nose.tools import (assert_is_not_none, assert_equal,
                        assert_true, assert_false)

from skylines import model
from skylines.lib import achievements, files
from skylines.lib.xcsoar_ import analysis


HERE = os.path.dirname(__file__)
DATADIR = os.path.join(HERE, '..', 'data')


def test_get_achievement():
    a = achievements.get_achievement('triangle-50')
    assert_is_not_none(a)
    assert_equal(repr(a),
                 "<Achievement triangle-50: 'Triangle of more than 50 km'>")


def test_triangle_achievement():
    a = achievements.TriangleAchievement('test', distance=100)

    assert_equal(a.title, 'Triangle of more than 100 km')

    assert_true(a.is_achieved(mock.Mock(triangle_distance=120)))
    assert_true(a.is_achieved(mock.Mock(triangle_distance=100)))
    assert_false(a.is_achieved(mock.Mock(triangle_distance=90)))


def test_duration_achievement():
    a = achievements.DurationAchievement('test', duration=3)

    assert_equal(a.title, 'Flight duration of more than 3 h')

    assert_true(a.is_achieved(mock.Mock(duration=4)))
    assert_true(a.is_achieved(mock.Mock(duration=3)))
    assert_false(a.is_achieved(mock.Mock(duration=2.5)))


def test_get_flight_achievements_inprominent():
    hours = lambda h: datetime.timedelta(0, h * 60 * 60)
    flight = mock.Mock(olc_triangle_distance=10000,
                       duration=hours(2.6))
    achieved = achievements.get_flight_achievements(flight)
    assert_equal(len(achieved), 0)


class TestFlightAchievementsDataCollector(object):
    def test_duration(self):
        c = achievements.FlightAchievementDataCollector(self.flight_100km)
        assert_equal(c.duration, 3.39)

    def test_triangle_distance(self):
        c = achievements.FlightAchievementDataCollector(self.flight_100km)
        assert_equal(c.triangle_distance, 57)

    def test_final_glide_distance(self):
        c = achievements.FlightAchievementDataCollector(self.flight_100km)
        assert_equal(c.final_glide_distance, 36)

    @classmethod
    @contextmanager
    def mock_db(cls):
        def airport_by_location(loc, *args, **kw):
            L = model.Location
            LOCS = [(L(54.47745, 24.991717), model.Airport(name="Paluknys"))]

            for aploc, airport in LOCS:
                if loc.geographic_distance(aploc) < 1000:  # what units is this?
                    return airport

            return None

        def timezone_by_location(loc):
            pass

        airport_patch = mock.patch("skylines.model.Airport.by_location",
                                   side_effect=airport_by_location)
        tz_patch = mock.patch("skylines.model.TimeZone.by_location",
                              side_effect=timezone_by_location)

        deltrace_patch = mock.patch.object(analysis, "delete_trace")
        delphase_patch = mock.patch("skylines.model.Flight.delete_phases")

        with airport_patch, tz_patch, deltrace_patch, delphase_patch:
            yield

    @classmethod
    @contextmanager
    def mock_flask_config(cls):
        app_mock = mock.Mock()
        app_mock.config = {"SKYLINES_FILES_PATH": DATADIR}
        f_patch = mock.patch.object(files, "current_app", app_mock)
        a_patch = mock.patch.object(analysis, "current_app", app_mock)
        with f_patch, a_patch:
            yield

    @classmethod
    def create_flight(cls, igcfile):
        igc = model.IGCFile(filename=igcfile,
                            md5=str(hash(igcfile)),
                            # owner=cls.pilot,
                            date_utc=datetime.datetime(2013, 7, 7, 13, 0))
        flight = model.Flight()
        flight.igc_file = igc

        with cls.mock_flask_config(), cls.mock_db():
            success = analysis.analyse_flight(flight, full=2048,
                                              triangle=6144, sprint=512)
            assert_true(success, "IGC file analysis failed")

        return flight

    @classmethod
    def setUpClass(cls):
        try:
            # Load several igc files for analysis
            cls.flight_100km = cls.create_flight("100km.igc")
        finally:
            # Drop anything added to session (we don't use real db for these
            # tests)
            model.db.session.rollback()

    @classmethod
    def tearDownClass(cls):
        mock.patch.stopall()
