class Progress:
    def __init__(self):
        self.value = 0

        self.done = 0
        self.total = 0

    def set_done(self, done):
        self.done = done
        if self.total > 0:
            self.value = self.done / self.total

    def increase_done(self, by):
        self.done += by
        if self.total > 0:
            self.value = self.done / self.total

    def decrease_done(self, by):
        self.done -= by
        if self.total > 0:
            self.value = self.done / self.total

    def set_total(self, total):
        self.total = total
        if self.total > 0:
            self.value = self.done / self.total

    def set_done_total(self, done, total):
        self.done = done
        self.total = total
        if self.total > 0:
            self.value = self.done / self.total

    def set_value(self, value):
        self.value = value
        self.done = int(value * self.total)

    def to_dict(self):
        d = {
            "value": self.value
        }
        if self.total > 0:
            d['done'] = self.done
            d['total'] = self.total
        return d
