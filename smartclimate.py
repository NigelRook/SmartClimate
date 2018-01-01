'''
Smartclimate component for homeassistant

Learns how long it takes your home to change temperature, ans allows you to
pre-heat your home at the most appropriate time
'''
import os
import pickle
import logging
from asyncio import coroutine
from uuid import uuid4
import voluptuous as vol

import homeassistant.util.dt as dt

from homeassistant.core import callback
from homeassistant.util.async import run_callback_threadsafe
from homeassistant.helpers import config_validation as cv, event as evt
from homeassistant.const import (
    CONF_ENTITY_ID, CONF_SENSORS, ATTR_TEMPERATURE, STATE_UNKNOWN)

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
BINARY_SENSORS = 'binary_sensors'
DATAPOINTS = 'datapoints'

SCHEDULE_FORMAT = '{}.schedule_{{}}'.format(DOMAIN)

DEPENDENCIES = ['climate']

REQUIREMENTS = ['numpy==1.13.3', 'scipy==1.00', 'scikit-learn==0.19.1']

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
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
}, extra=vol.ALLOW_EXTRA)

SERVICE_CONFIGURE = 'configure'

CONFIGURE_DESCRIPTIONS = {
    SERVICE_CONFIGURE: {
        'description': 'Reconfigure a sensor',
        'fields': {
            CONF_ENTITY_ID: {
                'description': 'Sensor to reconfigure',
                'example': 'binary_sensor.morning'
            },
            CONF_TEMPERATURE: {
                'description': 'New target temperature',
                'example': 20
            },
            CONF_START: {
                'description': 'New start time (binary sensor only)',
                'example': '06:30'
            },
            CONF_END: {
                'description': 'New start time (binary sensor only)',
                'example': '07:30'
            }
        }
    }
}

CONFIGURE_SCHEMA = vol.Schema({
    vol.Required(CONF_ENTITY_ID): cv.entity_id,
    vol.Optional(CONF_TEMPERATURE): vol.Coerce(float),
    vol.Optional(CONF_START): cv.time,
    vol.Optional(CONF_END): cv.time
})

MIN_DATAPOINTS = 3

_LOGGER = logging.getLogger(__name__)

@coroutine
def async_setup(hass, config):
    '''Set up component'''
    data_file = hass.config.path("{}.pickle".format(DOMAIN))
    store = yield from hass.async_add_job(DataStore, data_file)

    _LOGGER.debug('config = %s', config[DOMAIN])
    coros = [hass.loop.run_in_executor(None, Model, hass, store, name, entity_config)
             for name, entity_config in config[DOMAIN].items()]
    models = {}
    for coro in coros:
        model = yield from coro
        models[model.name] = model

    hass.data[DOMAIN] = {MODELS: models}

    @coroutine
    def handle_update_binary_sensor(call):
        '''update binary sensor configuration'''
        entity_id = call.data[CONF_ENTITY_ID]
        temperature = call.data.get(CONF_TEMPERATURE)
        start = call.data.get(CONF_START)
        end = call.data.get(CONF_END)
        yield from hass.data[DOMAIN][BINARY_SENSORS][entity_id].update_config(temperature, start, end)

    hass.services.async_register(
        DOMAIN, SERVICE_CONFIGURE, handle_update_binary_sensor,
        CONFIGURE_DESCRIPTIONS, schema=CONFIGURE_SCHEMA)

    return True


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
        target_temp = entity_state.attributes.get(ATTR_TEMPERATURE, None) if entity_state else None
        current_temp = entity_state.attributes.get(ATTR_CURRENT_TEMPERATURE, None) if entity_state else None
        _, current_temp, sensor_readings = self._get_readings(target_temp, current_temp)
        return (current_temp, sensor_readings)

    def _get_readings(self, target_temp, current_temp):
        sensor_readings = [(self._get_sensor_name(sensor), self._read_sensor(sensor))
                           for sensor in self._sensors]
        return (float(target_temp) if target_temp is not None else None,
                float(current_temp) if target_temp is not None else None,
                sensor_readings)

    @callback
    def _handle_climate_change(self, _, old_state, new_state):
        _LOGGER.debug('new state for %s: curr=%s, target=%s',
                      self.entity_id,
                      new_state.attributes[ATTR_CURRENT_TEMPERATURE],
                      new_state.attributes[ATTR_TEMPERATURE])

        if not old_state:
            return

        old_temp = new_temp = current_temp = None
        try:
            old_temp = float(old_state.attributes[ATTR_TEMPERATURE])
            new_temp = float(new_state.attributes[ATTR_TEMPERATURE])
            current_temp = float(new_state.attributes[ATTR_CURRENT_TEMPERATURE])
        except (KeyError, ValueError, TypeError):
            return

        if self._tracking_state == self.IDLE:
            self._handle_idle_climate_change(old_temp, new_temp, current_temp)
        elif self._tracking_state == self.TRACKING:
            if float(new_state.attributes[ATTR_TEMPERATURE]) == self._target_temp:
                self._handle_tracked_temp_change(current_temp)
            else:
                self._handle_tracked_target_temp_change(new_temp, current_temp)

    def _handle_idle_climate_change(self, old_temp, new_temp, current_temp):
        if not self._should_begin_monitoring(old_temp, new_temp, current_temp):
            return

        self._target_temp, self._start_temp, self._sensor_readings = self._get_readings(new_temp, current_temp)
        if self._start_temp is None or None in (value for (_, value) in self._sensor_readings):
            return

        self._tracking_state = self.TRACKING
        self._tracking_started_time = dt.utcnow()

        _LOGGER.info('Tracking climate change for %s from %s to %s',
                     self.entity_id, self._start_temp, self._target_temp)
        if self._sensor_readings:
            _LOGGER.debug('initial sensor readings: %s', self._sensor_readings)

    def _handle_tracked_temp_change(self, current_temp):
        if current_temp < self._target_temp:
            return

        self._complete_tracking(current_temp)

    def _handle_tracked_target_temp_change(self, new_temp, current_temp):
        if new_temp > current_temp:
            self._target_temp = current_temp
            return

        self._complete_tracking(current_temp)

    def _complete_tracking(self, end_temp):
        self._tracking_state = self.IDLE

        if end_temp <= self._start_temp:
            _LOGGER.info("Tracking aborted for %s - no temperature change", self.entity_id)
            return

        duration_s = (dt.utcnow() - self._tracking_started_time).total_seconds()
        _LOGGER.info("Tracking complete for %s, took %s seconds",
                     self.entity_id, duration_s)
        self._hass.async_run_job(self._new_datapoint_handler, end_temp,
                                 self._start_temp, self._sensor_readings, duration_s)

    @callback
    def _handle_update(self, event, old_state, new_state): #pylint: disable=unused-argument
        current_temp, sensor_readings = self.get_readings()
        for handler in self._update_handlers.values():
            self._hass.async_run_job(handler, current_temp, sensor_readings)

    @staticmethod
    def _should_begin_monitoring(old_temp, new_temp, current_temp):
        return new_temp > old_temp + 0.5 and new_temp > current_temp

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
