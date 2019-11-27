import appdaemon.plugins.hass.hassapi as hass
from datastore import DataStore # pylint: disable=unused-import
from zoneimpl import ZoneImpl

class Zone(hass.Hass):
    def initialize(self):
        # pylint: disable=attribute-defined-outside-init
        self.zone = ZoneImpl(self)
