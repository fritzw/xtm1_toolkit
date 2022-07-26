import pytest
import os
import sys
current_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(current_dir, '..'))

from gcode import GcodeFramer

@pytest.fixture
def framer():
    return GcodeFramer()

def test_framing_file(framer: GcodeFramer):
    filename = os.path.join(current_dir, 'test-gcode/lasse.gcode')
    gcode = framer.calculate_frame_file(filename)
    assert framer.Xminmax == pytest.approx((175, 212.043))
    assert framer.Yminmax == pytest.approx((155.05, 164.35))