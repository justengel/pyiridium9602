"""
    test.simple_example
    SeaLandAire Technologies
    @author: jengel

Very simple test for pyiridium. Run this while running the pyiridium_server
"""
import pyiridium9602
import time

# Create your own serial port object and give it as the first argument or just give it the port name.
iridium_port = pyiridium9602.IridiumCommunicator("COM2")


def message_failed(msg_len, content, checksum, calc_check):
    """Signal that the message has failed."""
    print("Message Failed!")
    print("Message Length:", msg_len, "Received Length: ", len(content))
    print("Message Data:", content)
    print("Message Checksum:", checksum, "Calculated Checksum:", calc_check)

iridium_port.signal.message_received = lambda data: print("Message Received:", data)
iridium_port.signal.message_receive_failed = message_failed

# NOTE: There is no thread, so connect creates a thread to Complete the connection process
iridium_port.connect()  # Raises IridiumError if the port cannot be opened or if the ping did not find a response.

# Non blocking command requests
print("Signal Quality (0 - 5):", iridium_port.acquire_signal_quality())
print("System Time:", iridium_port.acquire_system_time())
print("Serial Number:", iridium_port.acquire_serial_number())

with iridium_port.wait_for_command():
    iridium_port.check_message()

time.sleep(60)

# Stop the `iridium_port.listen_thread` and close the port
iridium_port.close()
