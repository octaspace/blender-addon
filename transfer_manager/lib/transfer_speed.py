import time


class TransferSpeed:
    def __init__(self, keep_num_entries=20):
        self.keep_num_entries = keep_num_entries
        self.entries = []

        self.value = 0

    def update(self, transfered_since_last_update):
        now = time.time()
        entry = (now, transfered_since_last_update)
        self.entries.append(entry)
        if len(self.entries) > self.keep_num_entries:  # truncate list
            self.entries = self.entries[-self.keep_num_entries:]

        if len(self.entries) > 1:
            start = self.entries[0][0]
            end = self.entries[-1][0]
            diff = end - start

            bytes_transfered = 0
            for e in self.entries:
                bytes_transfered += e[1]

            self.value = bytes_transfered / diff
        else:
            self.value = 0
