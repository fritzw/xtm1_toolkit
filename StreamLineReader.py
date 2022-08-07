import os
import select
from io import BufferedReader, BufferedWriter, UnsupportedOperation
from subprocess import Popen
from socket import socket
from time import time

from serial import Serial
from sympy import O

class FileDescriptor:
    def __init__(self, fd) -> None:
        self.fd = fd

    def write(self, data: bytes) -> int:
        return os.write(self.fd, data)
    
    def read(self, max_bytes: int) -> bytes:
        return os.read(self.fd, max_bytes)
    
    def fileno(self):
        return self.fd


class StreamLineReader:
    """readline() with a timeout for different types of communication channel"""
    def __init__(self, channel_object, write_channel=None):
        self.read_size = 128

        self._in_stream = channel_object

        if type(channel_object) is Serial:
            channel_object.timeout = 0 # Never do blocking reads
            self._in_stream: Serial = channel_object
            self._out_stream: Serial = channel_object
            self._read = self._serial.read
        elif type(channel_object) is Popen:
            self._in_stream: BufferedReader = channel_object.stdout
            self._out_stream: BufferedWriter = channel_object.stdin
            self._read = self._in_stream.read1 # read1 does not block
            self.write = self._out_stream.write
        elif type(channel_object) is socket:
            self._in_stream: socket = channel_object
            self._out_stream: socket = channel_object
            self._read = self._in_stream.recv
            self.write = self._out_stream.send
        elif type(channel_object) is int:
            self._in_stream: FileDescriptor = FileDescriptor(channel_object)
            self._read = self._in_stream.read
            if type(write_channel) is int:
                self._out_stream: FileDescriptor = FileDescriptor(write_channel)
                self.write = self._out_stream.write
            else:
                self._out_stream = None
        else:
            raise ValueError('Unknown communication channel type ' + str(type(channel_object)))
        if hasattr(self._out_stream, 'flush'):
            self.flush = self._out_stream.flush
        self._buffer = bytearray()

    def _read(self, length: int) -> bytes: ...
    def write(self, data: bytes) -> int: ...
    def flush(self): pass # will be overridden if _out_stream has flush()

    def write_flush(self, data: bytes) -> int:
        count = self.write(data)
        self.flush()
        return count

    def read(self, length: int, timeout=None) -> bytes:
        if len(self._buffer) == 0: # wait for new data only if no data is buffered
            readable, _w, _e = select.select([self._in_stream], [], [], timeout)
            if readable:
                self._buffer.extend(self._read(max(self.read_size, length)))
        if len(self._buffer) > 0: # If there is buffered data, return it immediately
            line = self._buffer[:length]
            del self._buffer[:length]
            return line
        return b''

    
    def readline(self, timeout=None, separator=b'\n') -> bytes: 
        start = time()
        total_timeout = timeout
        while separator not in self._buffer:
            if timeout is not None:
                timeout = total_timeout - (time() - start)
                if timeout < 0:
                    return b'' # Timeout, return nothing (not even newline)
            readable, _w, _e = select.select([self._in_stream], [], [], timeout)
            if not readable:
                return b'' # Timeout, return nothing (not even newline)
            self._buffer.extend(self._read(self.read_size))
        # Now we know that we have a separator
        sep_index = self._buffer.index(separator)
        line = bytes(self._buffer[:sep_index+1])
        del self._buffer[:sep_index+1]
        return line.replace(b'\r\n', b'\n') # TTYs on Linux may add carriage returns before newlines. We don't want that
