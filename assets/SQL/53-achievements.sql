CREATE TABLE achievements
(
  id serial NOT NULL,
  name character varying NOT NULL,
  time_created timestamp without time zone NOT NULL,
  pilot_id integer NOT NULL,
  flight_id integer,
  CONSTRAINT achievements_pkey PRIMARY KEY (id),
  CONSTRAINT achievements_flight_id_fkey FOREIGN KEY (flight_id)
      REFERENCES flights (id) MATCH SIMPLE
      ON UPDATE NO ACTION ON DELETE CASCADE,
  CONSTRAINT achievements_pilot_id_fkey FOREIGN KEY (pilot_id)
      REFERENCES tg_user (id) MATCH SIMPLE
      ON UPDATE NO ACTION ON DELETE CASCADE,
  CONSTRAINT unique_achievement UNIQUE (name, pilot_id)
);

CREATE INDEX ix_achievements_flight_id
  ON achievements
  USING btree
  (flight_id);

CREATE INDEX ix_achievements_name
  ON achievements
  USING btree
  (name);

CREATE INDEX ix_achievements_pilot_id
  ON achievements
  USING btree
  (pilot_id);

ALTER TABLE events
  ADD COLUMN achievement_id integer;

ALTER TABLE events
  ADD FOREIGN KEY (achievement_id) REFERENCES achievements (id)
  ON UPDATE NO ACTION ON DELETE CASCADE;

