"""
    pyiridium_server
    SeaLandAire Technologies
    @author: jengel

Iridium satellite communications server emulator.

Note:
    Not everything in this server works correctly. The below code is a simple test emulator for what I have observed 
    and assume to be the way that the iridium 9602 modem works.
"""
import collections
import random
import time
import datetime

from pyiridium9602.pyiridium import Command, MO_STATUS, MT_STATUS, IridiumError, Signal, IridiumCommunicator


class IridiumServer(IridiumCommunicator):
    """Iridium Server emulator for testing."""

    DEFAULT_OPTIONS = {'echo': True,
                       'ring_alerts': True,
                       'auto_session': True,
                       'flow_control': False,
                       'telephone': False,
                       }

    def __init__(self, serialport=None, signal=None, options=None):
        super().__init__(None, signal, options)

        # Variables
        self._serial_number = str(random.randint(0, 65535))
        self._system_time = 0
        self._session_counter = 0
        self._signal_quality = 5
        self._read_history = collections.deque(maxlen=10)
        self._mo_status = 0
        self._mt_msn = 0

        if serialport is not None:
            self.serialport = serialport
    # end Constructor

    def connect(self, port_id=None, create_thread=True):
        """Connect to the iridium modem over the serial port and ensure that it is working.
        
        Args:
            port_id (str/serial.Serial): COM port string or serial object.
            create_thread (bool): If True create a thread if the communicator is not already listening

        Raises:
            IridiumError: If the port cannot be opened or if the ping did not find a response.
        """
        if port_id is not None:
            self.serialport = port_id

        # Connecting signal
        self.signal.connecting()

        # Force the serial port to be open
        try:
            if not self.serialport.isOpen():
                self.serialport.open()
        except Exception as err:
            raise IridiumError("Could not connect. The serial port would not open!") from err

        # Start a thread to listen for responses
        if create_thread and not self.is_listening():
            self.start_thread()

        # Connected signal
        self._connected = True
        self.signal.connected()
    # end connect

    def write_iridium(self, data):
        """Write to the iridium? This command is called after a complete Write Binary command has been received.
        
        Args:
            data (bytes): 2 bytes of message length, contents, 2 bytes of checksum
        """
        pass

    def write_serial(self, msg):
        if len(msg) > 270:
            raise IridiumError("Message length must be no more than 270 bytes.")

        if isinstance(msg, str):
            msg = msg.encode("utf-8")
        self._write_queue.append(msg)
        self._silent_write(b"SBDRING\n")
    # end write_serial
    
    send_message = write_serial
        
    def _silent_write(self, msg):
        """Directly write over the serial port without ringing."""
        try:
            self.serialport.write(msg)
        except:
            self.close()
    # end _silent_write
    
    def set_echo(self, value=True):
        """Send the echo command."""
        self.set_option('echo', value)
    # end set_echo
    
    def set_flow_control(self, value=True):
        """Send the flow control command."""
        self.set_option('flow_control', value)
    # end set_flow_control
    
    def set_ring_alerts(self, value=True):
        """Send the ring alerts command."""
        self.set_option('ring_alerts', value)
    # end set_ring_alerts

    def echo_command(self, cmd):
        """Check if echo is on and echo the command if it is.
        
        Note:
            This command clears the `_read_buf`! If you implement a receive command in check_incoming without an echo
            be sure to clear the `_read_buf`!

        Args:
            cmd (bytes): The given command to echo.
        """
        if self.is_echo():
            self._silent_write(cmd + b'\r\n')
    # end echo_command

    def check_io(self, message=b''):
        """Check for incoming and outgoing messages."""
        # Add the message to the existing buffer
        if message != b'':
            self._read_history.append(message)
        self._read_buf += message

        while b'\r' in self._read_buf:
            data, self._read_buf = self._read_buf.split(b'\r', 1)
            self.check_incoming(data + b'\r')
    # end check_io

    def check_incoming(self, cmd):
        """Run the thread trying to connect."""
        # Ping
        if cmd == Command.PING + b'\r':
            self.echo_command(cmd)
            self._silent_write(Command.OK + b'\r\n')

        # Echo
        elif cmd == Command.ECHO_ON + b'\r':
            self.set_echo(True)
            self.echo_command(cmd)
            self._silent_write(Command.OK + b'\r\n')
        elif cmd == Command.ECHO_OFF + b'\r':
            self.set_echo(False)
            self._silent_write(Command.OK + b'\r\n')

        # Flow Control
        elif cmd == Command.FLOW_CONTROL_ON + b'\r':
            self.set_flow_control(True)
            self.echo_command(cmd)
            self._silent_write(Command.OK + b'\r\n')
        elif cmd == Command.FLOW_CONTROL_OFF + b'\r':
            self.set_flow_control(False)
            self.echo_command(cmd)
            self._silent_write(Command.OK + b'\r\n')

        # Ring Alerts
        elif cmd == Command.RING_ALERTS_ON + b'\r':
            self.set_ring_alerts(True)
            self.echo_command(cmd)
            self._silent_write(Command.OK + b'\r\n')
        elif cmd == Command.RING_ALERTS_OFF + b'\r':
            self.set_ring_alerts(False)
            self.echo_command(cmd)
            self._silent_write(Command.OK + b'\r\n')

        # Repeat the last command
        elif cmd == Command.REPEAT_LAST_COMMAND + b'\r':
            self.echo_command(cmd)
            self._read_history.pop()  # Remove the b'A/' Repeat Last Command from history. Don't know.
            self._silent_write(self._read_history[-1] + b'\r\n\r\n')  # Skip repeat of the b'A/'
            self._silent_write(Command.OK + b'\r\n')

        # Return echo
        elif cmd == Command.RETURN_ECHO + b'\r':
            self.echo_command(cmd)
            value = int(self.is_echo())
            self._silent_write(str(value).encode("utf-8") + b'\r\n\r\n')
            self._silent_write(Command.OK + b'\r\n')

        # Return Identification
        elif cmd == Command.RETURN_IDENTIFICATION + b'\r':
            self.echo_command(cmd)
            self._silent_write(b'4' + b'\r\n\r\n')  # 4 for Iridium 9602 Family
            self._silent_write(Command.OK + b'\r\n')

        # System Time
        elif cmd == Command.SYSTEM_TIME + b'\r':
            self.echo_command(cmd)
            # Network Time - I have no idea if this is right. Maybe just have a counter of total seconds running?
            # Find the time now minus the epoch in hex
            t = ((datetime.datetime.utcnow() - self.IRIDIUM_EPOCH).total_seconds()) * 1000 / 90
            h = hex(int(t))[2:]
            self._silent_write(b"-MSSTM: " + h.encode("utf-8").zfill(8) + b'\r\n\r\n')
            self._silent_write(Command.OK + b'\r\n')

        # Signal Quality
        elif cmd == Command.SIGNAL_QUALITY + b'\r':
            self.echo_command(cmd)
            # Request signal strength
            msg = b''.join((b"+CSQ:",
                            str(self._signal_quality).encode("utf-8"),  # Signal threshold is 2, max is 5
                            b'\r\n\r\n',  # End the message
                            ))
            self._silent_write(msg)
            self._silent_write(Command.OK + b'\r\n')

        # Serial Number
        elif cmd == Command.SERIAL_NUMBER + b'\r':
            self.echo_command(cmd)
            # Serial Number/IMEI number
            self._silent_write(str(self._serial_number).encode('utf_8') + b'\r\n\r\n')
            self._silent_write(Command.OK + b'\r\n')

        # Clear MO Buffer
        elif cmd == Command.CLEAR_MO_BUFFER + b'\r':
            self.echo_command(cmd)
            # Respond with success
            self._silent_write(b'0' + b'\r\n\r\n')
            self._silent_write(Command.OK + b'\r\n')

        # Check Ring
        elif cmd == Command.CHECK_RING + b'\r':
            self.echo_command(cmd)
            # Check the ring message
            msg = b''.join((b"+CRIS: ",  # Ring response
                            b'0,',  # Telephone 0
                            str(len(self._write_queue)).encode("utf-8"),  # SBD ring indication status
                            b'\r\n\r\n'  # End the message
                            ))
            self._silent_write(msg)
            self._silent_write(Command.OK + b'\r\n')

        # Session
        elif cmd == Command.SESSION + b'\r':
            self.echo_command(cmd)
            # Session
            mt_status = int(len(self._write_queue) > 0)
            try:
                mt_len = len(self._write_queue[0])
                queue_len = len(self._write_queue)-1
            except IndexError:
                mt_len = 0
                queue_len = 0

            msg = b''.join((b'+SBDIX: ',
                            str(self._mo_status).encode("utf-8"), b',',  # MO Status
                            str(self._session_counter).encode("utf-8"), b',',
                            str(mt_status).encode("utf-8"), b',',
                            str(self._mt_msn).encode("utf-8"), b',',
                            str(mt_len).encode("utf-8"), b',',
                            str(queue_len).encode("utf-8"),
                            b'\r\n\r\n'
                            ))
            self._silent_write(msg)

            self._session_counter = (self._session_counter + 1) & 0xffff
            self._mt_msn = (self._mt_msn + 1) & 0xffff
            self._mo_status = 0

            self._silent_write(Command.OK + b'\r\n')

        # Read Binary
        elif cmd == Command.READ_BINARY + b'\r':
            # Read Binary Data
            if len(self._write_queue) > 0:
                msg = self._write_queue.popleft()
                msg_len = len(msg).to_bytes(2, 'big')
                checksum = int(sum(msg)).to_bytes(4, 'big')[2:]  # smallest 2 bytes of the sum
                self._silent_write(b''.join((b'AT+SBDRB\r', msg_len, msg, checksum, b'\r\n\r\n')))

            self._silent_write(Command.OK + b'\r\n')

        # Write Binary
        elif cmd.startswith(Command.WRITE_BINARY):
            # Read the length from write binary and return a READY for the device to send data
            data = cmd.replace(Command.WRITE_BINARY, b'').strip()
            self.echo_command(cmd)

            try:
                length = int(data.decode("utf-8"))  # length of the expected message

                # Read for the Binary data
                self._silent_write(Command.READY + b'\r\n')

                # Read the Contents of the Write Binary message
                # Note: this section cannot be in the main read loop because b'\r' can be in the contents of the message
                msg = self.read_serial()
                start = time.time()
                while len(msg) < length + 2:
                    # Prevent running forever
                    if time.time() - start < 60:
                        self._mo_status = 18
                        self._silent_write(Command.OK + b'\r\n')
                        raise IridiumError("Timeout on Write Binary")

                    msg += self.read_serial()
                    
                # Successful write binary command with the correct length
                contents = msg[:-2]
                checksum = msg[-2:]
                calc_check = int(sum(contents)).to_bytes(4, 'big')[2:]  # smallest 2 bytes of the sum
                if checksum == calc_check:
                    # This is were a read Iridium modem would send the message
                    self.write_iridium(b''.join((str(length).encode("utf-8"), contents, checksum)))

                    self._mo_status = 1  # Success
                    self._silent_write(b'\r\n')
                    self._silent_write(b'0' + b'\r\n')  # Success

                else:
                    self._mo_status = 18  # Connect lost (RF drop). I don't think there is a checksum fail message

                    self._silent_write(b'\r\n')
                    self._silent_write(b'18' + b'\r\n')  # Error

                self._silent_write(b'\r\n')
                self._silent_write(Command.OK + b'\r\n')

            except IridiumError:
                self._mo_status = 10  # Gateway reported that the call did not complete in the allowed time.

                # Message failed
                self._silent_write(b'\r\n')
                self._silent_write(b'10' + b'\r\n')  # Error
                self._silent_write(b'\r\n')
                self._silent_write(Command.OK + b'\r\n')

            except:
                self._mo_status = 14  # Invalid segment size.

                # Message failed
                self._silent_write(b'\r\n')
                self._silent_write(b'14' + b'\r\n')  # Error
                self._silent_write(b'\r\n')
                self._silent_write(Command.OK + b'\r\n')

        # Message with no action
        elif self._read_buf.endswith(b'\r'):
            self.echo_command(cmd)
            self._silent_write(Command.OK + b'\r\n')
    # end check_incoming
# end class IridiumServer


def run_server(port="COM2"):
    """Create an instance of IridiumServer and connect to the given port. This method will run until the user gives
    empty input or types "exit".
    """
    ser = IridiumServer(port)
    ser.connect()

    msg = b" "
    while msg.lower() != b"exit" and msg != b"":
        msg = input("Enter a message to send: ").encode('utf_8').decode('unicode-escape').encode('utf-8')
        ser.write_serial(msg)

    # Wait for the pyiridium.run_communicator to ask for the message and get the exit message
    time.sleep(3)

    ser.close()
# end run_server


if __name__ == "__main__":
    import sys
    import argparse

    # Command Line arguments
    parser = argparse.ArgumentParser(description="Run the iridium server to mock how the iridium modem works.")
    parser.add_argument('port', type=str, help="COM port to use",)

    pargs = parser.parse_args(sys.argv[1:])

    #Run the server
    run_server(pargs.port)
