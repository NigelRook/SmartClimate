'''
SmartClimate binary_sensor component

Will have a value of 'on' if it thinks heating should be on, or 'off' if it thinks heating should be off
'''
import logging
from datetime import timedelta
from asyncio import coroutine
import voluptuous as vol

import homeassistant.util.dt as dt

from homeassistant.helpers import config_validation as cv, event as evt
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.const import (
    CONF_NAME, ATTR_TEMPERATURE, ATTR_FRIENDLY_NAME)
from homeassistant.components.binary_sensor import (
    BinarySensorDevice, ENTITY_ID_FORMAT, PLATFORM_SCHEMA)

from ..smartclimate import DOMAIN, MODELS, CONF_TEMPERATURE, CONF_START, CONF_END, BINARY_SENSORS

DEPENDENCIES = ['smartclimate']

CONF_MODEL = 'model'

ATTR_MODEL = 'model'
ATTR_START = 'start'
ATTR_END = 'end'
ATTR_HEATING_TIME = 'heating_time'
ATTR_NEXT_ON = 'next_on'

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_NAME): cv.slug,
    vol.Optional(ATTR_FRIENDLY_NAME): cv.string,
    vol.Required(CONF_MODEL): cv.slug,
    vol.Required(CONF_TEMPERATURE): vol.Coerce(float),
    vol.Required(CONF_START): cv.time,
    vol.Required(CONF_END): cv.time,
})

@coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up smartclimate binary sensor"""

    config = PLATFORM_SCHEMA(config)
    name = config[CONF_NAME]
    entity_id = async_generate_entity_id(ENTITY_ID_FORMAT, name, hass=hass)
    friendly_name = config.get(ATTR_FRIENDLY_NAME, name)
    model = hass.data[DOMAIN][MODELS][config[CONF_MODEL]]
    temperature = config[CONF_TEMPERATURE]
    start = config[CONF_START]
    end = config[CONF_END]

    sensor = SmartClimateBinarySensor(hass, entity_id, friendly_name, model, temperature, start, end)

    async_add_devices([sensor])

    if BINARY_SENSORS not in hass.data[DOMAIN]:
        hass.data[DOMAIN][BINARY_SENSORS] = {}

    hass.data[DOMAIN][BINARY_SENSORS][entity_id] = sensor

    return True

class SmartClimateBinarySensor(BinarySensorDevice):
    """A binary sensor indicating when heating should be on to satisfy a schedule."""

    def __init__(self, hass, entity_id, friendly_name, model, temperature, start, end):
        """Initialize the Smart Climate schedule."""
        self.hass = hass
        self.entity_id = entity_id
        self._friendly_name = friendly_name
        self._model = model
        self._temperature = temperature
        self._start = start.replace(tzinfo=dt.DEFAULT_TIME_ZONE)
        self._end = end.replace(tzinfo=dt.DEFAULT_TIME_ZONE)
        self._state = None
        self._heating_time = None
        self._next_on = None
        self._stop_timer = None
        self._stop_listening = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._friendly_name

    @property
    def is_on(self):
        """Return true if sensor is on."""
        return self._state

    @property
    def should_poll(self):
        """No polling needed."""
        return False

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
        if self._state == False: #pylint: disable=C0121
            attributes[ATTR_NEXT_ON] = self.format_time(self._next_on)
        return attributes

    @staticmethod
    def format_time(time):
        '''format times for attribute display'''
        fmt = '%H:%M' if time.second == 0 else '%H:%M:%S'
        return time.strftime(fmt)

    @coroutine
    def async_added_to_hass(self):
        """Register callbacks."""

        heating_time = self._model.predict(self._temperature)
        yield from self._update_state(heating_time)

    @coroutine
    def update_config(self, temperature, start, end):
        '''update this sensor's configuration'''
        if temperature is not None:
            self._temperature = temperature
        if start is not None:
            self._start = start.replace(tzinfo=dt.DEFAULT_TIME_ZONE)
        if end is not None:
            self._end = end.replace(tzinfo=dt.DEFAULT_TIME_ZONE)

        heating_time = self._model.predict(self._temperature)
        yield from self._update_state(heating_time)

    @coroutine
    def _update_state(self, heating_time):
        self._heating_time = heating_time
        heating_time = heating_time if heating_time is not None else 3600
        now = dt.now()
        time_now = now.timetz()

        # we want the current heating session if there is one, next one otherwise
        start_date = None
        if time_now < self._end:
            # still have some heating to do today, but may hae started yesterday
            start_date = now.date() if self._start <= self._end else now.date() - timedelta(days=1)
        else:
            # heating finishes tomorrow, but may still start today
            start_date = now.date() if self._start > self._end else now.date() + timedelta(days=1)

        start = dt.as_local(
            dt.as_utc(dt.dt.datetime.combine(start_date, self._start)) \
                - timedelta(seconds=heating_time))

        if now < start:
            self._next_on = start
            self._set_off_state()
        else:
            self._next_on = None
            self._set_on_state()

        yield from self.async_update_ha_state()

    def _set_off_state(self):
        if not self._stop_listening:
            self._stop_listening = self._model.listen_for_updates(self._temperature, self._update_state)

        self._set_timer(self._next_on)
        self._state = False

    def _set_on_state(self):
        if self._stop_listening:
            self.hass.async_run_job(self._stop_listening)
            self._stop_listening = None

        now = dt.now()
        off_time = dt.dt.datetime.combine(now.date(), self._end)
        if now > off_time:
            off_time = off_time + timedelta(days=1)

        self._set_timer(off_time)
        self._state = True

    @coroutine
    def _timer_handler(self, _):
        self._stop_timer = None
        heating_time = self._model.predict(self._temperature)
        yield from self._update_state(heating_time)

    def _set_timer(self, when):
        if self._stop_timer:
            self.hass.async_run_job(self._stop_timer)
        self._stop_timer = evt.async_track_point_in_time(self.hass, self._timer_handler, when)
