''' Tests for the smartclimate component '''
# pylint: disable=locally-disabled, line-too-long, invalid-name, R0201, R0904
import os
import pickle
import datetime
import unittest

from homeassistant.core import State
from homeassistant.setup import async_setup_component
from homeassistant.util.async import run_coroutine_threadsafe

import smartclimate

from . import setup_custom_components, cleanup_custom_components
from .common import (
    get_test_config_dir, get_test_home_assistant, mock_state_change_event)

ENTITY_ID = 'climate.test'

SIMPLE_CONFIG = {
    'smartclimate': {
        'test': {
            'entity_id': ENTITY_ID
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
        setup_custom_components()
        cls.setUpClassRun = True

    @classmethod
    def tearDownClass(cls):
        cleanup_custom_components()
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

    @staticmethod
    def relative_time(time_s):
        '''Provide relative timestamps in seconds'''
        return datetime.datetime.utcfromtimestamp(1512043200 + time_s)

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
                'test1': {
                    'entity_id': 'climate.test1'
                },
                'test2': {
                    'entity_id': 'climate.test2'
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


    @unittest.mock.patch('homeassistant.util.dt.utcnow')
    def test_doesnt_record_missing_sensor_reading(self, mock):
        '''Test a completed temperature shift gets recorded to the store'''
        initial_data = self.simple_init_data()
        config = {
            'smartclimate': {
                'test': {
                    'entity_id': ENTITY_ID,
                    'sensors': [
                        {
                            'entity_id': 'sensor.sensor1'
                        }
                    ]
                }
            }
        }
        self.init(config)

        #self.hass.states.set('sensor.sensor1', '8.0')
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
            self.assertEqual(data, initial_data)
