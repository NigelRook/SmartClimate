'''
Smartclimate component for homeassistant

Learns how long it takes your home to change temperature, ans allows you to
pre-heat your home at the most appropriate time
'''
# pylint: disable=locally-disabled, line-too-long, R0902, R0903
import os
import pickle
import logging
import voluptuous as vol

import homeassistant.util.dt as dt

from homeassistant.helpers import config_validation as cv, event as evt
from homeassistant.const import (
    CONF_ENTITY_ID, CONF_SENSORS, ATTR_TEMPERATURE)

DOMAIN = 'smartclimate'

CONF_ATTRIBUTE = 'attribute'

ATTR_CURRENT_TEMPERATURE = 'current_temperature'

STORE = 'store'
TRACKER = 'tracker'
DATAPOINTS = 'datapoints'

DEPENDENCIES = ['climate']

REQUIREMENTS = ['numpy==1.13.3', 'scipy==1.00', 'scikit-learn==0.19.1']

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_SENSORS): [
            vol.Schema({
                vol.Required(CONF_ENTITY_ID): cv.entity_id,
                vol.Optional(CONF_ATTRIBUTE): cv.string
            })
        ]
    }),
}, extra=vol.ALLOW_EXTRA)

_LOGGER = logging.getLogger(__name__)

def setup(hass, config):
    '''Set up component'''
    data_file = hass.config.path("{}.pickle".format(DOMAIN))
    store = DataStore(data_file)

    entity_id = config[DOMAIN][CONF_ENTITY_ID]
    sensors = config[DOMAIN].get(CONF_SENSORS, [])
    _LOGGER.debug('entity_id=%s, sensors = %s', entity_id, sensors)
    tracker = SmartClimate(hass, store, entity_id, sensors)

    hass.data[DOMAIN] = {
        STORE : DataStore(data_file),
        TRACKER : tracker
    }

    return True

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

class SmartClimate:
    '''Main SmartClimate class'''
    IDLE = 'idle'
    TRACKING = 'tracking'

    def __init__(self, hass, store, entity_id, sensors):
        self._hass = hass

        self._store = store
        if entity_id not in self._store.data:
            self._store.data[entity_id] = {}
        if DATAPOINTS not in self._store.data[entity_id]:
            self._store.data[entity_id][DATAPOINTS] = []

        self._entity_id = entity_id
        self._sensors = sensors

        self._listener = evt.track_state_change(hass, entity_id, self._handle_climate_change)
        self._tracking_state = self.IDLE

        self._start_temp = None
        self._target_temp = None
        self._sensor_readings = None
        self._tracking_started_time = None

    def _handle_climate_change(self, _, old_state, new_state):
        _LOGGER.debug('new state for %s: curr=%s, target=%s',
                      self._entity_id,
                      new_state.attributes[ATTR_CURRENT_TEMPERATURE],
                      new_state.attributes[ATTR_TEMPERATURE])
        if not old_state:
            return
        if self._tracking_state == self.IDLE:
            if self._should_begin_monitoring(old_state, new_state):
                _LOGGER.info('Tracking climate change for %s from %s to %s',
                             self._entity_id,
                             new_state.attributes[ATTR_CURRENT_TEMPERATURE],
                             new_state.attributes[ATTR_TEMPERATURE])
                self._start_temp = new_state.attributes[ATTR_CURRENT_TEMPERATURE]
                self._target_temp = new_state.attributes[ATTR_TEMPERATURE]
                self._sensor_readings = {self._get_sensor_name(sensor): self._read_sensor(sensor)
                                         for sensor in self._sensors}
                if self._sensor_readings:
                    _LOGGER.debug('initial sensor readings: %s', self._sensor_readings)
                self._tracking_state = self.TRACKING
                self._tracking_started_time = dt.utcnow()
        elif self._tracking_state == self.TRACKING:
            if new_state.attributes[ATTR_TEMPERATURE] == self._target_temp:
                if new_state.attributes[ATTR_CURRENT_TEMPERATURE] >= self._target_temp:
                    duration_s = (dt.utcnow() - self._tracking_started_time).total_seconds()
                    _LOGGER.info("Tracking complete for %s, took %s seconds",
                                 self._entity_id, duration_s)
                    self._tracking_complete(duration_s)
                    self._tracking_state = self.IDLE
            else:
                _LOGGER.info("Tracking aborted for %s, target temperature changed",
                             self._entity_id)
                self._tracking_state = self.IDLE

    @staticmethod
    def _should_begin_monitoring(old_state, new_state):
        return (new_state.attributes[ATTR_TEMPERATURE] > old_state.attributes[ATTR_TEMPERATURE] + 0.5 and
                new_state.attributes[ATTR_TEMPERATURE] > new_state.attributes[ATTR_CURRENT_TEMPERATURE])

    @staticmethod
    def _get_sensor_name(sensor):
        if CONF_ATTRIBUTE in sensor:
            return '{}.{}'.format(sensor[CONF_ENTITY_ID], sensor[CONF_ATTRIBUTE])
        else:
            return sensor[CONF_ENTITY_ID]

    def _read_sensor(self, sensor):
        state = self._hass.states.get(sensor[CONF_ENTITY_ID])
        if CONF_ATTRIBUTE in sensor:
            return float(state.attributes[sensor[CONF_ATTRIBUTE]])
        else:
            return float(state.state)

    def _tracking_complete(self, duration_s):
        datapoint = {
            'start_temp' : self._start_temp,
            'target_temp' : self._target_temp,
            'sensor_readings': self._sensor_readings,
            'duration_s' : duration_s
        }
        self._store.data[self._entity_id][DATAPOINTS].append(datapoint)
        self._store.save()
