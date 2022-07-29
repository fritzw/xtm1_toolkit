import select
from io import BufferedReader, BufferedWriter
from subprocess import Popen
from time import time

from serial import Serial


class StreamLineReader:
    def __init__(self, channel_object):
        if type(channel_object) is Serial:
            self._in_stream: Serial|BufferedReader = channel_object
            self._out_stream: Serial|BufferedWriter = channel_object
            self._in_stream.timeout = 0 # Never do blocking reads
        elif type(channel_object) is Popen:
            self._in_stream = channel_object.stdout
            self._out_stream = channel_object.stdin
            self._in_stream.read = self._in_stream.read1 # Never do blocking reads
        else:
            raise ValueError('Unknown communication channel type ' + str(type(channel_object)))
        self._buffer = bytearray()
    
    def write(self, data: bytes) -> int:
        count = self._out_stream.write(data)
        self._out_stream.flush()
        return count
    
    def readline(self, timeout=None, separator=b'\n') -> bytes: 
        start = time()
        total_timeout = timeout
        while separator not in self._buffer:
            if timeout is not None:
                timeout = total_timeout - (time() - start)
                if timeout < 0:
                    return '' # Timeout, return nothing (not even newline)
            readable, _w, _e = select.select([self._in_stream], [], [], timeout)
            if not readable:
                return '' # Timeout, return nothing (not even newline)
            self._buffer.extend(self._in_stream.read(128))
        # Now we know that we have a separator
        sep_index = self._buffer.index(separator)
        line = bytes(self._buffer[:sep_index+1])
        del self._buffer[:sep_index+1]
        return line
