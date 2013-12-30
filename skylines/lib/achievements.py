import itertools
import bisect

from flask.ext.babel import _

from skylines.lib.decorators import reify
from skylines.model.flight import get_elevations_for_flight


class FlightMetrics(object):
    """Collect information useful for detecting achievements.

    """
    def __init__(self, flight):
        self.flight = flight

    @reify
    def distance(self):
        """Flight distance in km
        """
        return (self.flight.olc_classic_distance or 0) / 1000

    @reify
    def triangle_distance(self):
        if not self.flight.olc_triangle_distance:
            return 0
        return (self.flight.olc_triangle_distance or 0) / 1000

    @reify
    def duration(self):
        """Duration in hours"""
        return self.flight.duration.total_seconds() / 3600

    @reify
    def final_glide_distance(self):
        """Final glide distance in km

        Phase of flight is considered a "final glide", if it is followed by
        landing in airfield without gaining height by circling. I.e. it will
        effectively be last phase of the flight, ended by landing on airfield.
        """
        from skylines.model import FlightPhase  # prevent circular imports

        if not self.flight.phases:
            return 0

        if self.flight.landing_airport is None:
            # Did not land on airport - no final glide
            return 0

        lastphase = self.flight.phases[-1]
        if lastphase.phase_type != FlightPhase.PT_CRUISE:
            # Circling after final glide? Final glide was not that final, sorry
            return 0

        return lastphase.distance / 1000  # we don't care about fractions

    @reify
    def altitude_gain(self):
        """Altitude gain in meters

        Altitude gain is a difference between altitude at the end of powered
        flight and maximum altitude achieved.
        """
        if self.flight.takeoff_airport is None:
            # Cannot reliably determine altitude gain if flight was not
            # recorded from takeoff.  We assume that all flight are started at
            # some known airporrt here, what might not be universally true,
            # though. Another approach is to check presence of "powered" phase
            # as first phase. That might not be too reliable though.
            return 0

        start_sod = self._release_time

        fpath = self._flight_path
        if not fpath:
            return 0

        start_idx = bisect.bisect([f.seconds_of_day for f in fpath], start_sod)
        release_alt = fpath[start_idx].altitude
        max_alt = max(f.altitude for f in fpath[start_idx:])

        return max(max_alt - release_alt, 0)

    @reify
    def time_below_400_m(self):
        """Time (in seconds) below 400 m AGL
        """
        TARGET_AGL = 140
        last_ts = None
        time_below_target = 0

        for ts, agl in self._agls:
            if self._release_time and ts < self._release_time:
                # Do not count time before release
                continue

            if last_ts is None:
                # Skip first record - we don't know how long it lasted
                last_ts = ts
                continue

            if agl < TARGET_AGL:
                # We assume pilot spent at `agl` all the time, since the last
                # fix.  Fixes are usually separated by short amount of time
                # (1-5s), so this is acceptable approximation.
                time_below_target += ts - last_ts

            last_ts = ts

        return time_below_target

    @reify
    def circling_percentage(self):
        """Return circling percentage for a flight
        """
        cp = None
        for cp in self.flight.circling_performance:
            if cp.circling_direction == cp.CD_TOTAL:
                break

        if cp is None:
            # No circling were detected
            return 0

        return cp.fraction

    @reify
    def _flight_path(self):
        from skylines.lib.xcsoar_.flightpath import flight_path

        if not self.flight.igc_file:
            return []

        return flight_path(self.flight.igc_file)

    @reify
    def _elevations(self):
        return list(get_elevations_for_flight(self.flight))

    @reify
    def _agls(self):
        """Calculate AGL height for each flight fix

        Return list of pairs: (seconds_after_midnight, agl).  Return only
        points, for which ground elevation is available.
        """
        if not self._flight_path:
            return []

        fpath = iter(self._flight_path)

        # We expect elevation times to be subset of flight path times, so for
        # each elevation point there exist corresponding flight path fix.
        agls = []
        for etime, elev in self._elevations:
            fix = fpath.next()
            while etime != fix.seconds_of_day:
                assert fix.seconds_of_day < etime
                fix = fpath.next()

            agls.append((etime, fix.altitude - elev))

        return agls

    @reify
    def _release_time(self):
        """Find release time (in seconds after midnight)
        """
        # Skip all phases until the last powered one. We will start counting
        # altitude gain after last powered phase.
        free_phase = None
        for ph in reversed(self.flight.phases):
            if ph.phase_type == ph.PT_POWERED:
                break
            free_phase = ph

        if not free_phase:
            return None

        stime = free_phase.start_time
        return stime.hour * 3600 + stime.minute * 60 + stime.second


class PilotMetrics(object):
    """Collect statistics about skylines-related user activity
    """

    def __init__(self, user):
        self.user = user

    @reify
    def tracks_uploaded(self):
        from skylines.model.igcfile import IGCFile
        return IGCFile.query().filter_by(owner=self.user).count()

    @reify
    def users_followed(self):
        from skylines.model.follower import Follower
        return Follower.query().filter_by(source=self.user).count()

    @reify
    def followers_attracted(self):
        from skylines.model.follower import Follower
        return Follower.query().filter_by(destination=self.user).count()

    @reify
    def comments_made(self):
        from skylines.model.flight_comment import FlightComment
        return FlightComment.query().filter_by(user=self.user).count()

    @reify
    def total_distance(self):
        """Total distance in km"""
        from sqlalchemy import func
        from skylines.model.flight import Flight
        from skylines.model import db

        c = db.session.query(func.sum(Flight.olc_classic_distance)) \
            .filter(Flight.pilot == self.user)

        return (c.scalar() or 0) / 1000.0


class Achievement(object):
    def __init__(self, name, **params):
        self.name = name
        self.params = params

    def is_achieved(self, context):
        raise NotImplementedError  # pragma: no cover

    @property
    def title(self):
        raise NotImplementedError  # pragma: no cover

    def __repr__(self):
        return "<Achievement %s: '%s'>" % (self.name, self.title)


class TriangleAchievement(Achievement):
    @property
    def title(self):
        return _("Triangle of more than %(distance)s km", **self.params)

    def is_achieved(self, context):
        return context.triangle_distance >= self.params['distance']


class DurationAchievement(Achievement):
    @property
    def title(self):
        return _("Flight duration of more than %(duration)s h", **self.params)

    def is_achieved(self, context):
        return context.duration >= self.params['duration']


class FinalGlideDistanceAchievement(Achievement):
    @property
    def title(self):
        return _("Final glide of more than %(distance)skm", **self.params)

    def is_achieved(self, context):
        return context.final_glide_distance >= self.params['distance']


class AltitudeGainAchievement(Achievement):
    @property
    def title(self):
        return _("Altitude gain over %(gain)sm", **self.params)

    def is_achieved(self, context):
        return context.altitude_gain >= self.params['gain']


class TimeBelow400mAchievement(Achievement):
    @property
    def title(self):
        return _("Spent %(minutes)s minutes below 400 m AGL", **self.params)

    def is_achieved(self, context):
        return context.time_below_400_m / 60.0 >= self.params['minutes']


class CommentAchievement(Achievement):
    @property
    def title(self):
        if self.params['number'] == 1:
            return _("First comment made on SkyLines")
        return _("%(number)s comments made on SkyLines", **self.params)

    def is_achieved(self, context):
        # Assume PilotMetrics as context
        return context.comments_made >= self.params['number']


class CirclingPercentageAchievement(Achievement):
    @property
    def title(self):
        return _("Circling percentage on a long flight (> 300km) under "
                 "%(percentage)s%", **self.params)

    def is_achieved(self, context):
        if context.distance < 300:
            return False
        return context.circling_percentage < self.params['percentage']


class TracksUploadedAchievement(Achievement):
    @property
    def title(self):
        if self.params['number'] == 1:
            return _("First track uploaded on SkyLines")
        return _("%(number)s tracks uploaded on SkyLines", **self.params)

    def is_achieved(self, context):
        # Assume PilotMetrics as context
        return context.tracks_uploaded >= self.params['number']


class UsersFollowedAchievement(Achievement):
    @property
    def title(self):
        if self.params['number'] == 1:
            return _("First user followed on SkyLines")
        return _("%(number)s users followed on SkyLines", **self.params)

    def is_achieved(self, context):
        # Assume PilotMetrics as context
        return context.users_followed >= self.params['number']


class FollowersAttractedAchievement(Achievement):
    @property
    def title(self):
        if self.params['number'] == 1:
            return _("Attracted first follower on SkyLines")
        return _("Attracted %(number)s followers on SkyLines", **self.params)

    def is_achieved(self, context):
        # Assume PilotMetrics as context
        return context.followers_attracted >= self.params['number']


class TotalDistanceAchievement(Achievement):
    @property
    def title(self):
        return _("Log a total distance of %(number)s km", **self.params)

    def is_achieved(self, context):
        # Assume PilotMetrics as context
        return context.total_distance >= self.params['number']


FLIGHT_ACHIEVEMENTS = \
    [TriangleAchievement('triangle-50', distance=50),
     TriangleAchievement('triangle-100', distance=100),
     TriangleAchievement('triangle-200', distance=200),
     TriangleAchievement('triangle-300', distance=300),
     TriangleAchievement('triangle-500', distance=500),
     TriangleAchievement('triangle-1000', distance=1000),

     DurationAchievement('duration-3', duration=3),
     DurationAchievement('duration-5', duration=5),
     DurationAchievement('duration-7', duration=7),
     DurationAchievement('duration-10', duration=10),
     DurationAchievement('duration-12', duration=12),
     DurationAchievement('duration-15', duration=15),

     FinalGlideDistanceAchievement('final-glide-10', distance=10),
     FinalGlideDistanceAchievement('final-glide-20', distance=20),
     FinalGlideDistanceAchievement('final-glide-30', distance=30),
     FinalGlideDistanceAchievement('final-glide-50', distance=50),
     FinalGlideDistanceAchievement('final-glide-75', distance=75),
     FinalGlideDistanceAchievement('final-glide-100', distance=100),

     AltitudeGainAchievement('alt-gain-1000', gain=1000),
     AltitudeGainAchievement('alt-gain-2000', gain=2000),
     AltitudeGainAchievement('alt-gain-3000', gain=3000),
     AltitudeGainAchievement('alt-gain-4000', gain=4000),
     AltitudeGainAchievement('alt-gain-5000', gain=5000),

     TimeBelow400mAchievement('time-below-400m-30', minutes=30),
     TimeBelow400mAchievement('time-below-400m-45', minutes=45),
     TimeBelow400mAchievement('time-below-400m-60', minutes=60),
     TimeBelow400mAchievement('time-below-400m-90', minutes=90),
     TimeBelow400mAchievement('time-below-400m-120', minutes=120),
     TimeBelow400mAchievement('time-below-400m-180', minutes=180),

     CirclingPercentageAchievement('circling-perc-30', percentage=30),
     CirclingPercentageAchievement('circling-perc-25', percentage=25),
     CirclingPercentageAchievement('circling-perc-20', percentage=20),
     CirclingPercentageAchievement('circling-perc-15', percentage=15),
     CirclingPercentageAchievement('circling-perc-10', percentage=10),
     CirclingPercentageAchievement('circling-perc-5', percentage=5),
     ]


UPLOAD_ACHIEVEMENTS = \
    [TracksUploadedAchievement('upload-1', number=1),
     TracksUploadedAchievement('upload-10', number=10),
     TracksUploadedAchievement('upload-100', number=100),
     TracksUploadedAchievement('upload-1000', number=1000),
     ]


COMMENT_ACHIEVEMENTS = \
    [CommentAchievement('comment-1', number=1),
     CommentAchievement('comment-10', number=10),
     CommentAchievement('comment-100', number=100),
     CommentAchievement('comment-1000', number=1000),
     ]


FOLLOW_ACHIEVEMENTS = \
    [UsersFollowedAchievement('follow-1', number=1),
     UsersFollowedAchievement('follow-10', number=10),
     UsersFollowedAchievement('follow-100', number=100),
     UsersFollowedAchievement('follow-1000', number=1000),
     ]


FOLLOWER_ACHIEVEMENTS = \
    [FollowersAttractedAchievement('follower-1', number=1),
     FollowersAttractedAchievement('follower-10', number=10),
     FollowersAttractedAchievement('follower-100', number=100),
     FollowersAttractedAchievement('follower-1000', number=1000),
     ]

TOTAL_DISTANCE_ACHIEVEMENTS = \
    [TotalDistanceAchievement('total-distance-500', number=500),
     TotalDistanceAchievement('total-distance-1000', number=1000),
     TotalDistanceAchievement('total-distance-2500', number=2500),
     TotalDistanceAchievement('total-distance-5000', number=5000),
     TotalDistanceAchievement('total-distance-10000', number=10000),
     TotalDistanceAchievement('total-distance-25000', number=25000),
     TotalDistanceAchievement('total-distance-50000', number=50000),
     TotalDistanceAchievement('total-distance-75000', number=75000),
     TotalDistanceAchievement('total-distance-100000', number=100000),
     TotalDistanceAchievement('total-distance-200000', number=200000),
     TotalDistanceAchievement('total-distance-500000', number=500000),
     TotalDistanceAchievement('total-distance-1000000', number=1000000)
     ]


ACHIEVEMENT_BY_NAME = {a.name: a
                       for a in itertools.chain(FLIGHT_ACHIEVEMENTS,
                                                UPLOAD_ACHIEVEMENTS,
                                                COMMENT_ACHIEVEMENTS,
                                                FOLLOW_ACHIEVEMENTS,
                                                FOLLOWER_ACHIEVEMENTS,
                                                TOTAL_DISTANCE_ACHIEVEMENTS)}


def get_achievement(name):
    return ACHIEVEMENT_BY_NAME[name]


def calculate_achievements(context, ach_definitions):
    return [a for a in ach_definitions if a.is_achieved(context)]


def get_user_achievements(user, ach_definitions):
    context = PilotMetrics(user)
    return calculate_achievements(context, ach_definitions)


def get_flight_achievements(flight):
    context = FlightMetrics(flight)
    return calculate_achievements(context, FLIGHT_ACHIEVEMENTS)
