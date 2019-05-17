import os
import pickle
from threading import Lock
import appdaemon.plugins.hass.hassapi as hass
from hasslog import HassLog

class DataStore(hass.Hass):
    '''Data store for SmartClimate'''

    def initialize(self):
        '''appdaemon init callback'''
        # pylint: disable=attribute-defined-outside-init
        self.impl = DataStoreImpl(self)

    @property
    def data(self):
        '''Get data'''
        return self.impl.data

    def save(self):
        '''Commit current data to disk'''
        self.impl.save()

class DataStoreImpl(HassLog):
    def __init__(self, app):
        super().__init__(app)
        self.lock = Lock()
        self._data_file = app.args["data_file"]
        self._load()

    def _load(self):
        # pylint: disable=attribute-defined-outside-init
        if os.path.exists(self._data_file):
            try:
                self.info('Loading data from {}', self._data_file)
                with open(self._data_file, 'rb') as file:
                    self.data = pickle.load(file) or self._default_data()
            except:
                self.error('Error loading data {}', self._data_file, exc_info=True)
                raise
        else:
            self.info('No data file found, using blank')
            self.data = self._default_data()

    @staticmethod
    def _default_data():
        return {'_version': 1}

    def save(self):
        '''Commit current data to disk'''
        try:
            self.debug('saving data to {}', self._data_file)
            temp_file = self._data_file+'.tmp'
            with open(temp_file, 'wb') as file:
                pickle.dump(self.data, file)
            if os.path.isfile(self._data_file):
                os.remove(self._data_file)
            os.rename(temp_file, self._data_file)
        except:
            self.error('Error saving data {}', self._data_file, exc_info=True)
            raise
