import appdaemon.plugins.hass.hassapi as hass
from .datastore import DataStore
from .roomimpl import RoomImpl

class Room(hass.Hass):
    def initialize(self):
        # pylint: disable=attribute-defined-outside-init
        self.room = RoomImpl(self)
