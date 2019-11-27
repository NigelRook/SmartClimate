from zoneimpl import ZoneImpl
from .common import FakeStore, FakeHass

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

def test_up_event():
    '''Test up event is fired'''
    ZoneImpl(hass)

    assert hass.fired_events == [{'event': 'smartclimate.up', 'data':{'zone': 'test'}}]
