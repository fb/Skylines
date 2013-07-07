# -*- coding: utf-8 -*-
from datetime import datetime

from sqlalchemy import Column, func
from sqlalchemy.types import Unicode, Integer, DateTime, Date, String

from skylines.model import db
from skylines.lib.achievements import get_flight_achievements, get_achievement
from skylines.model.event import create_achievement_notification, Event


class UnlockedAchievement(db.Model):
    __tablename__ = 'achievements'
    __table_args__ = (
        db.UniqueConstraint(
            'name', 'pilot_id', name='unique_achievement'),
    )

    id = Column(Integer, autoincrement=True, primary_key=True)
    time_created = Column(DateTime, nullable=False, default=datetime.utcnow)
    time_achieved = Column(DateTime, nullable=False, default=datetime.utcnow)
    name = Column(String(), nullable=False, index=True)

    pilot_id = db.Column(
        Integer, db.ForeignKey('tg_user.id', ondelete='CASCADE'),
        index=True, nullable=False)
    pilot = db.relationship('User', foreign_keys=[pilot_id],
                            backref='achievements')

    flight_id = db.Column(
        Integer, db.ForeignKey('flights.id', ondelete='CASCADE'), index=True)
    flight = db.relationship('Flight', foreign_keys=[flight_id],
                             backref=db.backref('achievements',
                                                order_by=name,
                                                passive_deletes=True))

    def __repr__(self):
        r = "<UnlockedAchievement %s: id=%s>" % (self.name, self.id)
        return r.encode('utf-8')

    @property
    def title(self):
        return get_achievement(self.name).title


def unlock_flight_achievements(flight):
    """Calculate new flight achievements for the pilot and store them in
    database.
    """
    pilot = flight.pilot
    assert pilot is not None

    unlocked_achievements = {a.name: a for a in pilot.achievements}
    achievements = get_flight_achievements(flight)

    newunlocked = []
    for a in achievements:
        time_achieved = flight.landing_time

        if a.name in unlocked_achievements:
            # check if flight was started prior the flight in existing
            # achievement and update both acievement and notification event in
            # this case.
            oldach = unlocked_achievements[a.name]
            if oldach.time_achieved > time_achieved:
                # reassign the flight
                oldach.flight = flight
                oldach.time_achieved = time_achieved
                # Update achievement event too
                event = Event.query(achievement_id=oldach.id).one()
                event.flight = flight

        else:
            newach = UnlockedAchievement(name=a.name,
                                         pilot=pilot, flight=flight,
                                         time_achieved=flight.landing_time)
            newunlocked.append(newach)
            db.session.add(newach)
            create_achievement_notification(newach)

    return newunlocked
