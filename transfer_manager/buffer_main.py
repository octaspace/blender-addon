import subprocess
import sys
import os
import tempfile
import logging
import threading
from logging.handlers import RotatingFileHandler


class Program:
    def __init__(self):
        self.log_file_path = os.path.join(tempfile.gettempdir(), "tm.log")
        self.logger = self.setup_logging()

    def setup_logging(self):
        log_handler = RotatingFileHandler(self.log_file_path, maxBytes=5 * 1024 * 1024, backupCount=5)
        log_formatter = logging.Formatter('%(asctime)s [%(levelname)s]:%(message)s')
        log_handler.setFormatter(log_formatter)

        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        logger.addHandler(log_handler)

        return logger

    def main(self):
        self.logger.warning("Starting Transfer Manager")

        def log_stream(stream, level):
            for line in iter(stream.readline, ''):
                self.logger.log(level, line.strip())
            stream.close()

        startupinfo = None
        if os.name == 'nt':  # Windows
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        process = subprocess.Popen(
            [sys.executable, "-m", "transfer_manager.main"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.path.dirname(os.path.dirname(__file__)),
            startupinfo=startupinfo
        )

        stdout_thread = threading.Thread(target=log_stream, args=(process.stdout, logging.INFO))
        stderr_thread = threading.Thread(target=log_stream, args=(process.stderr, logging.ERROR))

        stdout_thread.start()
        stderr_thread.start()

        process.wait()

        stdout_thread.join()
        stderr_thread.join()

        self.logger.warning(f"Transfer Manager exited with code {process.returncode}")


if __name__ == '__main__':
    program = Program()
    program.main()
