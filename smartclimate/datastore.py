import os
import pickle
import logging
from threading import Lock
import appdaemon.plugins.hass.hassapi as hass

_LOGGER = logging.getLogger(__name__)

class DataStore(hass.Hass):
    '''Data store for SmartClimate'''

    def initialize(self):
        '''appdaemon init callback'''
        # pylint: disable=attribute-defined-outside-init
        self.lock = Lock()
        self._data_file = self.args["data_file"]
        self._load()

    def _load(self):
        # pylint: disable=attribute-defined-outside-init
        if os.path.exists(self._data_file):
            try:
                _LOGGER.info('Loading data from %s', self._data_file)
                with open(self._data_file, 'rb') as file:
                    self.data = pickle.load(file) or self._default_data()
            except:
                _LOGGER.error('Error loading data %s', self._data_file, exc_info=True)
                raise
        else:
            _LOGGER.info('No data file found, using blank')
            self.data = self._default_data()

    @staticmethod
    def _default_data():
        return {'_version': 1}

    def save(self):
        '''Commit current data to disk'''
        try:
            _LOGGER.debug('saving data to %s', self._data_file)
            temp_file = self._data_file+'.tmp'
            with open(temp_file, 'wb') as file:
                pickle.dump(self.data, file)
            if os.path.isfile(self._data_file):
                os.remove(self._data_file)
            os.rename(temp_file, self._data_file)
        except:
            _LOGGER.error('Error saving data %s', self._data_file, exc_info=True)
            raise
