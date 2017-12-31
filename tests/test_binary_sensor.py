''' Tests for the smartclimate component '''
# pylint: disable=locally-disabled, line-too-long, invalid-name, R0201, R0904
import os
import pickle
import datetime
import unittest
from copy import deepcopy

from homeassistant.core import State
from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.setup import async_setup_component
from homeassistant.util.async import run_coroutine_threadsafe, run_callback_threadsafe
from homeassistant.util.dt import DEFAULT_TIME_ZONE

from . import setup_custom_components, cleanup_custom_components
from .common import (
    get_test_config_dir, get_test_home_assistant, mock_state_change_event, fire_time_changed)

ENTITY_ID = 'climate.test'

SIMPLE_CONFIG = {
    'binary_sensor': [
        {
            'platform': 'smartclimate',
            'name': 'test_name',
            'friendly_name': 'test_friendly_name',
            'model': 'test',
            'temperature': '21',
            'start': '7:00',
            'end': '8:00'
        }
    ],
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
        return \
            run_coroutine_threadsafe(
                async_setup_component(self.hass, 'smartclimate', config), self.hass.loop).result() and \
            run_coroutine_threadsafe(
                async_setup_component(self.hass, 'binary_sensor', config), self.hass.loop).result()

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
    def local_datetime(time_str):
        '''Return a local datetime at time_str'''
        parts = time_str.split(':')
        return datetime.datetime.now().replace(hour=int(parts[0]), minute=int(parts[1]),
                                               second=0, microsecond=0, tzinfo=DEFAULT_TIME_ZONE)

    def set_data(self, datapoints):
        '''set saved data'''
        data = {
            '_version': 1,
            'test': {'datapoints': datapoints}
        }
        with open(self.store, 'wb') as file:
            pickle.dump(data, file)
        return data

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_initial_schedule_before_on(self, mock):
        '''Ensure initial state is sensible'''
        mock.return_value = self.local_datetime('04:00')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':20.0, 'current_temperature':19.0})
        response = self.init(SIMPLE_CONFIG)
        self.assertTrue(response)
        self.block_till_done()
        self.assertState('binary_sensor.test_name', 'off', {
            'friendly_name': 'test_friendly_name',
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
        self.assertState('binary_sensor.test_name', 'off', {
            'friendly_name': 'test_friendly_name',
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
        self.assertState('binary_sensor.test_name', 'on', {
            'friendly_name': 'test_friendly_name',
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
        self.assertState('binary_sensor.test_name', 'on', {
            'friendly_name': 'test_friendly_name',
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
        self.assertHeatingTime('binary_sensor.test_name', 1800)
        self.assertOnTime('binary_sensor.test_name', '06:30')

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
        self.assertHeatingTime('binary_sensor.test_name', 1620)
        self.assertOnTime('binary_sensor.test_name', '06:33')

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_on_time_from_learned_data_with_sensor(self, mock):
        '''prediction test using sensor'''
        config = deepcopy(SIMPLE_CONFIG)
        config['smartclimate']['test']['sensors'] = [{'entity_id':'sensors.test'}]
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
        self.assertHeatingTime('binary_sensor.test_name', 2400)
        self.assertOnTime('binary_sensor.test_name', '06:20')

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_on_time_from_learned_data_with_sensor_attribute(self, mock):
        '''prediction test using sensor with value in attribute'''
        config = deepcopy(SIMPLE_CONFIG)
        config['smartclimate']['test']['sensors'] = [{'entity_id':'sensors.test', 'attribute':'temp'}]
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
        self.assertHeatingTime('binary_sensor.test_name', 2400)
        self.assertOnTime('binary_sensor.test_name', '06:20')

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_on_time_changes_if_sensor_reading_changes(self, mock):
        '''prediction updates after sensor reading changes'''
        config = deepcopy(SIMPLE_CONFIG)
        config['smartclimate']['test']['sensors'] = [{'entity_id':'sensors.test'}]
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
        self.assertHeatingTime('binary_sensor.test_name', 2340)
        self.assertOnTime('binary_sensor.test_name', '06:21')

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_on_time_changes_if_sensor_attribute_reading_changes(self, mock):
        '''prediction updates after sensor attribute reading changes'''
        config = deepcopy(SIMPLE_CONFIG)
        config['smartclimate']['test']['sensors'] = [{'entity_id':'sensors.test', 'attribute':'temp'}]
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
        self.assertHeatingTime('binary_sensor.test_name', 2340)
        self.assertOnTime('binary_sensor.test_name', '06:21')

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
        self.assertOnTime('binary_sensor.test_name', '06:30')
        mock.return_value = self.local_datetime('06:30')
        fire_time_changed(self.hass, self.local_datetime('06:30'))
        self.block_till_done()
        self.assertState('binary_sensor.test_name', 'on')

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
        self.assertState('binary_sensor.test_name', 'on')
        mock.return_value = self.local_datetime('08:00')
        fire_time_changed(self.hass, self.local_datetime('08:00'))
        self.block_till_done()
        self.assertState('binary_sensor.test_name', 'off')

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_heating_schedule_starting_next_day(self, mock):
        '''correctly disables if the heating schedule is for the next day'''
        mock.return_value = self.local_datetime('23:30')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':20.0, 'current_temperature':19.0})
        config = deepcopy(SIMPLE_CONFIG)
        config['binary_sensor'][0]['start'] = '02:00'
        response = self.init(config)
        self.assertTrue(response)
        self.block_till_done()
        self.assertState('binary_sensor.test_name', 'off', {
            'friendly_name': 'test_friendly_name',
            'model': 'test',
            'temperature': str(21.0),
            'start': '02:00',
            'end': '08:00',
            'heating_time': 3600,
            'next_on': '01:00'
        })

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_heating_schedule_starting_next_day_but_preheating_today(self, mock):
        '''correctly enables if the heating schedule is for the next day'''
        mock.return_value = self.local_datetime('23:30')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':20.0, 'current_temperature':19.0})
        config = deepcopy(SIMPLE_CONFIG)
        config['binary_sensor'][0]['start'] = '00:00'
        response = self.init(config)
        self.assertTrue(response)
        self.block_till_done()
        self.assertState('binary_sensor.test_name', 'on', {
            'friendly_name': 'test_friendly_name',
            'model': 'test',
            'temperature': str(21.0),
            'start': '00:00',
            'end': '08:00',
            'heating_time': 3600,
        })

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_heating_schedule_on_straddling_midnight(self, mock):
        '''correctly schedules heating straddling midnight'''
        mock.return_value = self.local_datetime('23:30')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':20.0, 'current_temperature':19.0})
        config = deepcopy(SIMPLE_CONFIG)
        config['binary_sensor'][0]['start'] = '23:00'
        response = self.init(config)
        self.assertTrue(response)
        self.block_till_done()
        self.assertState('binary_sensor.test_name', 'on', {
            'friendly_name': 'test_friendly_name',
            'model': 'test',
            'temperature': str(21.0),
            'start': '23:00',
            'end': '08:00',
            'heating_time': 3600,
        })

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_heating_schedule_off_straddling_midnight(self, mock):
        '''correctly schedules heating straddling midnight'''
        mock.return_value = self.local_datetime('21:30')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':20.0, 'current_temperature':19.0})
        config = deepcopy(SIMPLE_CONFIG)
        config['binary_sensor'][0]['start'] = '23:00'
        response = self.init(config)
        self.assertTrue(response)
        self.block_till_done()
        self.assertState('binary_sensor.test_name', 'off', {
            'friendly_name': 'test_friendly_name',
            'model': 'test',
            'temperature': str(21.0),
            'start': '23:00',
            'end': '08:00',
            'heating_time': 3600,
            'next_on': '22:00'
        })

    @unittest.mock.patch('homeassistant.util.dt.now')
    def test_update_config(self, mock):
        '''Ensure initial state is sensible'''
        mock.return_value = self.local_datetime('06:30')
        self.hass.states.set(ENTITY_ID, 'on', attributes={'temperature':19.0, 'current_temperature':18.0})
        response = self.init(SIMPLE_CONFIG)
        self.assertTrue(response)
        self.block_till_done()
        run_callback_threadsafe(self.hass.loop,
                                self.hass.bus.async_fire, EVENT_CALL_SERVICE, {
                                    'domain': 'smartclimate',
                                    'service': 'configure',
                                    'service_data': {
                                        'entity_id': 'binary_sensor.test_name',
                                        'temperature': str(20.0),
                                        'start': '09:00',
                                        'end': '10:00',
                                    }
                                }).result()
        self.block_till_done()
        self.assertState('binary_sensor.test_name', 'off', {
            'friendly_name': 'test_friendly_name',
            'model': 'test',
            'temperature': str(20.0),
            'start': '09:00',
            'end': '10:00',
            'heating_time': 3600,
            'next_on': '08:00'
        })
