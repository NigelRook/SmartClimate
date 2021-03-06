from hasslog import HassLog
from sensorset import SensorSet
from tracker import Tracker
from predictor import LinearPredictor
from smartevent import SmartEvent
from smartsensor import SmartSensor
from appdaemon_hass_interface import AppDaemonHassInterface

class ZoneImpl(HassLog):
    '''Implementation of Zone'''

    default_preheat = 3600

    def __init__(self, app, store):
        super().__init__(app)
        self.hass = AppDaemonHassInterface(app)
        self._preheats = {}
        self._climate_entity = self.hass.config["entity_id"]
        self._sensors = SensorSet(self, self.hass.config.get("sensors", []))

        self.info("Initialising zone {} for entity {} with {} sensors",
                  self.hass.name, self._climate_entity, len(self._sensors))

        self._tracker = Tracker(self._climate_entity, self._sensors, self)

        self._store = store
        datapoints = None
        with self._store.lock:
            if self.hass.name not in self._store.data:
                self._store.data[self.hass.name] = {}
            if "datapoints" not in self._store.data[self.hass.name]:
                self._store.data[self.hass.name]["datapoints"] = []

            datapoints = self._store.data[self.hass.name]["datapoints"]

        self.predictor = LinearPredictor(self.hass.name, self)
        self.predictor.learn(datapoints)

        self.hass.listen_state(self._handle_climate_updated, self._climate_entity, attribute="all")
        for sensor in self._sensors:
            self._listen_sensor_state(sensor)

        self.hass.listen_event(self._handle_set_preheat, "smartclimate.set_preheat", zone=self.hass.name)
        self.hass.listen_event(self._handle_clear_preheat, "smartclimate.clear_preheat")

        self.hass.fire_event("smartclimate.up", zone=self.hass.name)

    def _listen_sensor_state(self, sensor):
        if 'attribute' in sensor:
            self.hass.listen_state(self._handle_sensor_updated, sensor['entity_id'], attribute=sensor['attribute'])
        else:
            self.hass.listen_state(self._handle_sensor_updated, sensor['entity_id'])

    def _handle_climate_updated(self, entity_id, new, old):
        self._tracker.handle_update(old, new)
        for _, preheat in self._preheats.items():
            preheat.update()

    def _handle_sensor_updated(self, entity_id, new, old):
        self.debug("Sensor entity {} updated", entity_id)
        for _, preheat in self._preheats.items():
            preheat.update()

    def _handle_set_preheat(self, event, data):
        if data.get('zone', None) != self.hass.name:
            return

        name = data['name']
        if name in self._preheats:
            self.debug("Cancelling existing preheat {}", name)
            self._preheats[name].cancel()

        target_temp = float(data['target_temp'])
        preheat_type = data.get('type', 'event')
        if preheat_type == 'event':
            target_time = data['target_time']
            self.info("Adding preheat event {} temp={}, time={}", name, target_temp, target_time)
            self._preheats[name] = SmartEvent(name, target_temp, target_time, self)
        elif preheat_type == 'sensor':
            self.info("Adding preheat sensor {} temp={}", name, target_temp)
            self._preheats[name] = SmartSensor(name, target_temp, self)

    def _handle_clear_preheat(self, event, data):
        name = data['name']
        if name in self._preheats:
            self.info("Clearing preheat {}", name)
            self._preheats[name].cancel()
            del self._preheats[name]

    def add_datapoint(self, target_temp, start_temp, sensor_readings, duration_s):
        '''add a datapoint to the predictor'''
        datapoint = {
            'start_temp' : start_temp,
            'target_temp' : target_temp,
            'sensor_readings': sensor_readings,
            'duration_s' : duration_s
        }
        datapoints = None
        with self._store.lock:
            self._store.data[self.hass.name]['datapoints'].append(datapoint)
            self._store.save()
            datapoints = self._store.data[self.hass.name]['datapoints']
        self.predictor.learn(datapoints)

    def predict(self, target_temp):
        '''predict the number of seconds required to reach target_temp'''
        current_temp = self.hass.get_state(self._climate_entity, attribute='current_temperature')
        if current_temp is None:
            return None
        sensor_readings = self._sensors.get_readings()
        return self.predictor.predict(target_temp, current_temp, sensor_readings)
