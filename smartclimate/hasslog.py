import logging

class HassLog:
    def __init__(self, app):
        self._app = app

    def debug(self, message, *args, **kwargs):
        if self._app.get_main_log().isEnabledFor(logging.DEBUG):
            self._app.log(message.format(*args, **kwargs), level="DEBUG")

    def info(self, message, *args, **kwargs):
        if self._app.get_main_log().isEnabledFor(logging.INFO):
            self._app.log(message.format(*args, **kwargs), level="INFO")

    def warning(self, message, *args, **kwargs):
        if self._app.get_main_log().isEnabledFor(logging.WARNING):
            self._app.log(message.format(*args, **kwargs), level="WARNING")

    def error(self, message, *args, **kwargs):
        if self._app.get_main_log().isEnabledFor(logging.ERROR):
            self._app.log(message.format(*args, **kwargs), level="ERROR")
