# -*- coding: utf-8 -*-
from datetime import datetime

from sqlalchemy import Column, func
from sqlalchemy.types import Unicode, Integer, DateTime, Date, String

from skylines.model import db


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
