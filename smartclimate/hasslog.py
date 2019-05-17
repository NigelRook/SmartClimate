import logging

class HassLog:
    def __init__(self, hass):
        self.hass = hass

    def debug(self, message, *args, **kwargs):
        if self.hass.get_main_log().isEnabledFor(logging.DEBUG):
            self.hass.log(message.format(*args, **kwargs), level="DEBUG")

    def info(self, message, *args, **kwargs):
        if self.hass.get_main_log().isEnabledFor(logging.INFO):
            self.hass.log(message.format(*args, **kwargs), level="INFO")

    def warning(self, message, *args, **kwargs):
        if self.hass.get_main_log().isEnabledFor(logging.WARNING):
            self.hass.log(message.format(*args, **kwargs), level="WARNING")

    def error(self, message, *args, **kwargs):
        if self.hass.get_main_log().isEnabledFor(logging.ERROR):
            self.hass.log(message.format(*args, **kwargs), level="ERROR")
