class Progress:
    def __init__(self):
        self.value = 0
        self.of = 0
        self.finished = 0

    def set_of(self, of):
        self.of = of
        if self.of > 0:
            self.value = self.finished / self.of

    def set_finished(self, finished):
        self.finished = finished
        if self.of > 0:
            self.value = self.finished / self.of

    def set_of_finished(self, of, finished):
        self.of = of
        self.finished = finished
        if self.of > 0:
            self.value = self.finished / self.of

    def set_value(self, value):
        self.value = value
        self.finished = int(value * self.of)

    def to_dict(self):
        d = {
            "value": self.value
        }
        if self.of > 0:
            d['finished'] = self.finished
            d['of'] = self.of
