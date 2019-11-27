'''
Tests tracking of temperature changes.

All tests assume following formula for time to heat:
t = 1800(g - s) + 60(s - o) + 900
    = 1800g - 1740s - 60o + 900

where t = time to heat in seconds
        g = goal temperature in *C
        s = starting temperature in *C
        o = outside temperature in *C

for tests with no o, s == o
'''
from copy import deepcopy
from zoneimpl import ZoneImpl
from .common import FakeStore, FakeHass, relative_time

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

def test_records_temperature_change():
    '''Test a completed temperature shift gets recorded to the store'''
    ZoneImpl(hass)

    old_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 18., 'current_temperature' : 18.}}
    new_state = {'state': 'Manual', 'attributes': {'temperature': 20., 'current_temperature' : 18.}}
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    old_state = new_state
    new_state = {'state': 'Smart Schedule', 'attributes' :{'temperature': 20., 'current_temperature' : 20.}}
    hass.time = relative_time(5100)
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    assert store.saved
    assert store.data == {
        '_version': 1,
        'test': {
            'datapoints': [{
                'start_temp': 18.,
                'target_temp': 20.,
                'sensor_readings': [],
                'duration_s': 5100.0
            }]
        }
    }

def test_completes_tracking_if_target_temp_changed_to_below_current():
    '''nothing is recorded if the target temp is changed while tracking'''
    ZoneImpl(hass)

    old_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 18., 'current_temperature' : 18.}}
    new_state = {'state': 'Manual', 'attributes': {'temperature': 19., 'current_temperature' : 18.}}
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    old_state = new_state
    new_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 18., 'current_temperature' : 18.5}}
    hass.time = relative_time(1800)
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    assert store.saved
    assert store.data == {
        '_version': 1,
        'test': {
            'datapoints': [{
                'start_temp': 18.,
                'target_temp': 18.5,
                'sensor_readings': [],
                'duration_s': 1800.0
            }]
        }
    }

def test_conitinues_tracking_if_target_temp_lowered():
    '''nothing is recorded if the target temp is changed while tracking'''
    ZoneImpl(hass)

    old_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 18., 'current_temperature' : 18.}}
    new_state = {'state': 'Manual', 'attributes': {'temperature': 20., 'current_temperature' : 18.}}
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    old_state = new_state
    new_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 19., 'current_temperature' : 18.5}}
    hass.time = relative_time(1800)
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    old_state = new_state
    new_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 19., 'current_temperature' : 19.}}
    hass.time = relative_time(2700)
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    assert store.saved
    assert store.data == {
        '_version': 1,
        'test': {
            'datapoints': [{
                'start_temp': 18.,
                'target_temp': 19.,
                'sensor_readings': [],
                'duration_s': 2700.0
            }]
        }
    }

def test_conitinues_tracking_if_target_temp_raised():
    '''nothing is recorded if the target temp is changed while tracking'''
    ZoneImpl(hass)

    old_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 18., 'current_temperature' : 18.}}
    new_state = {'state': 'Manual', 'attributes': {'temperature': 20., 'current_temperature' : 18.}}
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    old_state = new_state
    new_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 21., 'current_temperature' : 18.5}}
    hass.time = relative_time(1800)
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    old_state = new_state
    new_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 21., 'current_temperature' : 21.}}
    hass.time = relative_time(6300)
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    assert store.saved
    assert store.data == {
        '_version': 1,
        'test': {
            'datapoints': [{
                'start_temp': 18.,
                'target_temp': 21.,
                'sensor_readings': [],
                'duration_s': 6300.0
            }]
        }
    }

def test_ignores_intermediate_states():
    '''Test a completed temperature shift gets recorded to the store'''
    ZoneImpl(hass)

    old_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 18., 'current_temperature' : 18.}}
    new_state = {'state': 'Manual', 'attributes': {'temperature': 20., 'current_temperature' : 18.}}
    hass.time = relative_time(0)
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    old_state = new_state
    new_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 20., 'current_temperature' : 19.}}
    hass.time = relative_time(5100)
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    old_state = new_state
    new_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 20., 'current_temperature' : 20.}}
    hass.time = relative_time(5100)
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    assert store.saved
    assert store.data == {
        '_version': 1,
        'test': {
            'datapoints': [{
                'start_temp': 18.,
                'target_temp': 20.,
                'sensor_readings': [],
                'duration_s': 5100.0
            }]
        }
    }

def test_records_additional_sensors():
    '''Test a completed temperature shift gets recorded to the store'''
    hass.args['sensors'] = [
        {'entity_id': 'sensor.sensor1'},
        {'entity_id': 'sensor.sensor2', 'attribute': 'attr'},
        {'name': 'test_sensor', 'entity_id': 'sensor.sensor3'}
    ]
    ZoneImpl(hass)

    hass.states['sensor.sensor1'] = {'state': 8.0}
    hass.states['sensor.sensor2'] = {'state': 'on', 'attributes': {'attr': '16.0'}}
    hass.states['sensor.sensor3'] = {'state': '12.0'}
    old_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 18., 'current_temperature' : 18.}}
    new_state = {'state': 'Manual', 'attributes': {'temperature': 20., 'current_temperature' : 18.}}
    hass.time = relative_time(0)
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    hass.states['sensor.sensor1'] = {'state': '9.0'}
    hass.states['sensor.sensor2'] = {'state': 'on', 'attributes':{'attr': '17.0'}}
    hass.states['sensor.sensor3'] = {'state': '13.0'}
    old_state = new_state
    new_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 20., 'current_temperature' : 20.}}
    hass.time = relative_time(5100)
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    assert store.saved
    assert store.data == {
        '_version': 1,
        'test': {
            'datapoints': [{
                'start_temp': 18.,
                'target_temp': 20.,
                'sensor_readings': [
                    ('sensor.sensor1', 8.),
                    ('sensor.sensor2.attr', 16.),
                    ('test_sensor', 12.)
                ],
                'duration_s': 5100.0
            }]
        }
    }

def test_doesnt_record_missing_sensor_reading():
    '''Test a completed temperature shift gets recorded to the store'''
    store.data[hass.name] = {
        'datapoints': [
            {
                'start_temp': 18.,
                'target_temp': 20.,
                'sensor_readings': [('sensor.sensor1', 8.0)],
                'duration_s': 5100.0
            }
        ]
    }
    initial_data = deepcopy(store.data)
    hass.args['sensors'] = [{'entity_id': 'sensor.sensor1'}]
    ZoneImpl(hass)

    #hass.states.set('sensor.sensor1', '8.0')
    old_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 18., 'current_temperature' : 18.}}
    new_state = {'state': 'Manual', 'attributes': {'temperature': 20., 'current_temperature' : 18.}}
    hass.time = relative_time(0)
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    old_state = new_state
    new_state = {'state': 'Smart Schedule', 'attributes': {'temperature': 20., 'current_temperature' : 20.}}
    hass.time = relative_time(5100)
    hass.trigger_state_callback('climate.test', None, old_state, new_state)

    assert store.saved is False
    assert store.data == initial_data
