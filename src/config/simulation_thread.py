import threading


class SimulationThread:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None

    def isAlive(self):
        if self.thread is not None:
            return self.thread.is_alive()
        else:
            return False

    def clear(self):
        self.stop_event.clear()
        self.thread = None

    def setThread(self, thread):
        self.thread = thread

    def start(self):
        self.thread.start()

    def stop(self):
        if self.thread is not None and self.thread.is_alive():
            self.stop_event.set()
            self.thread.join()
