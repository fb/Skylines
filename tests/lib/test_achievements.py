import datetime

import mock
import nose
from nose.tools import (assert_is_not_none, assert_equal,
                        assert_true, assert_false)

from skylines.lib import achievements


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
