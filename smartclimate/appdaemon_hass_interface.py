class AppDaemonHassInterface:
    def __init__(self, app):
        self._app = app

    @property
    def name(self):
        return self._app.name

    @property
    def config(self):
        return self._app.args

    def listen_state(self, callback, entity_id, all_attributes=False, attribute=None):
        if all_attributes:
            self._app.listen_state(self._listen_state_handler(callback), entity_id, attribute="all")
        elif attribute is not None:
            self._app.listen_state(self._listen_state_handler(callback), entity_id, attribute=attribute)
        else:
            self._app.listen_state(self._listen_state_handler(callback), entity_id)

    @staticmethod
    def _listen_state_handler(callback):
        def handler(entity, attribute, old, new, kwargs):
            callback(entity, new, old)
        return handler

    def listen_event(self, callback, event, **kwargs):
        self._app.listen_event(self._listen_event_handler(callback), event, **kwargs)

    @staticmethod
    def _listen_event_handler(callback):
        def handler(event, data, kwargs):
            callback(event, data)
        return handler

    def fire_event(self, event, **kwargs):
        self._app.fire_event(event, **kwargs)

    def run_at(self, callback, when):
        if when.tzinfo is not None:
            # AD requires timezone naive local time
            when = when.astimezone().replace(tzinfo=None)
        return self._app.run_at(callback, when)

    def cancel_timer(self, timer):
        self._app.cancel_timer(timer)

    def get_state(self, entity_id, attribute=None):
        if attribute is not None:
            return self._app.get_state(entity_id, attribute=attribute)
        else:
            return self._app.get_state(entity_id)

    def set_state(self, entity_id, state=None, attributes=None):
        self._app.set_state(entity_id, state, attributes)

    def datetime(self):
        return self._app.datetime()
