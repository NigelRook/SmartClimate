import logging

_LOGGER = logging.getLogger(__name__)

class LinearPredictor:
    '''Linear regression model for predicting heating time'''
    def __init__(self, name):
        from sklearn import linear_model
        self._name = name
        self._predictor = linear_model.LinearRegression()
        self._ready = False

    def predict(self, target_temp, current_temp, sensor_readings):
        '''Predict the time to reach target_temp'''
        if not self._ready:
            _LOGGER.debug("[%s] Insufficient data, not making prediction")
            return None

        prediction = (self._predictor.intercept_ +
                      target_temp * self._predictor.coef_[0] +
                      current_temp * self._predictor.coef_[1])
        for i, (_, value) in enumerate(sensor_readings):
            prediction += value * self._predictor.coef_[i+2]

        prediction = int(round(prediction))

        _LOGGER.debug("[%s] Prediction for %s %s %s: %s", self._name,
                      target_temp, current_temp, sensor_readings, prediction)
        return prediction

    def learn(self, datapoints):
        '''Intrepret measured data'''
        if not self.check_ready(datapoints):
            self._ready = False
            return

        x_values = [[datapoint['target_temp'], datapoint['start_temp']] +
                    [value for _, value in datapoint['sensor_readings']] for datapoint in datapoints]
        y_values = [datapoint['duration_s'] for datapoint in datapoints]
        self._predictor.fit(x_values, y_values)
        self._ready = True
        _LOGGER.debug("[%s] Intercept:%s Coefficients:%s", self._name,
                      self._predictor.intercept_, self._predictor.coef_)

    @staticmethod
    def check_ready(datapoints):
        '''Return whether there are anough datapoints to make sensible predictions'''
        if not datapoints:
            return False
        num_sensors = len(datapoints[0]['sensor_readings'])
        return len(datapoints) >= num_sensors + 3
