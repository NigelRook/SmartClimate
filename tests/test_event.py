'''
Tests preheat events

All tests assume following formula for time to heat:
t = 1800(g - s) + 60(s - o) + 900
    = 1800g - 1740s - 60o + 900

where t = time to heat in seconds
        g = goal temperature in *C
        s = starting temperature in *C
        o = outside temperature in *C

for tests with no o, s == o
'''
from zoneimpl import ZoneImpl
from .common import FakeStore, FakeHass, time_of_day

# pylint: disable=global-statement
# pylint: disable=invalid-name
hass = None
store = None

def setup_function():
    '''Initialize values for this test case class.'''
    global hass, store
    hass = FakeHass()
    hass.args = {
        'store': 'store',
        'entity_id': 'climate.test'
    }
    store = FakeStore()
    hass.apps['store'] = store

def test_preheat_event():
    hass.time = time_of_day(hour=4)
    hass.states['climate.test'] = {'state': 'Manual', 'attributes': {'temperature':18.0, 'current_temperature':20.5}}
    datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':2700.0, 'sensor_readings':[]},
                  {'start_temp':19.0, 'target_temp':20.0, 'duration_s':2700.0, 'sensor_readings':[]},
                  {'start_temp':18.0, 'target_temp':20.0, 'duration_s':4500.0, 'sensor_readings':[]}]
    store.data['test'] = {'datapoints': datapoints}
    ZoneImpl(hass)
    hass.trigger_event_callback('smartclimate.set_preheat',
                                {'zone': 'test', 'name': 'test', 'type': 'event',
                                 'target_temp': '21', 'target_time': '07:00'})
    hass.advance_time(time_of_day(6, 29, 59))
    assert events() == []
    hass.advance_time(time_of_day(6, 30))
    assert events() == [{'event': 'smartclimate.start_preheat', 'data':{'name': 'test', 'target_temp': 21}}]

def test_clear_preheat_event():
    hass.time = time_of_day(hour=4)
    hass.states['climate.test'] = {'state': 'Manual', 'attributes': {'temperature':18.0, 'current_temperature':20.5}}
    datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':2700.0, 'sensor_readings':[]},
                  {'start_temp':19.0, 'target_temp':20.0, 'duration_s':2700.0, 'sensor_readings':[]},
                  {'start_temp':18.0, 'target_temp':20.0, 'duration_s':4500.0, 'sensor_readings':[]}]
    store.data['test'] = {'datapoints': datapoints}
    ZoneImpl(hass)
    hass.trigger_event_callback('smartclimate.set_preheat',
                                {'zone': 'test', 'name': 'test', 'type': 'event',
                                 'target_temp': '21', 'target_time': '07:00'})
    hass.trigger_event_callback('smartclimate.clear_preheat', {'zone': 'test', 'name': 'test'})
    hass.advance_time(time_of_day(6, 30))
    assert events() == []

def test_preheat_event_default_duration():
    hass.time = time_of_day(hour=4)
    hass.states['climate.test'] = {'state': 'Manual', 'attributes': {'temperature':18.0, 'current_temperature':20.5}}
    ZoneImpl(hass)
    hass.trigger_event_callback('smartclimate.set_preheat',
                                {'zone': 'test', 'name': 'test', 'type': 'event',
                                 'target_temp': '21', 'target_time': '07:00'})
    hass.advance_time(time_of_day(5, 59, 59))
    assert events() == []
    hass.advance_time(time_of_day(6, 00))
    assert events() == [{'event': 'smartclimate.start_preheat', 'data':{'name': 'test', 'target_temp': 21}}]

def test_preheat_event_updates_trigger_time_on_temp_change():
    hass.time = time_of_day(hour=4)
    hass.states['climate.test'] = {'state': 'Manual', 'attributes': {'temperature':18.0, 'current_temperature':20.0}}
    datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':2700.0, 'sensor_readings':[]},
                  {'start_temp':19.0, 'target_temp':20.0, 'duration_s':2700.0, 'sensor_readings':[]},
                  {'start_temp':18.0, 'target_temp':20.0, 'duration_s':4500.0, 'sensor_readings':[]}]
    store.data['test'] = {'datapoints': datapoints}
    ZoneImpl(hass)
    hass.trigger_event_callback('smartclimate.set_preheat',
                                {'zone': 'test', 'name': 'test', 'type': 'event',
                                 'target_temp': '21', 'target_time': '07:00'})

    old_state = hass.states['climate.test']
    new_state = {'state': 'Manual', 'attributes': {'temperature':18.0, 'current_temperature':20.5}}
    hass.states['climate.test'] = new_state
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    hass.advance_time(time_of_day(6, 29, 59))
    assert events() == []
    hass.advance_time(time_of_day(6, 30))
    assert events() == [{'event': 'smartclimate.start_preheat', 'data':{'name': 'test', 'target_temp': 21}}]

def test_preheat_event_with_sensor():
    hass.time = time_of_day(hour=4)
    hass.args['sensors'] = [{'entity_id': 'sensor.test'}]
    hass.states['climate.test'] = {'state': 'Manual', 'attributes': {'temperature':18.0, 'current_temperature':20.5}}
    hass.states['sensor.test'] = {'state': 10.5}
    datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':3060.0,
                   'sensor_readings':[('sensor.test', 12.0)]},
                  {'start_temp':19.0, 'target_temp':20.0, 'duration_s':3060.0,
                   'sensor_readings':[('sensor.test', 13.0)]},
                  {'start_temp':18.0, 'target_temp':20.0, 'duration_s':5100.0,
                   'sensor_readings':[('sensor.test', 8.0)]},
                  {'start_temp':20.0, 'target_temp':21.0, 'duration_s':2940.0,
                   'sensor_readings':[('sensor.test', 16.0)]}]
    store.data['test'] = {'datapoints': datapoints}
    ZoneImpl(hass)
    hass.trigger_event_callback('smartclimate.set_preheat',
                                {'zone': 'test', 'name': 'test', 'type': 'event',
                                 'target_temp': '21', 'target_time': '07:00'})
    hass.advance_time(time_of_day(6, 19, 59))
    assert events() == []
    hass.advance_time(time_of_day(6, 20))
    assert events() == [{'event': 'smartclimate.start_preheat', 'data':{'name': 'test', 'target_temp': 21}}]

def test_preheat_event_with_named_sensor():
    hass.time = time_of_day(hour=4)
    hass.args['sensors'] = [{'name': 'test', 'entity_id': 'sensor.test'}]
    hass.states['climate.test'] = {'state': 'Manual', 'attributes': {'temperature':18.0, 'current_temperature':20.5}}
    hass.states['sensor.test'] = {'state': 10.5}
    datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':3060.0,
                   'sensor_readings':[('test', 12.0)]},
                  {'start_temp':19.0, 'target_temp':20.0, 'duration_s':3060.0,
                   'sensor_readings':[('test', 13.0)]},
                  {'start_temp':18.0, 'target_temp':20.0, 'duration_s':5100.0,
                   'sensor_readings':[('test', 8.0)]},
                  {'start_temp':20.0, 'target_temp':21.0, 'duration_s':2940.0,
                   'sensor_readings':[('test', 16.0)]}]
    store.data['test'] = {'datapoints': datapoints}
    ZoneImpl(hass)
    hass.trigger_event_callback('smartclimate.set_preheat',
                                {'zone': 'test', 'name': 'test', 'type': 'event',
                                 'target_temp': '21', 'target_time': '07:00'})
    hass.advance_time(time_of_day(6, 19, 59))
    assert events() == []
    hass.advance_time(time_of_day(6, 20))
    assert events() == [{'event': 'smartclimate.start_preheat', 'data':{'name': 'test', 'target_temp': 21}}]

def test_preheat_event_with_ttribute_sensor():
    hass.time = time_of_day(hour=4)
    hass.args['sensors'] = [{'entity_id': 'sensor.test', 'attribute': 'attr'}]
    hass.states['climate.test'] = {'state': 'Manual', 'attributes': {'temperature':18.0, 'current_temperature':20.5}}
    hass.states['sensor.test'] = {'state': 'whatever', 'attributes': {'attr': 10.5}}
    datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':3060.0,
                   'sensor_readings':[('sensor.test.attr', 12.0)]},
                  {'start_temp':19.0, 'target_temp':20.0, 'duration_s':3060.0,
                   'sensor_readings':[('sensor.test.attr', 13.0)]},
                  {'start_temp':18.0, 'target_temp':20.0, 'duration_s':5100.0,
                   'sensor_readings':[('sensor.test.attr', 8.0)]},
                  {'start_temp':20.0, 'target_temp':21.0, 'duration_s':2940.0,
                   'sensor_readings':[('sensor.test.attr', 16.0)]}]
    store.data['test'] = {'datapoints': datapoints}
    ZoneImpl(hass)
    hass.trigger_event_callback('smartclimate.set_preheat',
                                {'zone': 'test', 'name': 'test', 'type': 'event',
                                 'target_temp': '21', 'target_time': '07:00'})
    hass.advance_time(time_of_day(6, 19, 59))
    assert events() == []
    hass.advance_time(time_of_day(6, 20))
    assert events() == [{'event': 'smartclimate.start_preheat', 'data':{'name': 'test', 'target_temp': 21}}]

def test_preheat_event_with_sensor_reschedules_on_sensor_change():
    hass.time = time_of_day(hour=4)
    hass.args['sensors'] = [{'entity_id': 'sensor.test'}]
    hass.states['climate.test'] = {'state': 'Manual', 'attributes': {'temperature':18.0, 'current_temperature':20.5}}
    hass.states['sensor.test'] = {'state': 10}
    datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':3060.0,
                   'sensor_readings':[('sensor.test', 12.0)]},
                  {'start_temp':19.0, 'target_temp':20.0, 'duration_s':3060.0,
                   'sensor_readings':[('sensor.test', 13.0)]},
                  {'start_temp':18.0, 'target_temp':20.0, 'duration_s':5100.0,
                   'sensor_readings':[('sensor.test', 8.0)]},
                  {'start_temp':20.0, 'target_temp':21.0, 'duration_s':2940.0,
                   'sensor_readings':[('sensor.test', 16.0)]}]
    store.data['test'] = {'datapoints': datapoints}
    ZoneImpl(hass)
    hass.trigger_event_callback('smartclimate.set_preheat',
                                {'zone': 'test', 'name': 'test', 'type': 'event',
                                 'target_temp': '21', 'target_time': '07:00'})

    old_state = hass.states['sensor.test']
    new_state = {'state': 10.5}
    hass.states['sensor.test'] = new_state
    hass.trigger_state_callback('sensor.test', None, old_state, new_state)

    hass.advance_time(time_of_day(6, 19, 59))
    assert events() == []
    hass.advance_time(time_of_day(6, 20))
    assert events() == [{'event': 'smartclimate.start_preheat', 'data':{'name': 'test', 'target_temp': 21}}]

def test_preheat_event_can_immediately_trigger():
    hass.time = time_of_day(6, 40)
    hass.states['climate.test'] = {'state': 'Manual', 'attributes': {'temperature':18.0, 'current_temperature':20.5}}
    datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':2700.0, 'sensor_readings':[]},
                  {'start_temp':19.0, 'target_temp':20.0, 'duration_s':2700.0, 'sensor_readings':[]},
                  {'start_temp':18.0, 'target_temp':20.0, 'duration_s':4500.0, 'sensor_readings':[]}]
    store.data['test'] = {'datapoints': datapoints}
    ZoneImpl(hass)
    hass.trigger_event_callback('smartclimate.set_preheat',
                                {'zone': 'test', 'name': 'test', 'type': 'event',
                                 'target_temp': 21, 'target_time': '07:00'})
    assert events() == [{'event': 'smartclimate.start_preheat', 'data':{'name': 'test', 'target_temp': 21}}]

def test_preheat_event_after_trigger_time_triggers_next_day():
    hass.time = time_of_day(7, 1)
    hass.states['climate.test'] = {'state': 'Manual', 'attributes': {'temperature':18.0, 'current_temperature':20.5}}
    datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':2700.0, 'sensor_readings':[]},
                  {'start_temp':19.0, 'target_temp':20.0, 'duration_s':2700.0, 'sensor_readings':[]},
                  {'start_temp':18.0, 'target_temp':20.0, 'duration_s':4500.0, 'sensor_readings':[]}]
    store.data['test'] = {'datapoints': datapoints}
    ZoneImpl(hass)
    hass.trigger_event_callback('smartclimate.set_preheat',
                                {'zone': 'test', 'name': 'test', 'type': 'event',
                                 'target_temp': '21', 'target_time': '07:00'})
    assert events() == []
    hass.advance_time(time_of_day(6, 29, 59, extradays=1))
    assert events() == []
    hass.advance_time(time_of_day(6, 30, extradays=1))
    assert events() == [{'event': 'smartclimate.start_preheat', 'data':{'name': 'test', 'target_temp': 21}}]

def events():
    return [event for event in hass.fired_events if event['event'] == 'smartclimate.start_preheat']
