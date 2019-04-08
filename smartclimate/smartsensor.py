import logging

_LOGGER = logging.getLogger(__name__)

class SmartSensor:
    '''binary sensor which turns on when preheat should begin'''
    def __init__(self, name, target_temp, parent):
        self._name = name
        self._parent = parent
        self._target_temp = target_temp
        self.update()

    def update(self):
        '''update sensor state'''
        prediction = self._parent.predict(self._target_temp)
        prediction = prediction if prediction is not None else self._parent.default_preheat
        attributes = {'target_temp': self._target_temp}
        _LOGGER.warning("setting state for %s to %s with attrs %s", 'sensor.'+self._name, prediction, attributes)
        self._parent.hass.set_state('sensor.'+self._name, state=prediction, attributes=attributes)

    def cancel(self):
        '''clear state'''
        self._parent.hass.set_state('sensor.'+self._name, state='unknown')
