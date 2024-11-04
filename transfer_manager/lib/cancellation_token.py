class CancellationToken:
    def __init__(self):
        self._is_canceled = False

    def is_canceled(self):
        return self._is_canceled

    def cancel(self):
        self._is_canceled = True
