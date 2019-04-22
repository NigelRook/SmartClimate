class SensorSet:
    '''sensors for a particular room'''
    def __init__(self, parent, sensors):
        self._parent = parent
        self._sensors = sensors

    def __iter__(self):
        return iter(self._sensors)

    def __len__(self):
        return len(self._sensors)

    def get_readings(self):
        '''return readings for all sensors, or None on error'''
        sensor_readings = [(self._get_sensor_name(sensor), self._read_sensor(sensor))
                           for sensor in self._sensors]

        if None in (value for (_, value) in sensor_readings):
            return None

        return sensor_readings

    @staticmethod
    def _get_sensor_name(sensor):
        if 'name' in sensor:
            return sensor['name']
        elif 'attribute' in sensor:
            return '{}.{}'.format(sensor['entity_id'], sensor['attribute'])
        else:
            return sensor['entity_id']

    def _read_sensor(self, sensor):
        if 'attribute' in sensor:
            value = self._parent.hass.get_state(sensor['entity_id'], attribute=sensor['attribute'])
            return float(value) if value is not None else None

        value = self._parent.hass.get_state(sensor['entity_id'])
        try:
            return float(value)
        except TypeError:
            return None
