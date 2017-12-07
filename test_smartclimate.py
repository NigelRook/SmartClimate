''' Tests for the smartclimate component '''
# pylint: disable=locally-disabled, line-too-long, invalid-name, R0201, R0904
import os
from shutil import copy2, rmtree
import pickle
import datetime
import unittest
from copy import deepcopy

from ha_test_common import (
    get_test_config_dir, get_test_home_assistant, mock_state_change_event, fire_time_changed)

from homeassistant.core import State
from homeassistant.setup import async_setup_component
from homeassistant.util.async import run_coroutine_threadsafe
from homeassistant.util.dt import DEFAULT_TIME_ZONE

import smartclimate

ENTITY_ID = 'climate.test'

SIMPLE_CONFIG = {
    'smartclimate': {
        'models': {
            'test': {
                'entity_id': ENTITY_ID
            }
        },
        'schedules': {
            'test': {
                'model': 'test',
                'temperature': '21',
                'start': '7:00',
                'end': '8:00'
            }
        }
    }
}

class TestSmartClimate(unittest.TestCase):
    '''
    Tests the smartclimate component.

    All tests assume following formula for time to heat:
    t = 1800(g - s) + 60(s - o) + 900
      = 1800g - 1740s - 60o + 900

    where t = time to heat in seconds
          g = goal temperature in *C
          s = starting temperature in *C
          o = outside temperature in *C

    for tests with no o, s == o
    '''

    setUpClassRun = False
    @classmethod
    def setUpClass(cls):
        config_path = get_test_config_dir()
        if os.path.isdir(config_path):
            rmtree(config_path)
        os.mkdir(config_path)
        custom_components_path = os.path.join(config_path, 'custom_components')
        os.mkdir(custom_components_path)
        copy2(os.path.join(os.path.dirname(__file__), 'smartclimate.py'), custom_components_path)
        cls.setUpClassRun = True

    @classmethod
    def tearDownClass(cls):
        rmtree(get_test_config_dir())
        cls.setUpClassRun = False

    def setUp(self):
        '''Initialize values for this test case class.'''
        if not self.setUpClassRun:
            self.setUpClass()
        self.maxDiff = 2000
        self.hass = get_test_home_assistant()
        self.store = get_test_config_dir('smartclimate.pickle')

    def tearDown(self):
        '''Stop everything that was started.'''
        self.hass.stop()
        if os.path.isfile(self.store):
            os.remove(self.store)

    def init(self, config):
        '''Init smartclimate component'''
        return run_coroutine_threadsafe(
            async_setup_component(self.hass, 'smartclimate', config), self.hass.loop).result()

    def block_till_done(self):
        '''Block the hass loop until everything is processed'''
        return self.hass.block_till_done()

    def assertState(self, entity_id, expected_state, attributes=None):
        '''Assert state is as expected'''
        state = self.hass.states.get(entity_id)
        self.assertEqual(state.state, expected_state)
        if attributes is None:
            return
        state_attr_dict = {key: value for key, value in state.attributes.items()}
        self.assertEqual(state_attr_dict, attributes)

    def assertHeatingTime(self, entity_id, expected):
        '''assert the scheduled on time is correct'''
        state = self.hass.states.get(entity_id)
        self.assertEqual(state.attributes['heating_time'], expected)

    def assertOnTime(self, entity_id, expected_time):
        '''assert the scheduled on time is correct'''
        state = self.hass.states.get(entity_id)
        self.assertEqual(state.attributes['next_on'], expected_time)

    @staticmethod
    def relative_time(time_s):
        '''Provide relative timestamps in seconds'''
        return datetime.datetime.utcfromtimestamp(1512043200 + time_s)

    @staticmethod
    def local_datetime(time_str):
        '''Return a local datetime at time_str'''
        parts = time_str.split(':')
        return datetime.datetime.now().replace(hour=int(parts[0]), minute=int(parts[1]),
                                               second=0, microsecond=0, tzinfo=DEFAULT_TIME_ZONE)

    def simple_init_data(self):
        '''Init data non-empty store for simple config'''
        return self.set_data([{'start_temp': 18., 'target_temp': 20., 'sensor_readings': [], 'duration_s': 5100.0}])

    def set_data(self, datapoints):
        '''set saved data'''
        data = {
            '_version': 1,
            'test': {'datapoints': datapoints}
        }
        with open(self.store, 'wb') as file:
            pickle.dump(data, file)
        return data

    def test_simple_config_validation(self):
        '''Test validation of a valid, complex config'''
        smartclimate.CONFIG_SCHEMA(SIMPLE_CONFIG)

    def test_complex_config_validation(self):
        '''Test validation of a valid, complex config'''
        config = {
            'smartclimate': {
                'models': {
                    'test1': {
                        'entity_id': ENTITY_ID,
                        'sensors': [
                            {
                                'entity_id': 'sensor.sensor1'
                            },
                            {
                                'entity_id': 'sensor.sensor2',
                                'attribute': 'attr'
                            }
                        ]
                    },
                    'test2': {
                        'entity_id': 'climate.test2'
                    }
                },
                'schedules': {
                    'test_sched_1': {
                        'model': 'test1',
                        'temperature': '14',
                        'start': '11:31:19',
                        'end': '11:31:20'
                    },
                    'test_sched_2': {
                        'model': 'test1',
                        'temperature': '26.1',
                        'start': '23:00',
                        'end': '01:00'
                    }
                }
            }
        }
        smartclimate.CONFIG_SCHEMA(config)

    def test_initial_setup(self):
        '''Test the setup.'''
        response = self.init(SIMPLE_CONFIG)
        self.assertTrue(response)

    @unittest.mock.patch('homeassistant.util.dt.utcnow')
    def test_records_temperature_change(self, mock):
        '''Test a completed temperature shift gets recorded to the store'''
        self.init(SIMPLE_CONFIG)

        old_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 18., 'current_temperature' : 18.})
        new_state = State(ENTITY_ID, 'Manual', {'temperature': 20., 'current_temperature' : 18.})
        mock.return_value = self.relative_time(0)
        mock_state_change_event(self.hass, new_state, old_state)
        self.block_till_done()

        old_state = new_state
        new_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 20., 'current_temperature' : 20.})
        mock.return_value = self.relative_time(5100)
        mock_state_change_event(self.hass, new_state, old_state)
        self.block_till_done()

        self.assertTrue(os.path.isfile(self.store))
        with open(self.store, 'rb') as file:
            data = pickle.load(file)
            self.assertEqual(data, {
                '_version': 1,
                'test': {
                    'datapoints': [{
                        'start_temp': 18.,
                        'target_temp': 20.,
                        'sensor_readings': [],
                        'duration_s': 5100.0
                    }]
                }
            })

    @unittest.mock.patch('homeassistant.util.dt.utcnow')
    def test_aborts_tracking_if_target_temp_changed(self, mock):
        '''nothing is recorded if the target temp is changed while tracking'''
        initial_data = self.simple_init_data()
        self.init(SIMPLE_CONFIG)

        old_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 18., 'current_temperature' : 18.})
        new_state = State(ENTITY_ID, 'Manual', {'temperature': 19., 'current_temperature' : 18.})
        mock.return_value = self.relative_time(0)
        mock_state_change_event(self.hass, new_state, old_state)
        self.block_till_done()

        old_state = new_state
        new_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 18., 'current_temperature' : 18.5})
        mock.return_value = self.relative_time(2400)
        mock_state_change_event(self.hass, new_state, old_state)
        self.block_till_done()

        with open(self.store, 'rb') as file:
            data = pickle.load(file)
            self.assertEqual(data, initial_data)

    @unittest.mock.patch('homeassistant.util.dt.utcnow')
    def test_ignores_intermediate_states(self, mock):
        '''Test a completed temperature shift gets recorded to the store'''
        self.init(SIMPLE_CONFIG)

        old_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 18., 'current_temperature' : 18.})
        new_state = State(ENTITY_ID, 'Manual', {'temperature': 20., 'current_temperature' : 18.})
        mock.return_value = self.relative_time(0)
        mock_state_change_event(self.hass, new_state, old_state)
        self.block_till_done()

        old_state = new_state
        new_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 20., 'current_temperature' : 19.})
        mock.return_value = self.relative_time(5100)
        mock_state_change_event(self.hass, new_state, old_state)
        self.block_till_done()

        old_state = new_state
        new_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 20., 'current_temperature' : 20.})
        mock.return_value = self.relative_time(5100)
        mock_state_change_event(self.hass, new_state, old_state)
        self.block_till_done()

        self.assertTrue(os.path.isfile(self.store))
        with open(self.store, 'rb') as file:
            data = pickle.load(file)
            self.assertEqual(data, {
                '_version': 1,
                'test': {
                    'datapoints': [{
                        'start_temp': 18.,
                        'target_temp': 20.,
                        'sensor_readings': [],
                        'duration_s': 5100.0
                    }]
                }
            })

    @unittest.mock.patch('homeassistant.util.dt.utcnow')
    def test_records_additional_sensors(self, mock):
        '''Test a completed temperature shift gets recorded to the store'''
        config = {
            'smartclimate': {
                'models': {
                    'test': {
                        'entity_id': ENTITY_ID,
                        'sensors': [
                            {
                                'entity_id': 'sensor.sensor1'
                            },
                            {
                                'entity_id': 'sensor.sensor2',
                                'attribute': 'attr'
                            }
                        ]
                    }
                }
            }
        }
        self.init(config)

        self.hass.states.set('sensor.sensor1', '8.0')
        self.hass.states.set('sensor.sensor2', 'on', {'attr': '16.0'})
        old_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 18., 'current_temperature' : 18.})
        new_state = State(ENTITY_ID, 'Manual', {'temperature': 20., 'current_temperature' : 18.})
        mock.return_value = self.relative_time(0)
        mock_state_change_event(self.hass, new_state, old_state)
        self.block_till_done()

        self.hass.states.set('sensor.sensor1', '9.0')
        self.hass.states.set('sensor.sensor2', 'on', {'attr': '17.0'})
        old_state = new_state
        new_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 20., 'current_temperature' : 20.})
        mock.return_value = self.relative_time(5100)
        mock_state_change_event(self.hass, new_state, old_state)
        self.block_till_done()

        self.assertTrue(os.path.isfile(self.store))
        with open(self.store, 'rb') as file:
            data = pickle.load(file)
            self.assertEqual(data, {
                '_version': 1,
                'test': {
                    'datapoints': [{
                        'start_temp': 18.,
                        'target_temp': 20.,
                        'sensor_readings': [
                            ('sensor.sensor1', 8.),
                            ('sensor.sensor2.attr', 16.)
                        ],
                        'duration_s': 5100.0
                    }]
                }
            })



    @unittest.mock.patch('homeassistant.util.dt.utcnow')
    def test_records_temperature_change_for_multiple_entities(self, mock):
        '''Test a completed temperature shift gets recorded to the store for two seperate entities'''
        self.init({
            'smartclimate': {
                'models': {
                    'test1': {
                        'entity_id': 'climate.test1'
                    },
                    'test2': {
                        'entity_id': 'climate.test2'
                    }
                }
            }
        })

        old_state1 = State('climate.test1', 'Smart Schedule', {'temperature': 18., 'current_temperature' : 18.})
        new_state1 = State('climate.test1', 'Manual', {'temperature': 20., 'current_temperature' : 18.})
        mock.return_value = self.relative_time(0)
        mock_state_change_event(self.hass, new_state1, old_state1)
        self.block_till_done()

        old_state2 = State('climate.test2', 'Smart Schedule', {'temperature': 19., 'current_temperature' : 19.})
        new_state2 = State('climate.test2', 'Manual', {'temperature': 21., 'current_temperature' : 19.})
        mock.return_value = self.relative_time(100)
        mock_state_change_event(self.hass, new_state2, old_state2)
        self.block_till_done()

        old_state1 = new_state1
        new_state1 = State('climate.test1', 'Smart Schedule', {'temperature': 20., 'current_temperature' : 20.})
        mock.return_value = self.relative_time(5100)
        mock_state_change_event(self.hass, new_state1, old_state1)
        self.block_till_done()

        old_state2 = new_state1
        new_state2 = State('climate.test2', 'Smart Schedule', {'temperature': 21., 'current_temperature' : 21.})
        mock.return_value = self.relative_time(5201)
        mock_state_change_event(self.hass, new_state2, old_state2)
        self.block_till_done()

        self.assertTrue(os.path.isfile(self.store))
        with open(self.store, 'rb') as file:
            data = pickle.load(file)
            self.assertEqual(data, {
                '_version': 1,
                'test1': {
                    'datapoints': [{
                        'start_temp': 18.,
                        'target_temp': 20.,
                        'sensor_readings': [],
                        'duration_s': 5100.0
                    }]
                },
                'test2': {
                    'datapoints': [{
                        'start_temp': 19.,
                        'target_temp': 21.,
                        'sensor_readings': [],
                        'duration_s': 5101.0
                    }]
                }
            })

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_initial_schedule_before_on(self, mock):
        '''Ensure initial state is sensible'''
        mock.return_value = self.local_datetime('04:00')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':20.0, 'current_temperature':19.0})
        response = self.init(SIMPLE_CONFIG)
        self.assertTrue(response)
        self.block_till_done()
        self.assertState('smartclimate.schedule_test', 'off', {
            'friendly_name': 'test',
            'model': 'test',
            'temperature': str(21.0),
            'start': '07:00',
            'end': '08:00',
            'heating_time': 3600,
            'next_on': '06:00'
        })

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_initial_schedule_after_off(self, mock):
        '''Ensure initial state is sensible'''
        mock.return_value = self.local_datetime('12:00')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':20.0, 'current_temperature':19.0})
        response = self.init(SIMPLE_CONFIG)
        self.assertTrue(response)
        self.block_till_done()
        self.assertState('smartclimate.schedule_test', 'off', {
            'friendly_name': 'test',
            'model': 'test',
            'temperature': str(21.0),
            'start': '07:00',
            'end': '08:00',
            'heating_time': 3600,
            'next_on': '06:00'
        })

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_initial_schedule_state_on(self, mock):
        '''Ensure initial state is sensible'''
        mock.return_value = self.local_datetime('07:30')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':20.0, 'current_temperature':19.0})
        response = self.init(SIMPLE_CONFIG)
        self.assertTrue(response)
        self.block_till_done()
        self.assertState('smartclimate.schedule_test', 'on', {
            'friendly_name': 'test',
            'model': 'test',
            'temperature': str(21.0),
            'start': '07:00',
            'end': '08:00',
            'heating_time': 3600
        })

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_initial_schedule_state_during_warmup(self, mock):
        '''Ensure initial state is sensible'''
        mock.return_value = self.local_datetime('06:30')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':20.0, 'current_temperature':19.0})
        response = self.init(SIMPLE_CONFIG)
        self.assertTrue(response)
        self.block_till_done()
        self.assertState('smartclimate.schedule_test', 'on', {
            'friendly_name': 'test',
            'model': 'test',
            'temperature': str(21.0),
            'start': '07:00',
            'end': '08:00',
            'heating_time': 3600
        })

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_on_time_from_learned_data(self, mock):
        '''basic prediction test'''
        mock.return_value = self.local_datetime('04:00')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':18.0, 'current_temperature':20.5})
        datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':2700.0, 'sensor_readings':[]},
                      {'start_temp':19.0, 'target_temp':20.0, 'duration_s':2700.0, 'sensor_readings':[]},
                      {'start_temp':18.0, 'target_temp':20.0, 'duration_s':4500.0, 'sensor_readings':[]}]
        self.set_data(datapoints)
        response = self.init(SIMPLE_CONFIG)
        self.assertTrue(response)
        self.block_till_done()
        self.assertHeatingTime('smartclimate.schedule_test', 1800)
        self.assertOnTime('smartclimate.schedule_test', '06:30')

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_on_time_changes_if_current_temp_changes(self, mock):
        '''basic prediction test'''
        mock.return_value = self.local_datetime('04:00')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':18.0, 'current_temperature':20.5})
        datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':2700.0, 'sensor_readings':[]},
                      {'start_temp':19.0, 'target_temp':20.0, 'duration_s':2700.0, 'sensor_readings':[]},
                      {'start_temp':18.0, 'target_temp':20.0, 'duration_s':4500.0, 'sensor_readings':[]}]
        self.set_data(datapoints)
        response = self.init(SIMPLE_CONFIG)
        self.assertTrue(response)
        self.block_till_done()
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':18.0, 'current_temperature':20.6})
        old_state = State(ENTITY_ID, 'Smart Schedule', {'temperature':18.0, 'current_temperature':20.5})
        new_state = State(ENTITY_ID, 'Smart Schedule', {'temperature':18.0, 'current_temperature':20.6})
        mock_state_change_event(self.hass, new_state, old_state)
        self.block_till_done()
        self.assertHeatingTime('smartclimate.schedule_test', 1620)
        self.assertOnTime('smartclimate.schedule_test', '06:33')

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_on_time_from_learned_data_with_sensor(self, mock):
        '''prediction test using sensor'''
        config = deepcopy(SIMPLE_CONFIG)
        config['smartclimate']['models']['test']['sensors'] = [{'entity_id':'sensors.test'}]
        mock.return_value = self.local_datetime('04:00')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':18.0, 'current_temperature':20.5})
        self.hass.states.set('sensors.test', 10.5)
        datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':3060.0,
                       'sensor_readings':[('sensors.test', 12.0)]},
                      {'start_temp':19.0, 'target_temp':20.0, 'duration_s':3060.0,
                       'sensor_readings':[('sensors.test', 13.0)]},
                      {'start_temp':18.0, 'target_temp':20.0, 'duration_s':5100.0,
                       'sensor_readings':[('sensors.test', 8.0)]},
                      {'start_temp':20.0, 'target_temp':21.0, 'duration_s':2940.0,
                       'sensor_readings':[('sensors.test', 16.0)]}]
        self.set_data(datapoints)
        response = self.init(config)
        self.assertTrue(response)
        self.block_till_done()
        self.assertHeatingTime('smartclimate.schedule_test', 2400)
        self.assertOnTime('smartclimate.schedule_test', '06:20')

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_on_time_from_learned_data_with_sensor_attribute(self, mock):
        '''prediction test using sensor with value in attribute'''
        config = deepcopy(SIMPLE_CONFIG)
        config['smartclimate']['models']['test']['sensors'] = [{'entity_id':'sensors.test', 'attribute':'temp'}]
        mock.return_value = self.local_datetime('04:00')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':18.0, 'current_temperature':20.5})
        self.hass.states.set('sensors.test', 'sensing', attributes={'temp':10.5})
        datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':3060.0,
                       'sensor_readings':[('sensors.test.temp', 12.0)]},
                      {'start_temp':19.0, 'target_temp':20.0, 'duration_s':3060.0,
                       'sensor_readings':[('sensors.test.temp', 13.0)]},
                      {'start_temp':18.0, 'target_temp':20.0, 'duration_s':5100.0,
                       'sensor_readings':[('sensors.test.temp', 8.0)]},
                      {'start_temp':20.0, 'target_temp':21.0, 'duration_s':2940.0,
                       'sensor_readings':[('sensors.test.temp', 16.0)]}]
        self.set_data(datapoints)
        response = self.init(config)
        self.assertTrue(response)
        self.block_till_done()
        self.assertHeatingTime('smartclimate.schedule_test', 2400)
        self.assertOnTime('smartclimate.schedule_test', '06:20')

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_on_time_changes_if_sensor_reading_changes(self, mock):
        '''prediction updates after sensor reading changes'''
        config = deepcopy(SIMPLE_CONFIG)
        config['smartclimate']['models']['test']['sensors'] = [{'entity_id':'sensors.test'}]
        mock.return_value = self.local_datetime('04:00')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':18.0, 'current_temperature':20.5})
        self.hass.states.set('sensors.test', 10.5)
        datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':3060.0,
                       'sensor_readings':[('sensors.test', 12.0)]},
                      {'start_temp':19.0, 'target_temp':20.0, 'duration_s':3060.0,
                       'sensor_readings':[('sensors.test', 13.0)]},
                      {'start_temp':18.0, 'target_temp':20.0, 'duration_s':5100.0,
                       'sensor_readings':[('sensors.test', 8.0)]},
                      {'start_temp':20.0, 'target_temp':21.0, 'duration_s':2940.0,
                       'sensor_readings':[('sensors.test', 16.0)]}]
        self.set_data(datapoints)
        response = self.init(config)
        self.assertTrue(response)
        self.block_till_done()
        self.hass.states.set('sensors.test', 11.5)
        old_state = State('sensors.test', 10.5)
        new_state = State('sensors.test', 11.5)
        mock_state_change_event(self.hass, new_state, old_state)
        self.block_till_done()
        self.assertHeatingTime('smartclimate.schedule_test', 2340)
        self.assertOnTime('smartclimate.schedule_test', '06:21')

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_on_time_changes_if_sensor_attribute_reading_changes(self, mock):
        '''prediction updates after sensor attribute reading changes'''
        config = deepcopy(SIMPLE_CONFIG)
        config['smartclimate']['models']['test']['sensors'] = [{'entity_id':'sensors.test', 'attribute':'temp'}]
        mock.return_value = self.local_datetime('04:00')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':18.0, 'current_temperature':20.5})
        self.hass.states.set('sensors.test', 'sensing', attributes={'temp':10.5})
        datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':3060.0,
                       'sensor_readings':[('sensors.test.temp', 12.0)]},
                      {'start_temp':19.0, 'target_temp':20.0, 'duration_s':3060.0,
                       'sensor_readings':[('sensors.test.temp', 13.0)]},
                      {'start_temp':18.0, 'target_temp':20.0, 'duration_s':5100.0,
                       'sensor_readings':[('sensors.test.temp', 8.0)]},
                      {'start_temp':20.0, 'target_temp':21.0, 'duration_s':2940.0,
                       'sensor_readings':[('sensors.test.temp', 16.0)]}]
        self.set_data(datapoints)
        response = self.init(config)
        self.assertTrue(response)
        self.block_till_done()
        self.hass.states.set('sensors.test', 'sensing', attributes={'temp':11.5})
        old_state = State('sensors.test', 'sensing', {'temp':10.5})
        new_state = State('sensors.test', 'sensing', {'temp':11.5})
        mock_state_change_event(self.hass, new_state, old_state)
        self.block_till_done()
        self.assertHeatingTime('smartclimate.schedule_test', 2340)
        self.assertOnTime('smartclimate.schedule_test', '06:21')

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_state_transition_at_on_time(self, mock):
        '''switches to on at next_on'''
        mock.return_value = self.local_datetime('04:00')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':18.0, 'current_temperature':20.5})
        datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':2700.0, 'sensor_readings':[]},
                      {'start_temp':19.0, 'target_temp':20.0, 'duration_s':2700.0, 'sensor_readings':[]},
                      {'start_temp':18.0, 'target_temp':20.0, 'duration_s':4500.0, 'sensor_readings':[]}]
        self.set_data(datapoints)
        response = self.init(SIMPLE_CONFIG)
        self.assertTrue(response)
        self.block_till_done()
        self.assertOnTime('smartclimate.schedule_test', '06:30')
        mock.return_value = self.local_datetime('06:30')
        fire_time_changed(self.hass, self.local_datetime('06:30'))
        self.block_till_done()
        self.assertState('smartclimate.schedule_test', 'on')

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_state_transition_at_off_time(self, mock):
        '''switches to off at end time'''
        mock.return_value = self.local_datetime('07:30')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':18.0, 'current_temperature':20.5})
        datapoints = [{'start_temp':18.0, 'target_temp':19.0, 'duration_s':2700.0, 'sensor_readings':[]},
                      {'start_temp':19.0, 'target_temp':20.0, 'duration_s':2700.0, 'sensor_readings':[]},
                      {'start_temp':18.0, 'target_temp':20.0, 'duration_s':4500.0, 'sensor_readings':[]}]
        self.set_data(datapoints)
        response = self.init(SIMPLE_CONFIG)
        self.assertTrue(response)
        self.block_till_done()
        self.assertState('smartclimate.schedule_test', 'on')
        mock.return_value = self.local_datetime('08:00')
        fire_time_changed(self.hass, self.local_datetime('08:00'))
        self.block_till_done()
        self.assertState('smartclimate.schedule_test', 'off')
