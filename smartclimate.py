'''
Smartclimate component for homeassistant

Learns how long it takes your home to change temperature, ans allows you to
pre-heat your home at the most appropriate time
'''
import os
import pickle
import logging
from datetime import timedelta
from asyncio import coroutine
from uuid import uuid4
import voluptuous as vol

import homeassistant.util.dt as dt

from homeassistant.core import callback
from homeassistant.util.async import run_callback_threadsafe
from homeassistant.helpers import config_validation as cv, event as evt
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.const import (
    CONF_ENTITY_ID, CONF_SENSORS,
    ATTR_TEMPERATURE,
    STATE_UNKNOWN, STATE_OFF, STATE_ON)

DOMAIN = 'smartclimate'

CONF_ATTRIBUTE = 'attribute'
CONF_MODELS = 'models'
CONF_SCHEDULES = 'schedules'
CONF_MODEL = 'model'
CONF_TEMPERATURE = 'temperature'
CONF_START = 'start'
CONF_END = 'end'

ATTR_CURRENT_TEMPERATURE = 'current_temperature'
ATTR_MODEL = 'model'
ATTR_START = 'start'
ATTR_END = 'end'
ATTR_HEATING_TIME = 'heating_time'
ATTR_NEXT_ON = 'next_on'

STORE = 'store'
MODELS = 'models'
DATAPOINTS = 'datapoints'

SCHEDULE_FORMAT = '{}.schedule_{{}}'.format(DOMAIN)

DEPENDENCIES = ['climate']

REQUIREMENTS = ['numpy==1.13.3', 'scipy==1.00', 'scikit-learn==0.19.1']

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_MODELS): vol.Schema({
            cv.slug: vol.Schema({
                vol.Required(CONF_ENTITY_ID): cv.entity_id,
                vol.Optional(CONF_SENSORS): [
                    vol.Schema({
                        vol.Required(CONF_ENTITY_ID): cv.entity_id,
                        vol.Optional(CONF_ATTRIBUTE): cv.string,
                    })
                ]
            })
        }),
        vol.Optional(CONF_SCHEDULES, {}): vol.Schema({
            cv.slug: vol.Schema({
                vol.Required(CONF_MODEL): cv.slug,
                vol.Required(CONF_TEMPERATURE): vol.Coerce(float),
                vol.Required(CONF_START): cv.time,
                vol.Required(CONF_END): cv.time,
            }),
        }),
    }),
}, extra=vol.ALLOW_EXTRA)

MIN_DATAPOINTS = 3

_LOGGER = logging.getLogger(__name__)

@coroutine
def async_setup(hass, config):
    '''Set up component'''
    data_file = hass.config.path("{}.pickle".format(DOMAIN))
    store = yield from hass.async_add_job(DataStore, data_file)

    component = EntityComponent(_LOGGER, DOMAIN, hass)

    _LOGGER.debug('config = %s', config[DOMAIN])
    coros = [hass.loop.run_in_executor(None, Model, hass, store, name, entity_config)
             for name, entity_config in config[DOMAIN][CONF_MODELS].items()]
    models = {}
    for coro in coros:
        model = yield from coro
        models[model.name] = model

    schedules = [Schedule(hass, name, models, config)
                 for name, config in config[DOMAIN].get(CONF_SCHEDULES, {}).items()]

    yield from component.async_add_entities(schedules)

    return True

class Schedule(Entity):
    '''Main schedule class

       create inside event loop only'''
    def __init__(self, hass, name, models, config):
        self.entity_id = SCHEDULE_FORMAT.format(name)
        self.hass = hass
        self._name = name
        self._model = models[config[CONF_MODEL]]
        self._temperature = config[CONF_TEMPERATURE]
        self._start = config[CONF_START].replace(tzinfo=dt.DEFAULT_TIME_ZONE)
        self._end = config[CONF_END].replace(tzinfo=dt.DEFAULT_TIME_ZONE)
        self._next_on = None
        self._stop_timer = None
        self._stop_listening = None
        self._state = STATE_UNKNOWN
        self._heating_time = self._model.predict(self._temperature)
        hass.async_run_job(self._update_state, self._heating_time)

    @coroutine
    def _update_state(self, heating_time):
        self._heating_time = heating_time
        heating_time = heating_time if heating_time is not None else 3600
        now = dt.now()
        today_start = dt.dt.datetime.combine(now.date(), self._start)
        today_end = dt.dt.datetime.combine(now.date(), self._end)

        if now < today_start:
            self._next_on = dt.as_local(dt.as_utc(today_start) - timedelta(seconds=heating_time))
            if now < self._next_on:
                self._set_off_state()
            else:
                self._next_on = None
                self._set_on_state()
        elif now < today_end:
            self._next_on = None
            self._set_on_state()
        else:
            tomorrow_start = today_start + timedelta(days=1)
            self._next_on = dt.as_local(dt.as_utc(tomorrow_start) - timedelta(seconds=heating_time))
            self._set_off_state()

        yield from self.async_update_ha_state()

    def _set_off_state(self):
        if not self._stop_listening:
            self._stop_listening = self._model.listen_for_updates(self._temperature, self._update_state)

        self._set_timer(self._next_on)
        self._state = STATE_OFF

    def _set_on_state(self):
        if self._stop_listening:
            self.hass.async_run_job(self._stop_listening)
            self._stop_listening = None

        now = dt.now()
        off_time = dt.dt.datetime.combine(now.date(), self._end)
        if now > off_time:
            off_time = off_time + timedelta(days=1)

        self._set_timer(off_time)
        self._state = STATE_ON

    @coroutine
    def _timer_handler(self, _):
        self._stop_timer = None
        heating_time = self._model.predict(self._temperature)
        yield from self._update_state(heating_time)

    def _set_timer(self, when):
        if self._stop_timer:
            self.hass.async_run_job(self._stop_timer)
        self._stop_timer = evt.async_track_point_in_time(self.hass, self._timer_handler, when)

    @property
    def should_poll(self):
        return False

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def state_attributes(self):
        attributes = {
            ATTR_MODEL: self._model.name,
            ATTR_TEMPERATURE: str(self._temperature),
            ATTR_START: self.format_time(self._start),
            ATTR_END: self.format_time(self._end),
        }
        if self._heating_time is not None:
            attributes[ATTR_HEATING_TIME] = int(round(self._heating_time))
        if self._state == STATE_OFF:
            attributes[ATTR_NEXT_ON] = self.format_time(self._next_on)
        return attributes

    @staticmethod
    def format_time(time):
        '''format times for attribute display'''
        fmt = '%H:%M' if time.second == 0 else '%H:%M:%S'
        return time.strftime(fmt)

class Model:
    '''Main SmartClimate class'''
    def __init__(self, hass, store, name, config):
        _LOGGER.debug("Initialising model %s with config %s", name, config)

        self.name = name
        self._hass = hass

        self._store = store
        if self.name not in self._store.data:
            self._store.data[self.name] = {}
        if DATAPOINTS not in self._store.data[self.name]:
            self._store.data[self.name][DATAPOINTS] = []

        self._tracker = Tracker(hass, config, self._handle_new_datapoint)
        self._predictor = LinearPredictor(name)

        datapoints = self._store.data[self.name][DATAPOINTS]
        self._predictor.learn(datapoints)

    def listen_for_updates(self, target_temp, handler):
        '''Request notification whenever the tracker detects a reading change'''
        @callback
        def wrapped_handler(current_temp, sensor_readings): #pylint: disable=missing-docstring
            prediction = self._predict(target_temp, current_temp, sensor_readings)
            self._hass.async_run_job(handler, prediction)

        return self._tracker.listen_for_updates(wrapped_handler)

    def predict(self, target_temp):
        '''Predict how long it will take to reach the target temperature'''
        current_temp, sensor_readings = self._tracker.get_readings()
        return self._predict(target_temp, current_temp, sensor_readings)

    def _predict(self, target_temp, current_temp, sensor_readings):
        if current_temp is None or None in (value for (_, value) in sensor_readings):
            return None
        return self._predictor.predict(target_temp, current_temp, sensor_readings)

    def _handle_new_datapoint(self, target_temp, start_temp, sensor_readings, duration_s):
        datapoint = {
            'start_temp' : start_temp,
            'target_temp' : target_temp,
            'sensor_readings': sensor_readings,
            'duration_s' : duration_s
        }
        self._store.data[self.name][DATAPOINTS].append(datapoint)
        self._store.save()
        self._predictor.learn(self._store.data[self.name][DATAPOINTS])

class Tracker:
    '''Class for tracking temperature changes to learn from'''
    IDLE = 'idle'
    TRACKING = 'tracking'

    def __init__(self, hass, config, new_datapoint_handler):
        self.entity_id = config[CONF_ENTITY_ID]
        self._hass = hass
        self._sensors = config.get(CONF_SENSORS, [])
        self._new_datapoint_handler = new_datapoint_handler

        self._tracking_state = self.IDLE
        self._update_handlers = {}
        _LOGGER.debug('listening for %s state changes', self.entity_id)
        self._listener = run_callback_threadsafe(self._hass.loop, evt.async_track_state_change,
            self._hass, self.entity_id, self._handle_climate_change) #pylint: disable=C0330

        self._updates_listener = None
        self._start_temp = None
        self._target_temp = None
        self._sensor_readings = None
        self._tracking_started_time = None

    @callback
    def listen_for_updates(self, handler):
        '''Add a listener for updates to tracked entity/sensors'''
        entity_ids = [self.entity_id] + [sensor[CONF_ENTITY_ID] for sensor in self._sensors]
        if not self._updates_listener:
            self._updates_listener = evt.async_track_state_change(self._hass, entity_ids,
                                                                  self._handle_update)

        uuid = uuid4()
        self._update_handlers[uuid] = handler
        def remove():  #pylint: disable=missing-docstring
            del self._update_handlers[uuid]

            if not self._update_handlers:
                self._updates_listener()
                self._updates_listener = None

        return remove

    def get_readings(self):
        '''get readings from all relevant sensors'''
        entity_state = self._hass.states.get(self.entity_id)
        _, current_temp, sensor_readings = self._get_readings(entity_state)
        return (current_temp, sensor_readings)

    def _get_readings(self, entity_state):
        target_temp = entity_state.attributes.get(ATTR_TEMPERATURE, None) if entity_state else None
        current_temp = entity_state.attributes.get(ATTR_CURRENT_TEMPERATURE, None) if entity_state else None
        sensor_readings = [(self._get_sensor_name(sensor), self._read_sensor(sensor))
                           for sensor in self._sensors]
        return (float(target_temp) if target_temp is not None else None,
                float(current_temp) if target_temp is not None else None,
                sensor_readings)

    @coroutine
    def _handle_climate_change(self, _, old_state, new_state):
        _LOGGER.debug('new state for %s: curr=%s, target=%s',
                      self.entity_id,
                      new_state.attributes[ATTR_CURRENT_TEMPERATURE],
                      new_state.attributes[ATTR_TEMPERATURE])

        if not old_state:
            return

        if self._tracking_state == self.IDLE:
            if not self._should_begin_monitoring(old_state, new_state):
                return

            self._target_temp, self._start_temp, self._sensor_readings = self._get_readings(new_state)
            self._tracking_state = self.TRACKING
            self._tracking_started_time = dt.utcnow()

            _LOGGER.info('Tracking climate change for %s from %s to %s',
                         self.entity_id, self._start_temp, self._target_temp)
            if self._sensor_readings:
                _LOGGER.debug('initial sensor readings: %s', self._sensor_readings)

        elif self._tracking_state == self.TRACKING:
            if new_state.attributes[ATTR_TEMPERATURE] == self._target_temp:
                if new_state.attributes[ATTR_CURRENT_TEMPERATURE] < self._target_temp:
                    return

                duration_s = (dt.utcnow() - self._tracking_started_time).total_seconds()
                _LOGGER.info("Tracking complete for %s, took %s seconds",
                             self.entity_id, duration_s)
                self._tracking_state = self.IDLE
                self._hass.async_run_job(self._new_datapoint_handler, self._target_temp,
                                         self._start_temp, self._sensor_readings, duration_s)
            else:
                _LOGGER.info("Tracking aborted for %s, target temperature changed",
                             self.entity_id)
                self._tracking_state = self.IDLE

    @coroutine
    def _handle_update(self, event, old_state, new_state): #pylint: disable=unused-argument
        current_temp, sensor_readings = self.get_readings()
        for handler in self._update_handlers.values():
            self._hass.async_run_job(handler, current_temp, sensor_readings)

    @staticmethod
    def _should_begin_monitoring(old_state, new_state):
        return (new_state.attributes[ATTR_TEMPERATURE] > old_state.attributes[ATTR_TEMPERATURE] + 0.5 and
                new_state.attributes[ATTR_TEMPERATURE] > new_state.attributes[ATTR_CURRENT_TEMPERATURE])

    @staticmethod
    def _get_sensor_name(sensor):
        if CONF_ATTRIBUTE in sensor: #pylint: disable=R1705
            return '{}.{}'.format(sensor[CONF_ENTITY_ID], sensor[CONF_ATTRIBUTE])
        else:
            return sensor[CONF_ENTITY_ID]

    def _read_sensor(self, sensor):
        state = self._hass.states.get(sensor[CONF_ENTITY_ID])
        if state is None:
            return None

        if CONF_ATTRIBUTE in sensor:
            return float(state.attributes.get(sensor[CONF_ATTRIBUTE], None))

        if state.state is None or state.state == STATE_UNKNOWN:
            return None

        return float(state.state)

class LinearPredictor:
    '''Linear regression model for predicting heating time'''

    def __init__(self, name):
        from sklearn import linear_model
        self._name = name
        self._predictor = linear_model.LinearRegression()
        self._ready = False

    def predict(self, target_temp, current_temp, sensor_readings):
        '''Predict the time to reach target_temp'''
        if not self._ready:
            return self._predict_dumb(target_temp, current_temp)

        prediction = (self._predictor.intercept_ +
                      target_temp * self._predictor.coef_[0] +
                      current_temp * self._predictor.coef_[1])
        for i, (_, value) in enumerate(sensor_readings):
            prediction += value * self._predictor.coef_[i+2]

        _LOGGER.debug("[%s] Prediction for %s %s %s: %s", self._name,
                      target_temp, current_temp, sensor_readings, prediction)
        return prediction

    @staticmethod
    def _predict_dumb(target_temp, current_temp):
        return (target_temp - current_temp) * 30 * 60

    def learn(self, datapoints):
        '''Intrepret measured data'''
        if len(datapoints) < MIN_DATAPOINTS:
            self._ready = False
            return

        x_values = [[datapoint['target_temp'], datapoint['start_temp']] +
                    [value for _, value in datapoint['sensor_readings']] for datapoint in datapoints]
        y_values = [datapoint['duration_s'] for datapoint in datapoints]
        self._predictor.fit(x_values, y_values)
        self._ready = True
        _LOGGER.debug("[%s] Intercept:%s Coefficients:%s", self._name,
                      self._predictor.intercept_, self._predictor.coef_)

class DataStore:
    '''Data store for SmartClimate'''
    def __init__(self, data_file):
        self._data_file = data_file
        self._load()

    def _load(self):
        if os.path.exists(self._data_file):
            try:
                _LOGGER.debug('loading data from %s', self._data_file)
                with open(self._data_file, 'rb') as file:
                    self.data = pickle.load(file) or self._default_data()
            except:
                _LOGGER.error('Error loading data %s', self._data_file, exc_info=True)
                raise
        else:
            self.data = self._default_data()

    @staticmethod
    def _default_data():
        return {'_version': 1}

    def save(self):
        '''Commit current data to disk'''
        try:
            _LOGGER.debug('saving data to %s', self._data_file)
            temp_file = self._data_file+'.tmp'
            with open(temp_file, 'wb') as file:
                pickle.dump(self.data, file)
            if os.path.isfile(self._data_file):
                os.remove(self._data_file)
            os.rename(temp_file, self._data_file)
        except:
            _LOGGER.error('Error saving data %s', self._data_file, exc_info=True)
            raise
