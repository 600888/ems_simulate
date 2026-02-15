
from blinker import Signal

class BasePoint:
    def __init__(self, code):
        self.code = code
        self.value_changed = Signal()
        self.is_send_signal = True
        self._value = 0

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._value = new_value
        if self.is_send_signal:
            print(f"Sending signal from {self.code}")
            # Simulate the exact call in BasePoint.py
            self.value_changed.send(self, old_point=self)

class Calculator:
    def on_source_changed(self, sender, **kwargs):
        print(f"Received signal. Sender: {sender}, Type: {type(sender)}")
        if hasattr(sender, 'code'):
            print(f"Sender code: {sender.code}")
        else:
            print("Sender has no code attribute")

def test_signal():
    p = BasePoint("TEST_POINT")
    c = Calculator()
    
    # Connect
    p.value_changed.connect(c.on_source_changed)
    
    # Trigger
    p.value = 10

if __name__ == "__main__":
    test_signal()
