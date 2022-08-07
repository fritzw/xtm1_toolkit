from socket import AF_INET, SOCK_STREAM, socketpair
from threading import Thread
import pytest
import os
import sys
import time
try:
    import pty
except ImportError:
    pty = None


current_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(current_dir, '..'))
from StreamLineReader import StreamLineReader

def send(endpoint, data: bytes):
    if hasattr(endpoint, 'write'):
        count = endpoint.write(data)
    elif hasattr(endpoint, 'send'):
        count = endpoint.send(data)
    elif type(endpoint) is int:
        count = os.write(endpoint, data)
    else:
        raise ValueError()
    if hasattr(endpoint, 'flush'):
        endpoint.flush()
    return count

def create_endpoints():
    endpoints = []
    endpoints.append(socketpair())
    #endpoints.append(os.pipe())
    if pty:
        endpoints.append(pty.openpty())
        import termios
        attr = termios.tcgetattr(endpoints[-1][1])
        print(attr, file=sys.stderr)
        attr[1] &= ~termios.OCRNL # disable \n => \r\n translation on pty
        termios.tcsetattr(endpoints[-1][1], termios.TCSANOW, attr)

        attr = termios.tcgetattr(endpoints[-1][0])
        print(attr)
        attr[1] &= ~termios.OCRNL # disable \n => \r\n translation on pty
        termios.tcsetattr(endpoints[-1][0], termios.TCSANOW, attr)
    return endpoints

def close_endpoints(read_port, write_port):
    if hasattr(read_port, 'close'): read_port.close()
    if hasattr(write_port, 'close'): write_port.close()
    if type(read_port) is int: os.close(read_port)
    if type(write_port) is int: os.close(write_port)

@pytest.mark.parametrize('two_endpoints', create_endpoints())
def test_readline(two_endpoints):
    read_port, write_port = two_endpoints
    reader = StreamLineReader(read_port)

    start = time.time()
    data = reader.readline(timeout=0.1)
    elapsed = time.time() - start
    assert elapsed >= 0.1
    assert data == b''

    send(write_port, b'no-newline')
    start = time.time()
    data = reader.readline(timeout=0.1)
    elapsed = time.time() - start
    assert elapsed >= 0.1
    assert data == b''

    send(write_port, b'-more\ntest')
    start = time.time()
    data = reader.readline(timeout=0.1)
    elapsed = time.time() - start
    assert elapsed < 0.1 # readline should return instantly if data is available
    assert data == b'no-newline-more\n'

    start = time.time()
    data = reader.readline(timeout=0.1)
    elapsed = time.time() - start
    assert elapsed >= 0.1 # readline should return instantly if data is available
    assert data == b''

    assert reader.read(100) == b'test' # remove remaining data before moving on

    def send_two_parts():
        send(write_port, b'part1')
        time.sleep(0.1)
        send(write_port, b'-part2\npart3')
        
    sender_thread = Thread(group=None, target=send_two_parts)
    start = time.time()
    sender_thread.run()
    data = reader.readline(timeout=1)
    elapsed = time.time() - start
    assert 0.1 < elapsed < 1 # readline should return instantly if data is available
    assert data == b'part1-part2\n'

    close_endpoints(read_port, write_port)
