''' Tests for the smartclimate component '''
# pylint: disable=locally-disabled, line-too-long, invalid-name
import os
import pickle
import datetime
import unittest

from ha_test_common import (
    get_test_config_dir, get_test_home_assistant, mock_state_change_event)

from homeassistant.core import State

import smartclimate

ENTITY_ID = 'climate.test'

SIMPLE_CONFIG = {
    'smartclimate': {
        'entity_id': ENTITY_ID
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
    '''

    def cleanup(self):
        '''Cleanup any data created from the tests.'''
        if os.path.isfile(self.store):
            os.remove(self.store)

    def setUp(self):
        '''Initialize values for this test case class.'''
        self.maxDiff = 2000
        if not os.path.isdir(get_test_config_dir()):
            os.mkdir(get_test_config_dir())
        self.hass = get_test_home_assistant()
        self.store = get_test_config_dir('smartclimate.pickle')

    def tearDown(self):
        '''Stop everything that was started.'''
        self.hass.stop()
        self.cleanup()

    def test_initial_setup(self):
        '''Test the setup.'''
        response = smartclimate.setup(self.hass, SIMPLE_CONFIG)
        self.assertTrue(response)

    def init(self, config):
        '''Init smartclimate component'''
        smartclimate.setup(self.hass, config)

    @staticmethod
    def relative_time(time_s):
        '''Provide relative timestamps in seconds'''
        return datetime.datetime.utcfromtimestamp(1512043200 + time_s)

    def simple_init_data(self):
        '''Init data non-empty store for simple config'''
        data = {
            '_version': 1,
            ENTITY_ID: {
                'datapoints': [{
                    'start_temp': 18.,
                    'target_temp': 20.,
                    'sensor_readings': {},
                    'duration_s': 5100.0
                }]
            }
        }
        with open(self.store, 'wb') as file:
            pickle.dump(data, file)
        return data

    @unittest.mock.patch('homeassistant.util.dt.utcnow')
    def test_records_temperature_change(self, mock):
        '''Test a completed temperature shift gets recorded to the store'''
        self.init(SIMPLE_CONFIG)

        old_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 18., 'current_temperature' : 18.})
        new_state = State(ENTITY_ID, 'Manual', {'temperature': 20., 'current_temperature' : 18.})
        mock.return_value = self.relative_time(0)
        mock_state_change_event(self.hass, new_state, old_state)
        self.hass.block_till_done()

        old_state = new_state
        new_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 20., 'current_temperature' : 20.})
        mock.return_value = self.relative_time(5100)
        mock_state_change_event(self.hass, new_state, old_state)
        self.hass.block_till_done()

        self.assertTrue(os.path.isfile(self.store))
        with open(self.store, 'rb') as file:
            data = pickle.load(file)
            self.assertEqual(data, {
                '_version': 1,
                ENTITY_ID: {
                    'datapoints': [{
                        'start_temp': 18.,
                        'target_temp': 20.,
                        'sensor_readings': {},
                        'duration_s': 5100.0
                    }]
                }
            })

    @unittest.mock.patch('homeassistant.util.dt.utcnow')
    def test_aborts_test_if_target_temp_reset(self, mock):
        '''Test a completed temperature shift gets recorded to the store'''
        initial_data = self.simple_init_data()
        self.init(SIMPLE_CONFIG)

        old_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 18., 'current_temperature' : 18.})
        new_state = State(ENTITY_ID, 'Manual', {'temperature': 19., 'current_temperature' : 18.})
        mock.return_value = self.relative_time(0)
        mock_state_change_event(self.hass, new_state, old_state)
        self.hass.block_till_done()

        old_state = new_state
        new_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 18., 'current_temperature' : 18.5})
        mock.return_value = self.relative_time(2400)
        mock_state_change_event(self.hass, new_state, old_state)
        self.hass.block_till_done()

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
        self.hass.block_till_done()

        old_state = new_state
        new_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 20., 'current_temperature' : 19.})
        mock.return_value = self.relative_time(5100)
        mock_state_change_event(self.hass, new_state, old_state)
        self.hass.block_till_done()

        old_state = new_state
        new_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 20., 'current_temperature' : 20.})
        mock.return_value = self.relative_time(5100)
        mock_state_change_event(self.hass, new_state, old_state)
        self.hass.block_till_done()

        self.assertTrue(os.path.isfile(self.store))
        with open(self.store, 'rb') as file:
            data = pickle.load(file)
            self.assertEqual(data, {
                '_version': 1,
                ENTITY_ID: {
                    'datapoints': [{
                        'start_temp': 18.,
                        'target_temp': 20.,
                        'sensor_readings': {},
                        'duration_s': 5100.0
                    }]
                }
            })

    @unittest.mock.patch('homeassistant.util.dt.utcnow')
    def test_records_additional_sensors(self, mock):
        '''Test a completed temperature shift gets recorded to the store'''
        config = {
            'smartclimate': {
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
        self.init(config)

        self.hass.states.set('sensor.sensor1', '8.0')
        self.hass.states.set('sensor.sensor2', 'on', {'attr': '16.0'})
        old_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 18., 'current_temperature' : 18.})
        new_state = State(ENTITY_ID, 'Manual', {'temperature': 20., 'current_temperature' : 18.})
        mock.return_value = self.relative_time(0)
        mock_state_change_event(self.hass, new_state, old_state)
        self.hass.block_till_done()

        self.hass.states.set('sensor.sensor1', '9.0')
        self.hass.states.set('sensor.sensor2', 'on', {'attr': '17.0'})
        old_state = new_state
        new_state = State(ENTITY_ID, 'Smart Schedule', {'temperature': 20., 'current_temperature' : 20.})
        mock.return_value = self.relative_time(5100)
        mock_state_change_event(self.hass, new_state, old_state)
        self.hass.block_till_done()

        self.assertTrue(os.path.isfile(self.store))
        with open(self.store, 'rb') as file:
            data = pickle.load(file)
            self.assertEqual(data, {
                '_version': 1,
                ENTITY_ID: {
                    'datapoints': [{
                        'start_temp': 18.,
                        'target_temp': 20.,
                        'sensor_readings': {
                            'sensor.sensor1': 8.,
                            'sensor.sensor2.attr': 16.
                        },
                        'duration_s': 5100.0
                    }]
                }
            })

