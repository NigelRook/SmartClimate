import logging
from datetime import timezone

_LOGGER = logging.getLogger(__name__)

class Tracker:
    '''Class for tracking temperature changes to learn from'''
    IDLE = 'idle'
    TRACKING = 'tracking'

    def __init__(self, entity_id, sensors, parent):
        self._entity_id = entity_id
        self._sensors = sensors
        self._parent = parent

        self._tracking_state = self.IDLE

        self._updates_listener = None
        self._start_temp = None
        self._target_temp = None
        self._sensor_readings = None
        self._tracking_started_time = None

    def handle_update(self, old_state, new_state):
        '''handle state update of the tracked climate entity'''
        _LOGGER.debug('new state for %s: curr=%s, target=%s',
                      self._entity_id,
                      new_state["attributes"]["current_temperature"],
                      new_state["attributes"]["temperature"])

        if not old_state:
            return

        old_temp = new_temp = current_temp = None
        try:
            old_temp = float(old_state["attributes"]["temperature"])
            new_temp = float(new_state["attributes"]["temperature"])
            current_temp = float(new_state["attributes"]["current_temperature"])
        except (KeyError, ValueError, TypeError):
            return

        if self._tracking_state == self.IDLE:
            self._handle_idle_update(old_temp, new_temp, current_temp)
        elif self._tracking_state == self.TRACKING:
            if float(new_state["attributes"]["temperature"]) == self._target_temp:
                self._handle_tracked_temp_change(current_temp)
            else:
                self._handle_tracked_target_temp_change(new_temp, current_temp)

    def _handle_idle_update(self, old_temp, new_temp, current_temp):
        if not self._should_begin_monitoring(old_temp, new_temp, current_temp):
            return

        self._target_temp = new_temp
        self._start_temp = current_temp
        self._sensor_readings = self._sensors.get_readings()
        if self._sensor_readings is None:
            return

        self._tracking_state = self.TRACKING
        self._tracking_started_time = self._parent.hass.datetime().astimezone(timezone.utc)

        _LOGGER.info('Tracking %s from %s to %s',
                     self._entity_id, self._start_temp, self._target_temp)
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
            _LOGGER.info("Tracking aborted for %s - no temperature change", self._entity_id)
            return

        now = self._parent.hass.datetime().astimezone(timezone.utc)
        duration_s = (now - self._tracking_started_time).total_seconds()
        _LOGGER.info("Tracking complete for %s, took %s seconds",
                     self._entity_id, duration_s)
        self._parent.add_datapoint(end_temp, self._start_temp, self._sensor_readings, duration_s)

    @staticmethod
    def _should_begin_monitoring(old_temp, new_temp, current_temp):
        return new_temp > old_temp + 0.5 and new_temp > current_temp
