# pyiridium9602 
Python 3 iridium satelite communication library for the iridium 9602 modem.

## Purpose
I wrote this library after trying to work with pyRockBlock foud at https://github.com/MakerSnake/pyRockBlock. The pyRockblock library 
was a great resource to start with, but I quickly found out it did not suit the needs for my application. I had too many problems 
with the serial port readline commands and long timeouts hanging my GUI application. I ended up digging through the documentation 
about the iridium 9602 modem at http://www.nalresearch.com/Info/AT%20Commands%20for%20Models%209602.pdf and wrote this library. 
This library is strictly a callback based library, although blocking methods are provided as well.

See the modules under the tests folder for examples of how to use the library.

## Example
Try running `python -m pyiridium9602.pyiridium_server COM1` and `python -m pyiridium9602.pyiridium COM1` to see how the library works.

```
# ===== Command Line: pyiridium_server.py COM2 =====
Enter a message to send: Hello World!
Enter a message to send: Hi
Enter a message to send: 

# ===== Command Line: pyiridium.py COM2 =====
Warning No threads are listening for responses. A thread will be created 
Signal Quality (0 - 5): 5
System Time: 3521898596
Serial Number: 60134
Message acquired: b'Hello'
Message acquired: b'Hi'

# ===== pyiridium_server.py COM2 =====
Enter a message to send: exit

# ===== Command Line: pyiridium.py COM2 =====
Message acquired: b'exit'

# Both programs close
```

Use the Signal class (or create your own class) and use custom callback methods while the IridiumCommunicator class manages all of the communications.

```python
import pyiridium9602

# Create your own serial port object and give it as the first argument or just give it the port name.
iridium_port = pyiridium9602.IridiumCommunicator("COM2")

# Message parser
def parse_data(data):
    print("My data:", data)

def message_failed(msg_len, content, checksum, calc_check):
    print("Message Failed checksum or length!", msg_len, content, checksum, calc_check)

# Use the default signal class and override the Signal API methods or create your own object.
iridium_port.signal.connected = lambda: print("Connected!")
iridium_port.signal.disconnected = lambda: print("Disconnected!")
iridium_port.signal.serial_number_updated = lambda s: print("Serial Number:", s)
iridium_port.signal.system_time_updated = lambda s: print("System Time:", s)
iridium_port.signal.signal_quality_updated = lambda sig: print("Signal Quality (0-5):", sig)
iridium_port.signal.check_ring_updated = lambda tri, sri: print("Telephone Indicator:", tri, 
                                                                "\nSBD Indicator:", sri)
iridium_port.signal.message_received = parse_data
iridium_port.signal.message_receive_failed = message_failed
iridium_port.signal.notification = print

# NOTE: There is no thread in this example, so `connect()` creates a thread to Complete the connection process
iridium_port.connect() # Raises IridiumError if the port cannot be opened or if the ping did not find a response.

# Non blocking command requests
iridium_port.request_signal_quality()
iridium_port.queue_system_time()

# If you run a request immediately after a request then the response will error
# This is because the first command will have it's value returned while the new request is the expected command
#iridium_port.request_serial_number()

# Blocking command (wait for previous command and wait to complete)
with iridium_port.wait_for_command():
    iridium_port.request_signal_quality()

# Blocking command (wait for previous command and wait to complete)
with iridium_port.wait_for_command():
    iridium_port.check_ring()  # If an SBD ring is found automatically start the session to read the value.

# Blocking Command (Do not wait for previous `wait_for_previous=0`)
serial_number = iridium_port.acquire_response(pyiridium9602.Command.SERIAL_NUMBER, wait_for_previous=0)
print("Manual Serial Number:", serial_number)

# Pre-made Blocking Command
sig = iridium_port.acquire_signal_quality()
print("Manual Signal Quality (0 - 5):", sig)

# Stop the `iridium_port.listen_thread` and close the port
iridium_port.close()

```

## Threading
The IridiumCommunicator was created to work with threading that is why the Signal callback class exists.

To use threading follow the example below.

```python
import pyiridium9602
import threading
import time

# Create your own serial port object and give it as the first argument or just give it the port name.
iridium_port = pyiridium9602.IridiumCommunicator("COM2")

class CustomSignal(object):
    """Create a cusotm Signal callback manager.
    
    Note:
        If other Signal methods do not exist they will be created as empty methods. If the notification method
        does not exist it will use the print function. You may want to use the notification method for logging special events.

    See Also:
        pyiridium9602.Signal
    """

    def connected(self):
        """This method is called after the connection is verified."""
        print("Connected!")
    
    def disconnected(self):
        """This method is called after the connection is closed."""
        print("Disconnected!")

    def signal_quality_updated(self, signal):
        """This method is called after a new signal quality has been received."""
        print("Signal Quality (0-5):", signal)
        
    def check_ring_updated(self, tri, sri):
        """This method is called after a new check ring response has been received.
        
        Args:
            tri (int): Telephone ring indicator
            sri (int): SBD ring indicator
        """
        print("Check Ring Response", tri, sri)
    
    def message_received(self, data):
        """This method is called after a message has been received and has passed the checksum.
        
        Args:
            data (bytes): Message contents without the length or checksum bytes.
        """
        print("Message Received:", data)

    def message_receive_failed(self, msg_len, content, checksum, calc_check):
        """This method is called after a message has benn received and it failed the checksum or does not meet the 
        message length.

        Args:
            msg_len (int): Parsed length of the message (the first 2 byes).
            content (bytes): Content portion of the message without the first 2 bytes (message length) and the last 
                2 bytes (checksum).
            checksum (bytes): 2 checksum bytes that were included with the message.
            calc_check (bytes): 2 calculated checksum bytes from the content.
        """
        print("Message Failed checksum or length!", msg_len, content, checksum, calc_check)

# Set the signal callback manager
iridium_port.signal = CustomSignal()

# Manually creating the thread
th = threading.Thread(target=iridium_port.listen)
th.start()

# The IridiumCommunicator needs to know if a method is reading the serial port `IridiumCommunicator.listen()`
# If the thread isn't using `IridiumCommunicator.listen()` and tell the  that it is listening
#iridium_port.set_listening(True)

# Because the iridium_port knows it is listening it will not create it's own thread. 
iridium_port.connect() # Raises IridiumError if the port cannot be opened or if the ping did not find a response.

# Blocking methods example
sys_time = iridium_port.acquire_system_time()
print("System Time:", sys_time)

serial_number = iridium_port.acquire_serial_number()
print("Serial Number:", serial_number)

# Non blocking command requests.
# Note the previous command was blocking so we know it is finished
iridium_port.request_signal_quality()

# Wait for the response
time.sleep(2)

# Note `time.sleep(2)` is blocking so the previous command should be finished. We don't really know how long it takes
with iridium_port.wait_for_command(wait_for_previous=0):
    iridium_port.check_ring()

# Note the ring command finished, but the subsequent (if SBD Ring was more than 0) Session SBDIX probably did not.
time.sleep(2)

# Stop the `iridium_port.listen_thread` and close the port
iridium_port.close()
th.join()

```
