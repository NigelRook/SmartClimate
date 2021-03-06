class LinearPredictor:
    '''Linear regression model for predicting heating time'''
    def __init__(self, name, hasslog):
        from sklearn import linear_model
        self._name = name
        self.log = hasslog
        self._predictor = linear_model.LinearRegression()
        self._ready = False

    def predict(self, target_temp, current_temp, sensor_readings):
        '''Predict the time to reach target_temp'''
        if not self._ready:
            self.log.debug("[{}] Insufficient data, not making prediction", self._name)
            return None

        prediction = (self._predictor.intercept_ +
                      target_temp * self._predictor.coef_[0] +
                      current_temp * self._predictor.coef_[1])
        for i, (_, value) in enumerate(sensor_readings):
            prediction += value * self._predictor.coef_[i+2]

        prediction = int(round(prediction))

        self.log.debug("[{}] Prediction for {} {} {}: {}", self._name,
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
        self.log.debug("[{}] Intercept:{} Coefficients:{}", self._name,
                       self._predictor.intercept_, self._predictor.coef_)

    @staticmethod
    def check_ready(datapoints):
        '''Return whether there are anough datapoints to make sensible predictions'''
        if not datapoints:
            return False
        num_sensors = len(datapoints[0]['sensor_readings'])
        return len(datapoints) >= num_sensors + 3
