from datetime import datetime, time, timezone, timedelta

class SmartEvent:
    '''binary sensor which turns on when preheat should begin'''
    def __init__(self, name, target_temp, target_time, parent):
        self._name = name
        self._parent = parent
        self._target_temp = target_temp
        self._target_time = self._convert_time(target_time)
        self._timer = None
        self._triggered = False
        self.update()

    def _convert_time(self, timestr):
        parts = timestr.split(':')
        timeval = time(hour=int(parts[0]),
                       minute=int(parts[1] if len(parts) >= 2 else 0),
                       second=int(parts[2] if len(parts) >= 3 else 0))
        now = self._parent.hass.datetime()
        today = now.date()
        todaydt = datetime.combine(today, timeval)

        if todaydt < now:
            return datetime.combine(today + timedelta(days=1), timeval)

        return todaydt

    def update(self):
        '''update sensor state'''
        if self._triggered:
            return

        if self._timer is not None:
            self._parent.hass.cancel_timer(self._timer)

        prediction = self._parent.predict(self._target_temp)
        if prediction is None:
            prediction = self._parent.default_preheat

        trigger_time = self._target_time.astimezone(timezone.utc) - timedelta(seconds=prediction)
        if trigger_time <= self._parent.hass.datetime().astimezone(timezone.utc):
            self._fire_event()
        else:
            # ugh, appdaemon uses timezone-naive local time...
            ad_trigger_time = trigger_time.astimezone().replace(tzinfo=None)
            self._parent.info("Setting event {} timer for {}", self._name, ad_trigger_time)
            self._timer = self._parent.hass.run_at(self._handle_timer, ad_trigger_time)

    def _fire_event(self):
        self._triggered = True
        self._parent.hass.fire_event('smartclimate.start_preheat', name=self._name, target_temp=self._target_temp)

    def cancel(self):
        '''cancel timer'''
        if self._timer is not None:
            self._parent.hass.cancel_timer(self._timer)

    def _handle_timer(self, **kwargs):
        self._timer = None
        self._fire_event()
