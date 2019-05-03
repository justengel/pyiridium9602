"""
    pyiridium
    SeaLandAire Technologies
    @author: jengel

Manages iridium satellite communications.
Iridium data sheet: http://www.nalresearch.com/Info/AT%20Commands%20for%20Models%209602.pdf
"""
import time
import serial
import threading
import collections
import contextlib
import datetime

import atexit


__all__ = ['Command', 'MO_STATUS', 'MT_STATUS', 'IridiumError',
           'parse_system_time', 'parse_serial_number', 'parse_signal_quality', 'parse_check_ring',
           'parse_session', 'parse_read_binary', 'has_read_binary_data', 'parse_write_binary',
           'Signal', 'IridiumCommunicator', 'run_serial_log_file', 'run_communicator']


class Command:
    """Commands for Iridium. Maybe in the future make a system where a command is a class associated with a specific 
    parsing action. That would make it easier to add new commands.
    """
    OK = b'OK'
    RING = b'SBDRING'
    READY = b'READY'
    
    PING = b'AT'
    
    ECHO_BASE = b'ATE'
    ECHO_ON = b'ATE1'
    ECHO_OFF = b'ATE0'
    
    FLOW_CONTROL_BASE = b'AT&K'
    FLOW_CONTROL_ON = b'AT&K3'
    FLOW_CONTROL_OFF = b'AT&K0'

    RING_ALERTS_BASE = b'AT+SBDMTA'
    RING_ALERTS_ON = b'AT+SBDMTA=1'
    RING_ALERTS_OFF = b'AT+SBDMTA=0'

    SYSTEM_TIME = b'AT-MSSTM'
    SERIAL_NUMBER = b'AT+CGSN'
    SIGNAL_QUALITY = b'AT+CSQ'
    CHECK_RING = b'AT+CRIS'

    CLEAR_BUFFER = b'AT+SBDD'
    CLEAR_MO_BUFFER = b'AT+SBDD0'
    CLEAR_MT_BUFFER = b'AT+SBDD1'
    CLEAR_BOTH_BUFFERS = b'AT+SBDD2'

    SESSION = b'AT+SBDIX'
    SESSION_RECEIVE = b'+SBDIX:'

    READ_BINARY = b'AT+SBDRB'
    READ_BINARY_RECEIVE = b'AT+SBDRB\r'

    WRITE_BINARY = b'AT+SBDWB='  # length of message
    
    # OTHER COMMANDS
    REPEAT_LAST_COMMAND = b'A/'
    RETURN_ECHO = b'En'
    RETURN_IDENTIFICATION = b'In'

    @classmethod
    def all_commands(cls):
        """Yield all of the commands except for OK, SBDRING, and READY, because they are responses.
        
        Note:
            The command value is yielded so SESSION yields b'AT+SBDIX'.
        """
        for name in dir(cls):
            if not name.startswith(b"_") and name != "OK" and name != "RING" and name != "READY":
                yield getattr(cls, name)

    @classmethod
    def is_command(cls, data):
        """Return if the data is a command."""
        return data in cls.all_commands() or data + b'\r' in cls.all_commands()
# end Command


# MO STATUS
MO_STATUS = dict()
MO_STATUS[0] = "MO message, if any, transferred successfully."
MO_STATUS[1] = ("MO message, if any, transferred successfully, but the MT message in the "
                " queue was too big to be transferred.")
MO_STATUS[2] = ("MO message, if any, transferred successfully, but the requested Location"
                " Update was not accepted.")
MO_STATUS[3] = "Reserved, but indicate MO session success if used."
MO_STATUS[4] = "Reserved, but indicate MO session success if used."

# Failed
MO_STATUS.update({i: "Reserved, but indicate MO session failure if used." for i in range(5, 9)})
MO_STATUS[10] = "Gateway reported that the call did not complete in the allowed time."
MO_STATUS[11] = "MO message queue at the Gateway is full."
MO_STATUS[12] = "MO message has too many segments."
MO_STATUS[13] = "Gateway reported that the session did not complete"
MO_STATUS[14] = "Invalid segment size."
MO_STATUS[15] = "Access is denied."

# 9602-reported values
MO_STATUS[16] = "9602 has been locked and may not make SBD calls (see +CULK command)."
MO_STATUS[17] = "Gateway not responding (local session timeout)."
MO_STATUS[18] = "Connection lost (RF drop)."

MO_STATUS[32] = "No network service, unable to initiate call."
MO_STATUS[33] = "Antenna fault, unable to initiate call."
MO_STATUS[34] = "Radio is disabled, unable to initiate call (see *Rn command)."
MO_STATUS[35] = "9602 is busy, unable to initiate call (typically performing auto-registration)."


# MT STATUS
MT_STATUS = {0: "No MT SBD message to receive from the Gateway.",
             1: "MT SBD message successfully received from the Gateway.",
             2: "An error occurred while attempting to perform a mailbox check or receive a message from the Gateway.",
             }


class IridiumError(Exception):
    """Custom exception for parsing issues and any other issue found."""
    pass


def parse_system_time(data):
    """Parse and return the values.

    Parse the data returned from the message: b'AT-MSSTM'

    Args:
        data (bytes): Data bytes read in.

    Returns:
        system_time (int): System time.

    Raise:
        IridiumError: If the data could not be parsed
    """
    try:
        # Find the Message data
        resp = data.strip()
        idx = resp.find(b"-MSSTM:")
        if idx >= 0:
            resp = resp[idx+7:].strip()
            endline = resp.find(b'\n')
            if endline >= 0:
                resp = resp[:endline].strip()

            # Check the data
            split_resp = resp.decode("utf-8")
            if len(split_resp) >= 8:
                sys_time = int(split_resp, 16)
                return sys_time
    except Exception as err:
        raise IridiumError("Could not parse the system time!") from err
    raise IridiumError("Could not parse the system time!")
# end parse_system_time


def parse_serial_number(data):
    """Parse and return the values.

    Parse the data returned from the message: b'AT+CGSN'

    Args:
        data (bytes): Data bytes read in.

    Returns:
        serial_number (str): Serial number / imei identification number as a sting

    Raise:
        IridiumError: If the data could not be parsed
    """
    try:
        # Find the Message data
        lines = data.splitlines()
        resp = b''
        for line in lines:
            # Check for echo and empty
            line = line.strip()
            if b'AT+CGSN' not in line and b'AT+GSN' not in line and line != b'':
                resp = line
                break

        if resp != Command.OK and data != b'':
            return resp.decode("utf-8")
    except Exception as err:
        raise IridiumError("Could not parse the serial number!") from err
    raise IridiumError("Could not parse the serial number!")
# end parse_serial_number


def parse_signal_quality(data):
    """Parse and return the values.

    Parse the data returned from the message: b'AT+CSQ'

    Args:
        data (bytes): Data bytes read in.

    Returns:
        sig (int): Signal quality number (0 - 5) 

    Raise:
        IridiumError: If the data could not be parsed
    """
    try:
        # Find the Message data
        resp = data.strip()
        idx = resp.find(b"+CSQ:")
        if idx >= 0:
            resp = resp[idx+5:].strip()
            endline = resp.find(b'\n')
            if endline >= 0:
                resp = resp[:endline].strip()

            # Check the data
            split_resp = resp.decode("utf-8")
            sig = int(split_resp)
            return sig
    except Exception as err:
        raise IridiumError("Could not parse the signal quality!") from err
    raise IridiumError("Could not parse the signal quality!")
# end parse_signal_quality


def parse_check_ring(data):
    """Parse and return the values.

    Parse the data returned from the message: b'AT+CRIS'

    Args:
        data (bytes): Data bytes read in.

    Returns:
        tri (int): Telephone ring indication status
        sri (int): SBD ring indication status

    Raise:
        IridiumError: If the data could not be parsed
    """
    try:
        # Find the Message data
        resp = data.strip()
        idx = resp.find(b"+CRIS:")
        if idx >= 0:
            resp = resp[idx+6:].strip()
            endline = resp.find(b'\n')
            if endline >= 0:
                resp = resp[:endline].strip()

            # Check the data
            split_resp = resp.decode("utf-8")
            parts = split_resp.split(",")
            tri = int(parts[0])  # indicates the telephony ring indication status
            sri = int(parts[1])  # indicates the SBD ring indication status
            return tri, sri
    except Exception as err:
        raise IridiumError("Could not parse the check ring response!") from err
    raise IridiumError("Could not parse the check ring response!")
# end parse_check_ring


def parse_session(data):
    """Parse and return the values.

    Parse the data returned from the message: b'AT+SBDIX'

    Args:
        data (bytes): Data bytes read in.

    Returns:
        mo_status (int): Outgoing status
        mo_msn (int): Outgoing message serial number
        mt_status (int): Incoming status
        mt_msn (int): Incoming message serial number
        mt_length (int): Incoming message length
        mt_queued (int): Number of incoming messages queued

    Raise:
        IridiumError: If the data could not be parsed
    """
    try:
        # Find the Message data
        resp = data.strip()
        idx = resp.find(b"+SBDIX:")
        if idx >= 0:
            resp = resp[idx+7:].strip()
            endline = resp.find(b'\n')
            if endline >= 0:
                resp = resp[:endline].strip()

            # Check the data
            split_resp = resp.decode("utf-8")
            parts = split_resp.split(",")

            mo_status = int(parts[0])
            mo_msn = int(parts[1])
            mt_status = int(parts[2])
            mt_msn = int(parts[3])
            mt_length = int(parts[4])
            mt_queued = int(parts[5])
            return mo_status, mo_msn, mt_status, mt_msn, mt_length, mt_queued

    except Exception as err:
        raise IridiumError("Could not parse the session!") from err
    raise IridiumError("Could not parse the session!")
# end parse_session


def parse_read_binary(data):
    """Parse and return the values.

    Parse the data returned from the message: b'AT+SBDRB'

    Args:
        data (bytes): Data bytes read in.

    Returns:
        msg_len (int): Message content length (will not exceed 270 or 340).
        content (bytes): Message content
        checksum (bytes): 2 checksum bytes included in the read binary message
        calc_check (bytes): 2 calculated checksum bytes from the message content.

    Raise:
        IridiumError: If the data could not be parsed
    """
    try:
        idx = data.find(b"AT+SBDRB\r")
        if idx >= 0:
            data = data[idx+9:]

        # Check the data
        msg_len = int.from_bytes(data[:2], "big")
        content = data[2: msg_len + 2]
        checksum = data[msg_len + 2: msg_len + 2 + 2]
        if len(checksum) != 2:
            raise ValueError("Not enough data given!")

        # Calculate the checksum
        calc_check = int(sum(content)).to_bytes(4, 'big')[2:]  # smallest 2 bytes of the sum

        return msg_len, content, checksum, calc_check

    except Exception as err:
        raise IridiumError("Could not parse the read binary response!") from err
# end parse_read_binary


def has_read_binary_data(data):
    """Return True if the given data has enough data for the read binary command. 

    Parse the data returned from the message: b'AT+SBDRB'

    Args:
        data (bytes): Data bytes read in.

    Returns:
        has_length (bool): True if there is enough data
    """
    try:
        idx = data.find(b"AT+SBDRB\r")
        if idx >= 0:
            data = data[idx+9:]
    
        # Check the data
        msg_len = int.from_bytes(data[:2], "big")
        # content = data[2: msg_len + 2]
        checksum = data[msg_len + 2: msg_len + 2 + 2]
        if len(checksum) != 2:
            return False
        return True

    except (AttributeError, ValueError, TypeError):
        return False
# end has_read_binary_data


def parse_write_binary(data):
    """Parse and return the values.
    
    Parse the data returned from the message: b'AT+SBDWB=' # length of message
    
    Args:
        data (bytes): Data bytes read in.
        
    Returns:
        success (bool): Return True if the response was b'0' after the ready and write message were already complete.
    """
    resp = data.strip()
    
    # Check the last value since OK should be after this
    try:
        return bytes([resp[-1]]) == b'0'
    except IndexError:
        pass
    raise IridiumError("Could not parse the write binary response!")
# end parse_write_binary


class Signal(object):
    def connecting(self):
        """This method is called when the connection process is about to start."""
        pass

    def connected(self):
        """This method is called after the connection is verified."""
        pass
    
    def disconnecting(self):
        """This method is called when the disconnecting process is about to start."""
        pass

    def disconnected(self):
        """This method is called after the connection is closed."""
        pass

    def system_time_updated(self, system_time):
        """This method is called after the system time was requested and received."""
        pass

    def serial_number_updated(self, sn):
        """This method is called after the serial number was requested and received."""
        pass

    def signal_quality_updated(self, signal):
        """This method is called after a new signal quality has been received."""
        pass

    def check_ring_updated(self, tri, sri):
        """This method is called after a new check ring response has been received.
        
        Args:
            tri (int): Telephone ring indicator
            sri (int): SBD ring indicator
        """
        pass

    def message_received(self, data):
        """This method is called after a message has been received and has passed the checksum.
        
        Args:
            data (bytes): Message contents without the length or checksum bytes.
        """
        pass

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
        pass
    
    def message_transferred(self, mo_msn):
        """This method is called after a session indicates that a message has been transferred successfully."""
        pass
    
    def message_transfer_failed(self, mo_msn):
        """This method is called after a session indicates that a message transfer has failed."""
        pass
    
    def notification(self, ntype, message, additional_info):
        """This method notifies when something has happened.
        
        Args:
            ntype (str): Notification type. "Error", "Success", "Warning", "Info"
            message (str): Message string of what happened.
            additional_info (str): Extra information to help explain what happened.
        """
        print(ntype, message, additional_info)
        
    def command_finished(self, cmd, value, contents=b''):
        """This method is called for the AsyncIridiumCommunicator after a command was called. Value is a boolean if OK
        was read.
        
        Args:
            cmd (bytes): Command bytes that were sent to issue a command
            value (bool): True or False if parsing the command was successful and OK was found as a response.
            contents (bytes)[b'']: Bytes associated with the response.
        """
        pass
    
    API = ['connecting', 'connected', 'disconnecting', 'disconnected', 
           'system_time_updated', 'serial_number_updated', 'signal_quality_updated', 'check_ring_updated',
           'message_received', 'message_receive_failed', 'message_transferred', 'message_transfer_failed',
           'notification', 'command_finished']

    @staticmethod
    def set_to_print(signal):
        """Set the signal to print everything to the console.
        
        Args:
            signal (object): Generally a Signal object, but it can be anything. All of the Signal.API methods will print
                to the console.
        """
        signal.connecting = lambda: print("Connecting!")
        signal.connected = lambda: print("Connected!")
        signal.disconnecting = lambda: print("Disconnecting!")
        signal.disconnected = lambda: print("Disconnected!")
        signal.system_time_updated = lambda s: print("System Time:", s)
        signal.serial_number_updated = lambda s: print("Serial Number:", s)
        signal.signal_quality_updated = lambda s: print("Signal Quality (0-5):", s)
        signal.check_ring_updated = lambda t, s: print("Telephone Ring Indicator:", t,
                                                       "SBD Ring Indicator:", s)
        signal.message_received = lambda s: print("Message Received:", s)
        signal.message_receive_failed = lambda l, c, ck, cc: print("Message Failed!", 
                                                                   "Length:", l,
                                                                   "Content:", c,
                                                                   "Checksum:", ck,
                                                                   "Calc Checksum:", cc)
        signal.message_transferred = lambda s: print("Message Transferred:", s)
        signal.message_transfer_failed = lambda s: print("Message Transfer Failed:", s)
        signal.notification = lambda et, m, a: print("Notification:", et, m, repr(a))
        signal.command_finished = lambda cmd, v, c: print("Command Finished:", cmd, v, c)
    # end set_to_print
# end class Signal


class IridiumCommunicator(object):
    """Communicates with an iridium modem through a serial port.
    
    Note:
        IridiumCommunicator().connect() should be called to connect the serial port.
        
    Note:
        It is suggested that you use the "queue_" commands when writing to the serial port. If you call a request 
        command be careful to wait until the command is finished until you call another request command. You can wait
        for commands to finish by using the `IridiumCommunicator.wait_for_command` context manager or by calling the
        appropriate `acquire_response` method. 

    Args:
        serialport(serial.Serial/str): Serial port or string com port name.
        signal (Signal)[None]: Signal object with methods for custom actions.
        options (dict): Dictionary of options 'echo', 'ring_alerts', 'auto_read', 'flow_control', 'telephone'.
    """

    DEFAULT_OPTIONS = {'echo': True,
                       'ring_alerts': True,
                       'auto_read': True,
                       'flow_control': False,
                       'telephone': False,
                       }

    # Iridium epoch will change about every 12 years
    IRIDIUM_EPOCH_STR = "Mar 8, 2007, 03:50:35 (GMT)"
    IRIDIUM_EPOCH = datetime.datetime.strptime(IRIDIUM_EPOCH_STR, "%b %d, %Y, %H:%M:%S (%Z)")

    def __init__(self, serialport=None, signal=None, options=None):
        super().__init__()
        
        # Close when the program exits
        def safe_close():
            try: self.close()
            except (RuntimeError, AttributeError): pass
        atexit.register(safe_close)

        # Protocol callback methods
        self._signal = None
        if signal is None:
            signal = Signal()
        self.set_signal(signal)

        # Communication options
        self.options = self.DEFAULT_OPTIONS.copy()
        if isinstance(options, dict):
            self.options.update(options)

        # Control states
        self._active = threading.Event()
        self._connected = False

        # Variables
        self._serialport = serial.Serial()
        self._timeout = 0.01
        self._connect_timeout = 2
        self._serial_number = ""
        self._last_mt_queued = 0
        self._last_mt_queued_retry = 0
        self._read_buf = b''
        self._write_queue = collections.deque(maxlen=100)
        self._sequential_write_queue = collections.deque(maxlen=100)
        self._previous_command = None
        self._que_next_command = False
        self.listen_thread = None

        if serialport is not None:
            self.serialport = serialport
    # end Constructor

    @property
    def signal(self):
        """Return the signal object."""
        return self._signal

    @signal.setter
    def signal(self, value):
        """Set the signal and make sure all of the functions are callable."""
        self.set_signal(value)

    def set_signal(self, value):
        """Set the signal and make sure all of the functions are callable."""
        self._signal = value

        if self._signal is not None:
            # Force all Signal methods to exist
            for key in Signal.API:
                attr = getattr(self._signal, key, None)
                if attr is None:
                    if key == "notification":
                        setattr(self._signal, key, print)
                    else:
                        # Set an empty function
                        setattr(self._signal, key, lambda *args, **kwargs: None)
                elif not callable(attr):
                    raise IridiumError("Signal must have the attribute " + repr(key) + " callable!")
        else:
            self._signal = Signal()
    # end signal
    
    @property
    def serial_number(self):
        """Return the serial number or imei number."""
        return self._serial_number

    @serial_number.setter
    def serial_number(self, value):
        self._serial_number = value

    @property
    def imei(self):
        """Return the serial number or imei number."""
        return self.serial_number

    @imei.setter
    def imei(self, value):
        self.serial_number = value

    @property
    def serialport(self):
        """Return the serial port object.
        
        Note:
            IridiumCommunicator().connect should be called to connect the serial port.
        """
        return self._serialport

    @serialport.setter
    def serialport(self, serialport):
        """Set the serial port with a serial port object."""
        if isinstance(serialport, str):
            self._serialport.port = serialport
        else:
            self._serialport = serialport
        self._serialport.baudrate = 19200
        self._serialport.timeout = self.timeout
        self._serialport.write_timeout = 0
    # end serialport
    
    @property
    def timeout(self):
        """Return the main serialport readline timeout. This is the timeout used for most read communications.
        
        A larger timeout has a higher chance of success, but may take a lot longer for every operation.
        """ 
        return self._timeout

    @timeout.setter
    def timeout(self, value):
        self._timeout = value
        self.serialport.timeout = self._timeout
    # end timeout

    @property
    def connect_timeout(self):
        """Return the timeout for readline when you are connecting to the iridium modem.
        
        The initial connection has several steps including setting the echo, flow control, ring alerts, and two pings 
        to ensure that the iridium modem is setup properly. If any of these fails with the normal timeout the 
        connection process takes a long time and may freeze your application.
        """
        return self._connect_timeout

    @connect_timeout.setter
    def connect_timeout(self, value):
        self._connect_timeout = value
    # end connect_timeout
    
    def read_serial(self):
        """Serial port readline command that can be overwritten with inheritance to log data. This should return all 
        characters that were read in.
        """
        try:
            return self.serialport.readline()
        except Exception as err:
            self.signal.notification("Error", "Error when reading from the serial port! The connection will be closed!",
                                     str(err))
            self.close()
            return b''
    # end read_serial
    
    def write_serial(self, msg):
        """Serial port write command that can be overwritten with inheritance to log data."""
        try:
            self.serialport.write(msg)
        except Exception as err:
            self.signal.notification("Error", "Error when writing to the serial port! The connection will be closed!",
                                     str(err))
            self.close()
    # end write_serial

    def start_thread(self):
        """Start a thread to listen for responses."""
        # Check if there is a thread listening.
        if not self.is_listening() and self.listen_thread is None:
            self.signal.notification("Warning", "No threads are listening for responses. A thread will be created", "")
            self.listen_thread = threading.Thread(target=self.listen)
            self.listen_thread.daemon = True  # Close at program exit. Otherwise the program will remain open.
            self.listen_thread.start()
    # end start_thread

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

        # Configure the port options
        if not self.configure_connection_options():
            raise IridiumError("Could not configure the port options!")

        # Ping and wait for a response
        with self.wait_for_command(self.connect_timeout, wait_for_previous=0):
            self.ping()
        
        # Check if ping failed    
        if self.pending_command() is not None:
            self.close()
            raise IridiumError("Could not connect. The ping did not find a response!")

        # Ping and wait for a response    
        with self.wait_for_command(self.connect_timeout, wait_for_previous=0):
            self.ping()

        # Check if ping failed
        if self.pending_command() is not None:
            self.close()
            raise IridiumError("Could not connect. The ping did not find a response!")

        # Connected signal
        self._connected = True
        self.signal.connected()
    # end connect

    def silent_connect(self, port_id=None):
        """Connect without pinging or configuring the port options.

        Args:
            port_id (str/serial.Serial): COM port string or serial object.

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

        # Connected signal
        self._connected = True
        self.signal.connected()
    # end silent_connect

    def close(self):
        """Close the serial port properly."""
        # Disconnecting signal
        self.signal.disconnecting()
        try:
            self.stop_listening()
        except:
            pass

        try:
            self.serialport.close()
        except:
            pass
        self._connected = False
        
        # Disconnected signal
        self.signal.disconnected()
    # end close

    def is_port_connected(self):
        """Return if the serial port is connected."""
        return self.serialport is not None and self.serialport.isOpen()

    def is_connected(self):
        """Return if the serial port is connected."""
        return self.is_port_connected() and self._connected
    
    def is_listening(self):
        """Return if the IridiumCommunicator is actively listening."""
        return self._active.is_set()
    
    def set_listening(self, value):
        """Set if the IridiumCommunicator is listening for responses."""
        if value:
            self._active.set()
        else:
            self.stop_listening()

    def stop_listening(self):
        """Stop the IridiumCommunicator from listening."""
        self._active.clear()
        try:
            self.listen_thread.join()
        except AttributeError:
            pass
        self.listen_thread = None

    def listen(self):
        """Continuously listen for commands. (This method should be called in a separate thread).

        Raises:
            IridiumError: If there is already a thread listening. Multiple threads will mess up the internal read buffer
        """
        # Check if there is another thread listening
        if self.is_listening():
            raise IridiumError("There is already a thread listening!")

        self._active.set()
        while self.is_listening():
            if self.is_port_connected():
                data = self.read_serial()
                self.check_io(data)
            time.sleep(0.001)  # prevent the thread from being greedy when not connected
    # end listen

    def check_io(self, message=b''):
        """Check for incoming and outgoing messages."""
        # Add the message to the existing buffer
        self._read_buf += message

        # Check if in a command
        if self.pending_command():
            self.check_pending_command()
        else:
            self.check_unsolicited()
    # end check_io

    def check_pending_command(self):
        """Check the incoming messages for responses from the previous command."""
        # Check for an OK
        if Command.OK in self._read_buf:

            # Split out the command from the buff
            command_success = True
            idx = self._read_buf.index(Command.OK)
            data = self._read_buf[:idx]
            self._read_buf = self._read_buf[idx+2:]

            # Check the commands
            if Command.SYSTEM_TIME == self._previous_command:
                try:
                    sys_time = parse_system_time(data)
                    self.signal.system_time_updated(sys_time)
                except IridiumError as err:
                    self.signal.notification("Error", "Could not parse the system time response", str(err))
                    command_success = False

            elif Command.SERIAL_NUMBER == self._previous_command:
                try:
                    sn = parse_serial_number(data)
                    self.serial_number = sn
                    self.signal.serial_number_updated(sn)
                except IridiumError as err:
                    self.signal.notification("Error", "Could not parse the serial number response", str(err))
                    command_success = False

            elif Command.SIGNAL_QUALITY == self._previous_command:
                try:
                    sig = parse_signal_quality(data)
                    self.signal.signal_quality_updated(sig)
                except IridiumError as err:
                    self.signal.notification("Error", "Could not parse the signal quality response", str(err))
                    command_success = False

            elif Command.CHECK_RING == self._previous_command:
                try:
                    tri, sri = parse_check_ring(data)
                    self.signal.check_ring_updated(tri, sri)

                    # Handle the response
                    if sri > 0 and not self.get_option('telephone') and self.get_option('auto_read'):
                        self.queue_session()

                except IridiumError as err:
                    self.signal.notification("Error", "Could not parse the check ring response", str(err))
                    command_success = False

            elif Command.SESSION == self._previous_command:
                try:
                    mo_status, mo_msn, mt_status, mt_msn, mt_length, mt_queued = parse_session(data)

                    # ========== Run operations from parsed message ==========
                    # Check outgoing
                    if 4 >= mo_status >= 0:
                        self.queue_clear_mo_buffer()

                        # Success - Message Transferred signal
                        self.signal.message_transferred(mo_msn)
                    else:
                        # Failed - Message Transfer Failed signal
                        self.signal.notification("Error", "Message Transfer Failed!",
                                                 MO_STATUS.get(mo_status, "Unknown failure!"))
                        self.signal.message_transfer_failed(mo_msn)

                    # Check if there is a message to process - mt_status 0 no message, 1 success, 2 fail
                    if mt_status == 1 and mt_length > 0:
                        self._last_mt_queued = mt_queued
                        self._last_mt_queued_retry = 0
                        self.queue_read_binary_message()

                    elif mt_status > 1:
                        self.signal.notification("Error", "Message Receive Failed!",
                                                 MT_STATUS.get(mt_status, "Unknown error!"))

                        # An error happened! Check the last mt_queued value to see if we should retry
                        if mt_queued == 0 and self._last_mt_queued > 1 and self._last_mt_queued_retry < 2:
                            time.sleep(0.5)  # Wait some time to retry
                            mt_queued = self._last_mt_queued
                            self._last_mt_queued_retry += 1

                    # Check for additional messages until the queue is empty
                    if mt_queued > 0 and self.get_option("auto_read"):
                        self.queue_session()

                except IridiumError as err:
                    self.signal.notification("Error", "Could not parse the session response", str(err))
                    command_success = False
        
            # Read Binary
            elif Command.READ_BINARY == self._previous_command:
                # Check if the read binary command has received enough data
                while not has_read_binary_data(data) and Command.OK in self._read_buf:
                    idx = self._read_buf.index(Command.OK)
                    data = data + Command.OK + self._read_buf[:idx]
                    self._read_buf = self._read_buf[idx+2:]

                # Final check for data
                if not has_read_binary_data(data):
                    self._read_buf = data + Command.OK + self._read_buf
                    print("here", data, self._read_buf)
                    return

                # Parse the data
                try:
                    msg_len, content, checksum, calc_check = parse_read_binary(data)
    
                    # Check if the message is valid
                    if msg_len == len(content) and calc_check == checksum:
                        # Message received successfully
                        self.signal.message_received(content)
                    else:
                        # Message Receive Failed signal
                        self.signal.message_receive_failed(msg_len, content, checksum, calc_check)
    
                except IridiumError as err:
                    self.signal.notification("Error", "Could not parse the read binary data", str(err))
                    command_success = False

            # Write Binary
            elif Command.WRITE_BINARY == self._previous_command:
                try:
                    command_success = parse_write_binary(data)
                except IridiumError as err:
                    self.signal.notification("Error", "Could not parse the write binary response", str(err))
                    command_success = False

            # Clear Buffer (MO or MT or both)
            elif Command.CLEAR_BUFFER in self._previous_command:
                # The data should be b'0'
                resp = data.replace(Command.CLEAR_MO_BUFFER, b'').replace(Command.CLEAR_MO_BUFFER, b'')\
                    .replace(Command.CLEAR_BOTH_BUFFERS, b'').strip()
                if resp != b'0':
                    command_success = False

            # A message completed
            self.signal.command_finished(self._previous_command, command_success, data)
            self._previous_command = None

        # Check for a READY
        elif Command.READY in self._read_buf and Command.READ_BINARY != self._previous_command:

            # Split out the command from the buff
            command_success = True
            idx = self._read_buf.index(Command.READY)
            data = self._read_buf[:idx]
            self._read_buf = self._read_buf[idx + len(Command.READY):]

            # Check the commands that use "READY"
            if self._previous_command.startswith(Command.WRITE_BINARY):
                # Write a binary message
                message = self._write_queue.popleft()
                # msg_length already given with the write binary message
                checksum = int(sum(message)).to_bytes(4, 'big')[2:]  # smallest 2 bytes of the sum
                self.write_serial(message + checksum)

            # A message with no known response completed
            self.signal.command_finished(self._previous_command, command_success, data)
            self._previous_command = None        
    # end check_pending_command

    def check_unsolicited(self):
        """Check the buffers for an unsolicited command or a queued write message."""
        # Check for unsolicited messages
        if Command.RING in self._read_buf:
            # Ring received check for messages
            idx = self._read_buf.index(Command.RING)
            self._read_buf = self._read_buf[idx + len(Command.RING):]

            if Command.SESSION not in self._sequential_write_queue:
                self.queue_session()

        elif len(self._sequential_write_queue) > 0:
            # Write messages from the queue
            self._previous_command = self._sequential_write_queue.popleft()
            self.write_serial(self.previous_command + b'\r')
            self._read_buf = b''

        else:
            # Trim the buffer if no unsolicited messages were found and there are no pending commands
            try:
                self._read_buf = self._read_buf.splitlines()[-1]
            except IndexError:
                pass
    # end check_unsolicited

    @property
    def previous_command(self):
        """Private variable storing the previous command."""
        return self._previous_command

    @previous_command.setter
    def previous_command(self, command):
        """Set a command as pending."""
        if self._previous_command and command is None:
            self.signal.command_finished(self._previous_command, True)
        elif self._previous_command:
            self.signal.command_finished(self._previous_command, False)
        self._previous_command = command
    # end previous_command

    def pending_command(self):
        """Return if the system is waiting for a command to finish and return the command that was called."""
        return self._previous_command
    # end pending_command

    @contextlib.contextmanager
    def wait_for_command(self, wait_time=120, wait_for_previous=120):
        """Wait for a command to run and respond okay (clearing the previous command).

        Note:
            You can check if the command was successful and did not timeout by using 
            `success = self.pending_command() is None`

        Args:
            wait_time (float)[120]: Time in seconds to wait for the command to complete.
            wait_for_previous (float)[120]: Time in seconds to wait for the previous command to finish
        """
        # Wait for previous command to finish
        start = time.time()
        while (self.pending_command() or len(self._sequential_write_queue) > 0) and (
                time.time() - start < wait_for_previous):
            time.sleep(0.001)

        yield

        # Wait for this command to finish and nested commands to finish
        start = time.time()
        while self.pending_command() and (time.time() - start < wait_time):
            time.sleep(0.001)
    # end wait_for_command

    def acquire_response(self, command, wait_time=120, wait_for_previous=120):
        """Wait for a command to run and return the value for that command.

        Args:
            command (bytes/str): Command to send and get the response for. This should only be one command message!
            wait_time (float)[120]: Time in seconds to wait for the command to complete.
            wait_for_previous (float)[120]: Time in seconds to wait for the previous command to finish

        Raises:
            IridiumError: If no values were found

        Returns:
            values (tuple): Returns the values that would be collected from the corresponding callback method.
        """
        if isinstance(command, str):
            command = command.encode("utf-8")

        # Get the old signal values
        old_system_time = self.signal.system_time_updated
        old_serial_number = self.signal.serial_number_updated
        old_signal_quality = self.signal.signal_quality_updated
        old_check_ring = self.signal.check_ring_updated
        old_command_finished = self.signal.command_finished

        # Create a collection method to collect the value
        values = []

        # Collect command finished data for unknown commands
        cmd_finish = []

        def command_finished(cmd, val, content=b''):
            """"Find where commands finished True for unknown commands."""
            if val and cmd == command and len(values) == 0:
                values.append(content)  # May be empty
            old_command_finished(cmd, val, content)

        # Replace the signal callbacks with the collect callback
        self.signal.system_time_updated = lambda s: values.append(s)
        self.signal.serial_number_updated = lambda s: values.append(s)
        self.signal.signal_quality_updated = lambda s: values.append(s)
        self.signal.check_ring_updated = lambda tri, sri: values.append((tri, sri))

        # Run the command and wait for it to finish
        with self.wait_for_command(wait_time, wait_for_previous):
            self.previous_command = command
            self.signal.command_finished = command_finished
            self.write_serial(self.previous_command + b"\r")

        # Replace the signal callbacks with their original methods
        self.signal.system_time_updated = old_system_time
        self.signal.serial_number_updated = old_serial_number
        self.signal.signal_quality_updated = old_signal_quality
        self.signal.check_ring_updated = old_check_ring
        self.signal.command_finished = old_command_finished

        # Return the collected values or raise an IridiumError
        if len(values) == 0:
            # No known values were parsed try to find if an unknown command was sent
            if len(cmd_finish) == 0:
                # No commands finished successfully
                raise IridiumError("The command timed out or completed without returning a proper value!")
            values.append(cmd_finish[-1][2])  # Return the found content

        # Unpack the last value
        if isinstance(values[-1], (list, tuple)) and len(values[-1]) == 1:
            return values[-1][0]
        return values[-1]
    # end acquire_response
    
    def _acquire_response(self, command, wait_time=120, wait_for_previous=120):
        """Wait for a command to run and return the value for that command.

        This command does not look for unknown commands!

        See Also:
            acquire_response

        Args:
            command (bytes/str): Command to send and get the response for. This should only be one command message!
            wait_time (float)[120]: Time in seconds to wait for the command to complete.
            wait_for_previous (float)[120]: Time in seconds to wait for the previous command to finish

        Returns:
            values (tuple): Returns the values that would be collected from the corresponding callback method.

        Raises:
            IridiumError: If no values were found
        """
        if isinstance(command, str):
            command = command.encode("utf-8")

        # Get the old signal values
        old_system_time = self.signal.system_time_updated
        old_serial_number = self.signal.serial_number_updated
        old_signal_quality = self.signal.signal_quality_updated
        old_check_ring = self.signal.check_ring_updated

        # Create a collection method to collect the value
        values = []

        # Replace the signal callbacks with the collect callback
        self.signal.system_time_updated = lambda s: values.append(s)
        self.signal.serial_number_updated = lambda s: values.append(s)
        self.signal.signal_quality_updated = lambda s: values.append(s)
        self.signal.check_ring_updated = lambda tri, sri: values.append((tri, sri))

        # Run the command and wait for it to finish
        with self.wait_for_command(wait_time, wait_for_previous):
            self.previous_command = command
            self.write_serial(self.previous_command + b"\r")

        # Replace the signal callbacks with their original methods
        self.signal.system_time_updated = old_system_time
        self.signal.serial_number_updated = old_serial_number
        self.signal.signal_quality_updated = old_signal_quality
        self.signal.check_ring_updated = old_check_ring

        # Return the collected values or raise an IridiumError
        if len(values) == 0:
            raise IridiumError("The command timed out or completed without returning a proper value!")

        # Unpack the last value
        if isinstance(values[-1], (list, tuple)) and len(values[-1]) == 1:
            return values[-1][0]
        return values[-1]
    # end _acquire_response

    def queue_command(self, command):
        """Queue a command to be written later in with the thread in the `check_unsolicited` method (inside `check_io`).
        
        This method should only be used when you have threading using `check_io` (`listen` uses `check_io`).
        The main reading loop `check_io` uses this method for any received messages that need to send messages in 
        a nested way. It preserves the `pending_command()` and `Signal.command_finished` methods.
        """
        self._sequential_write_queue.append(command)
    # end queue_command

    def get_option(self, option_name):
        """Get the value for the option.

        See Also:
            DEFAULT_OPTIONS
        """
        return self.options.get(str(option_name).lower(), False)
    # end get_option

    def set_option(self, option_name, value):
        """Set the given option.
        
        Note:
            Some of the options must be set before the connection has been made!
        """
        self.options[str(option_name).lower()] = value
    # end set_option.

    def configure_connection_options(self):
        """Configure port options for 'echo', 'flow_control', and 'ring_alerts'."""
        with self.wait_for_command(self.connect_timeout, wait_for_previous=0):
            self.set_echo(self.get_option("echo"))
        
        if self.pending_command() is None:
            with self.wait_for_command(self.connect_timeout, wait_for_previous=0):
                self.set_flow_control(self.get_option("flow_control"))
        else:
            return False
        
        if self.pending_command() is None:
            with self.wait_for_command(self.connect_timeout, wait_for_previous=0):        
                self.set_ring_alerts(self.get_option("ring_alerts"))
        else:
            return False

        return self.pending_command() is None
    # end configure_connection_options

    def ping(self):
        """Ping the connection."""
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False
        
        self.previous_command = Command.PING
        self.write_serial(self.previous_command + b'\r')
    # end ping

    def is_echo(self):
        """Return if the echo command is on."""
        return self.get_option('echo')

    def set_echo(self, value=True):
        """Send the echo command."""
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False

        self.set_option('echo', value)
        if value:
            self.previous_command = Command.ECHO_ON
        else:
            self.previous_command = Command.ECHO_OFF
        self.write_serial(self.previous_command + b'\r')
    # end set_echo
    
    def set_flow_control(self, value=True):
        """Send the flow control command."""
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False

        self.set_option('flow_control', value)
        if value:
            self.previous_command = Command.FLOW_CONTROL_ON
        else:
            self.previous_command = Command.FLOW_CONTROL_OFF
        self.write_serial(self.previous_command + b'\r')
    # end set_flow_control
    
    def set_ring_alerts(self, value=True):
        """Send the ring alerts command."""
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False

        self.set_option('ring_alerts', value)
        if value:
            self.previous_command = Command.RING_ALERTS_ON
        else:
            self.previous_command = Command.RING_ALERTS_OFF
        self.write_serial(self.previous_command + b'\r')
    # end set_ring_alerts

    def request_system_time(self):
        """Request the system time."""
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False

        self.previous_command = Command.SYSTEM_TIME
        self.write_serial(self.previous_command + b'\r')
    # end request_system_time
    
    def queue_system_time(self):
        """Queue the system time message."""
        self.queue_command(Command.SYSTEM_TIME)

    def acquire_system_time(self, wait_time=120, wait_for_previous=120):
        """Wait for the response and return the system time.
        
        Args:
            wait_time (float)[120]: Time in seconds to wait for the command to complete.
            wait_for_previous (float)[120]: Time in seconds to wait for the previous command to finish

        Returns:
            system_time (int): System time.

        Raises:
            IridiumError: If no values were found
        """
        return self._acquire_response(Command.SYSTEM_TIME, wait_time=wait_time, wait_for_previous=wait_for_previous)
    # end acquire_system_time

    def request_serial_number(self):
        """Request the system serial number or IMEI number."""
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False

        self.previous_command = Command.SERIAL_NUMBER
        self.write_serial(self.previous_command + b'\r')
    # end request_serial_number

    def queue_serial_number(self):
        """Queue the serial number message."""
        self.queue_command(Command.SERIAL_NUMBER)

    def acquire_serial_number(self, wait_time=120, wait_for_previous=120):
        """Wait for the response and return the serial number.

        Args:
            wait_time (float)[120]: Time in seconds to wait for the command to complete.
            wait_for_previous (float)[120]: Time in seconds to wait for the previous command to finish

        Returns:
            serial_number (str): Serial number / imei identification number as a sting

        Raises:
            IridiumError: If no values were found
        """
        return self._acquire_response(Command.SERIAL_NUMBER, wait_time=wait_time, wait_for_previous=wait_for_previous)
    # end acquire_serial_number

    def request_signal_quality(self):
        """Request the signal strength the values returned should be from 0 - 5 with 2 as the signal threshold. You
        should not really request messages unless you have a signal quality of 2 or more.
        
        Returns:
            sig (int): 0-5 for signal quality. -1 if the request did not return properly.
        """ 
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False

        self.previous_command = Command.SIGNAL_QUALITY
        self.write_serial(self.previous_command + b'\r')
    # end request_signal_quality

    def queue_signal_quality(self):
        """Queue the signal quality message."""
        self.queue_command(Command.SIGNAL_QUALITY)

    def acquire_signal_quality(self, wait_time=120, wait_for_previous=120):
        """Wait for the response and return the serial number.

        Args:
            wait_time (float)[120]: Time in seconds to wait for the command to complete.
            wait_for_previous (float)[120]: Time in seconds to wait for the previous command to finish

        Returns:
            sig (int): Signal quality number (0 - 5) 

        Raises:
            IridiumError: If no values were found
        """
        return self._acquire_response(Command.SIGNAL_QUALITY, wait_time=wait_time, wait_for_previous=wait_for_previous)
    # end acquire_signal_quality

    def check_ring(self):
        """Check if the modem has received a ring."""
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False

        self.previous_command = Command.CHECK_RING
        self.write_serial(self.previous_command + b'\r')
    # end check_ring
    
    def queue_check_ring(self):
        """Queue the check ring message."""
        self.queue_command(Command.CHECK_RING)
        
    def acquire_ring(self, wait_time=120, wait_for_previous=120):
        """Wait for the response and return the telephone indicator and SBD indicator.

        Args:
            wait_time (float)[120]: Time in seconds to wait for the command to complete.
            wait_for_previous (float)[120]: Time in seconds to wait for the previous command to finish

        Returns:
            tri (int): Telephone Ring Indicator
            sri (int): SBD Ring Indicator

        Raises:
            IridiumError: If no values were found
        """
        return self._acquire_response(Command.CHECK_RING, wait_time=wait_time, wait_for_previous=wait_for_previous)
    # end acquire_signal_quality

    def clear_mo_buffer(self):
        """Clear the mo transmit buffer."""
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False

        self.previous_command = Command.CLEAR_MO_BUFFER
        self.write_serial(self.previous_command + b'\r')
    # end clear_mo_buffer

    def queue_clear_mo_buffer(self):
        """Queue the clear mo buffer message."""
        self.queue_command(Command.CLEAR_MO_BUFFER)

    def clear_mt_buffer(self):
        """Clear the mt receive buffer."""
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False

        self.previous_command = Command.CLEAR_MT_BUFFER
        self.write_serial(self.previous_command + b'\r')
    # end clear_mt_buffer

    def queue_clear_mt_buffer(self):
        """Queue the clear mt receive message."""
        self.queue_command(Command.CLEAR_MT_BUFFER)

    def clear_both_buffers(self):
        """Clear the mo transmit and the mt receive buffer."""
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False

        self.previous_command = Command.CLEAR_BOTH_BUFFERS
        self.write_serial(self.previous_command + b'\r')
    # end clear_both_buffer

    def queue_clear_both_buffer(self):
        """Queue the clear mo transmit and mt receive message."""
        self.queue_command(Command.CLEAR_BOTH_BUFFERS)

    def check_message(self):
        """Check for a message by using a session."""
        self.initiate_session()
    # end check_message
    
    def acquire_message(self, wait_time=120, wait_for_previous=120):
        """Wait for the response and return the read binary message.
        
        Note:
            This method temporarily turns off the 'auto_read' option, so you should only receive one message at a time.

        Args:
            wait_time (float)[120]: Time in seconds to wait for the command to complete.
            wait_for_previous (float)[120]: Time in seconds to wait for the previous command to finish

        Returns:
            message (bytes): The message that was received.

        Raises:
            IridiumError: If no values were found.
        """
        # Get the old signal values
        old_read = self.get_option("auto_read")
        old_message_received = self.signal.message_received
        old_message_receive_failed = self.signal.message_receive_failed

        # Create a collection method to collect the value
        values = []

        def collect_values(data):
            values.append(data)

        def msg_failed(msg_len, content, checksum, calc_check):
            values.append(content)

        # Replace the signal callbacks with the collect callback
        self.set_option("auto_read", False)
        self.signal.message_received = collect_values
        self.signal.message_receive_failed = msg_failed

        # Wait for the previous command to finish
        start = time.time()
        while (self.pending_command() or len(self._sequential_write_queue) > 0) and (
                time.time() - start < wait_for_previous):
            time.sleep(0.001)

        self.previous_command = Command.SESSION
        self.write_serial(self.previous_command + b"\r")

        # Wait for other commands to finish like clear_mo_buffer, and read_binary
        start = time.time()
        while (self.pending_command() or len(self._sequential_write_queue) > 0) and (
                time.time() - start < wait_time):
            time.sleep(0.001)

        # Replace the signal callbacks with their original methods
        self.set_option("auto_read", old_read)
        self.signal.message_received = old_message_received
        self.signal.message_receive_failed = old_message_receive_failed

        # Return the collected values or raise an IridiumError
        if len(values) == 0:
            raise IridiumError("The command timed out or completed without returning a proper value!")

        # Unpack the last value
        return values[-1]
    # end acquire_message

    def initiate_session(self):
        """Initiate an SBD session extended (Check and read binary data)."""
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False

        self.previous_command = Command.SESSION
        self.write_serial(self.previous_command + b'\r')
    # end _initiate_session
    
    def queue_session(self):
        """Queue the session message."""
        self.queue_command(Command.SESSION)

    def read_binary_message(self):
        """Request and process a binary message."""
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False

        self.previous_command = Command.READ_BINARY
        self.write_serial(self.previous_command + b'\r')
    # end _process_message

    def queue_read_binary_message(self):
        """Queue the read binary message."""
        self.queue_command(Command.READ_BINARY)

    def send_message(self, message):
        """Send a message. Requires testing!"""
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False

        if len(message) > 340:
            raise IridiumError("Message length must be less than 341 bytes.")

        if isinstance(message, str):
            message = message.encode("utf-8")

        self._write_queue.append(message)
        self.previous_command = Command.WRITE_BINARY + str(len(message)).encode("utf-8")
        self.write_serial(self.previous_command + b'\r')
    # end send_message

    def queue_send_message(self, message):
        """Queue up a message. Requires testing!"""
        if not self.is_port_connected():
            self.signal.notification("Error", "Serial port not connected", "The port is closed!")
            return False

        if len(message) > 340:
            raise IridiumError("Message length must be no more than 340 bytes.")

        if isinstance(message, str):
            message = message.encode("utf-8")

        self._write_queue.append(message)
        self.queue_command(Command.WRITE_BINARY + str(len(message)).encode("utf-8"))
    # end _queue_message
# end class IridiumCommunicator


def run_serial_log_file(filename, communicator, print_serial=None):
    """Play a log file back through a communicator.
    
    Args:
        filename(str): Name of the log file to read in
        communicator (IridiumCommunicator/str): IridiumCommunicator object or com port name to use to emulate the 
            communications.
        print_serial (function): Function to emulate io for the reading and writing. This should simply be a display 
            function to see the I/O.
    """
    with open(filename, "rb") as file:
        buffer = file.read()

    if isinstance(communicator, str):
        communicator = IridiumCommunicator(communicator)
        Signal.set_to_print(communicator.signal)
        
    if print_serial is None:
        def print_serial(bs):
            """Fake pass through method"""
            pass

    if not communicator.is_connected():
        communicator.silent_connect()

    # Prevent reading and writing
    communicator.read_serial = lambda *args, **kwargs: b''
    communicator.write_serial = lambda *args, **kwargs: None
    communicator.queue_command = lambda *args, **kwargs: None

    # Loop through the data commands
    while len(buffer) > 0:
        at_idx = buffer.find(b'AT')
        if at_idx == -1:
            break

        end_idx = buffer[at_idx:].find(b'\r')
        newline_idx = buffer[at_idx:].find(b'\n')
        if end_idx + 2 < newline_idx:  # Commands send with \r. Commands echo with \r\r\n
            # Valid command
            previous_data = buffer[:at_idx]
            if previous_data != b"":
                communicator.check_io(previous_data)
            cmd = buffer[at_idx: at_idx+end_idx]
            buffer = buffer[at_idx+end_idx+1:]

            # Find the end of the command
            ok_idx = buffer.find(Command.OK)
            if ok_idx == -1:
                break

            # Find the receive data
            data = buffer[:ok_idx+2]
            buffer = buffer[ok_idx+2:]
            if cmd == Command.READ_BINARY:
                while not has_read_binary_data(data) and Command.OK in buffer:
                    ok_idx = buffer.index(Command.OK)
                    data = data + buffer[:ok_idx+2]
                    buffer = buffer[ok_idx+2:]

                # Final check for data (End of data)
                if not has_read_binary_data(data):
                    data = buffer
                    buffer = b''

            # Set the receive buffer to process data
            print_serial(cmd + b'\r')
            print_serial(data)
            communicator._previous_command = cmd
            communicator.check_io(data)

            # Separate commands printed
            print()

        else:
            # Skip
            data = buffer[:at_idx+end_idx]
            if data != b"":
                print_serial(data)
                communicator.check_io(data)
            buffer = buffer[at_idx+end_idx:]

    communicator.close()
# end run_serial_log_file


def run_communicator(port="COM2"):
    iridium_port = IridiumCommunicator(port)

    def message_failed(msg_len, content, checksum, calc_check):
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

#     iridium_port.check_ring()
#     time.sleep(5)

    msg = b""
    while msg.lower() != b"exit":
        try:
            msg = iridium_port.acquire_message()
            print("Message acquired:", msg)
        except IridiumError:
            pass  # SBDIX Session command returned saying there was no message.

    # Stop the `iridium_port.listen_thread` and close the port
    iridium_port.close()
# end run_communicator


if __name__ == "__main__":
    import sys
    import argparse

    # Command Line arguments
    parser = argparse.ArgumentParser(description="Run the iridium client.")
    parser.add_argument('port', type=str, help="COM port to use")
    parser.add_argument('-f', '--filename', type=str, default=None, help='Filename to run a log file.')

    pargs = parser.parse_args(sys.argv[1:])

    # Run the file or client
    if pargs.filename is not None:
        run_serial_log_file(pargs.filename, pargs.port)
    else:
        run_communicator(pargs.port)
