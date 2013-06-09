# -*- coding: utf-8 -*-
from datetime import datetime

from sqlalchemy import Column, func
from sqlalchemy.types import Unicode, Integer, DateTime, Date, String

from skylines.model import db
from skylines.lib.achievements import get_flight_achievements, get_achievement


class UnlockedAchievement(db.Model):
    __tablename__ = 'achievements'

    id = Column(Integer, autoincrement=True, primary_key=True)
    time_created = Column(DateTime, nullable=False, default=datetime.utcnow)
    name = Column(String(), nullable=False)

    pilot_id = db.Column(
        Integer, db.ForeignKey('tg_user.id', ondelete='CASCADE'), index=True)
    pilot = db.relationship('User', foreign_keys=[pilot_id],
                            backref='achievements')

    flight_id = db.Column(
        Integer, db.ForeignKey('flights.id', ondelete='CASCADE'), index=True)
    flight = db.relationship('Flight', foreign_keys=[flight_id],
                             backref='achievements')

    def __repr__(self):
        r = "<UnlockedAchievement %s: id=%s" % (self.name, self.id)
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

    unlocked = [a.name for a in pilot.achievements]
    achievements = get_flight_achievements(flight)

    newunlocked = []
    for a in achievements:
        if a.name in unlocked:
            # don't unlock what is already unlocked
            continue
        newach = UnlockedAchievement(name=a.name, pilot=pilot, flight=flight)
        newunlocked.append(newach)
        db.session.add(newach)

    return newunlocked
