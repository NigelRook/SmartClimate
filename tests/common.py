from uuid import uuid4 as uuid
from datetime import datetime, timezone, timedelta, date, time
from threading import Lock

def relative_time(seconds):
    '''Return a time relative to other usages of relative_time'''
    return datetime(2019, 1, 1, 0, 0, 0) + timedelta(seconds=seconds)

def time_of_day(hour=0, minute=0, second=0, extradays=0):
    '''return a time of day'''
    return datetime.combine(date(2019, 1, 1)+timedelta(days=extradays), time(hour, minute, second))

class FakeStore:
    def __init__(self):
        self.data = {'_version': 1}
        self.lock = Lock()
        self.saved = False

    def save(self):
        '''save'''
        self.saved = True

class FakeHass:
    def __init__(self):
        self.name = "test"
        self.args = {}
        self.apps = {}
        self.states = {}
        self.time = relative_time(0)
        self._state_listeners = {}
        self._event_listeners = {}
        self._time_triggers = {}
        self.set_states = {}
        self.fired_events = []

    def get_app(self, name):
        return self.apps[name]

    def get_state(self, entity_id, attribute=None):
        state = self.states.get(entity_id, {})
        if attribute is not None:
            return state.get('attributes', {}).get(attribute, None)
        return state.get('state', None)

    def set_state(self, entity_id, state, attributes=None):
        self.set_states[entity_id] = {'state': state}
        if attributes is not None:
            self.set_states[entity_id]['attributes'] = attributes

    def listen_state(self, callback, entity_id, attribute=None):
        self._state_listeners[entity_id] = callback

    def trigger_state_callback(self, entity_id, attribute, old, new):
        self._state_listeners[entity_id](entity_id, attribute, old, new, {})

    def listen_event(self, callback, event, **kwargs):
        self._event_listeners[event] = (callback, kwargs)

    def trigger_event_callback(self, event, data):
        callback, kwargs = self._event_listeners[event]
        for key, value in kwargs.items():
            if key in data and data[key] != value:
                return
        callback(event, data, kwargs)

    def fire_event(self, event, **kwargs):
        self.fired_events.append({'event': event, 'data':kwargs})

    def datetime(self):
        return self.time

    def run_at(self, callback, when):
        handle = uuid()
        self._time_triggers[handle] = (when, callback)
        return handle

    def cancel_timer(self, handle):
        del self._time_triggers[handle]

    def advance_time(self, when):
        callbacks = [callback
                     for (time, callback) in self._time_triggers.values()
                     if time <= when.astimezone(timezone.utc)]
        for callback in callbacks:
            callback()
        self._time_triggers = {handle: (time, callback)
                               for handle, (time, callback) in self._time_triggers.items()
                               if time > when.astimezone(timezone.utc)}
        self.time = when
