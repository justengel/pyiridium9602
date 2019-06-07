"""
    test.test_custom_signal
    SeaLandAire Technologies
    @author: jengel
"""
from __future__ import print_function

import pyiridium9602
import threading
import time

# Create your own serial port object and give it as the first argument or just give it the port name.
iridium_port = pyiridium9602.IridiumCommunicator("COM2")


class CustomSignal(object):
    """Create a custom Signal callback manager.
    
    Note:
        If other Signal methods do not exist they will be created as empty methods. If the notification method
        does not exist it will use the print function. You may want to use the notification method for logging special 
        events.

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
th.daemon = True
th.start()

# NOTE: There is no thread, so connect creates a thread to Complete the connection process
iridium_port.connect()  # Raises IridiumError if the port cannot be opened or if the ping did not find a response.

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
