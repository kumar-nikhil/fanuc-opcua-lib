import pytest

from fanuc_opcua import codec
from fanuc_opcua.types import Config, Position


def test_real_words_low_word_first():
    # 123.45 = 0x42F6E666 -> low word 0xE666 (-6554), high word 0x42F6 (17142)
    assert codec.float_to_words(123.45) == [-6554, 17142]
    assert codec.words_to_float(-6554, 17142) == 123.45


def test_int32_words():
    # 123456789 = 0x075BCD15 -> 0xCD15 (-13035), 0x075B (1883)
    assert codec.int32_to_words(123456789) == [-13035, 1883]
    assert codec.words_to_int32(-13035, 1883) == 123456789
    assert codec.words_to_int32(*codec.int32_to_words(-5)) == -5


def test_tidy_removes_float32_noise():
    assert codec.words_to_float(*codec.float_to_words(538.1)) == 538.1


def test_to_int16():
    assert codec.to_int16(65535) == -1
    assert codec.to_int16(-1) == -1
    with pytest.raises(ValueError):
        codec.to_int16(65536)


def test_string_round_trip():
    words = codec.str_to_words("Hello", 40)
    assert len(words) == 40
    assert words[0] == ord("H") | ord("e") << 8  # first character in the lower byte
    assert codec.words_to_str(words) == "Hello"


def test_string_too_long():
    codec.str_to_words("x" * 79, 40)
    with pytest.raises(ValueError):
        codec.str_to_words("x" * 80, 40)


def _position_words(cart, cfg, joints, validc=1, validj=1, uf=0, ut=1):
    words = [0] * 50
    for i, v in enumerate(cart):
        words[2 * i:2 * i + 2] = codec.float_to_words(v)
    words[18:25] = cfg
    words[25] = validc
    for i, v in enumerate(joints):
        words[26 + 2 * i:28 + 2 * i] = codec.float_to_words(v)
    words[44], words[45], words[46] = validj, uf, ut
    return words


def test_decode_position():
    words = _position_words([538.1, -148.75, 364.25, -179.5, 0.75, 0.0], [0, 0, 1, 1, 0, 0, 1],
                            [0.0, 0.25, -0.75, 0.0, -90.0, 0.0])
    pos = codec.decode_position(words)
    assert pos.xyzwpr == (538.1, -148.75, 364.25, -179.5, 0.75, 0.0)
    assert pos.config == Config(flip=False, left=False, up=True, front=True, turn6=1)
    assert pos.joints == (0.0, 0.25, -0.75, 0.0, -90.0, 0.0)
    assert (pos.uf, pos.ut, pos.valid_cartesian, pos.valid_joint) == (0, 1, True, True)
    assert str(pos.config) == "N R U T, 0, 0, 1"


def test_decode_uninitialized_position():
    pos = codec.decode_position([0] * 50)
    assert not pos.valid_cartesian and not pos.valid_joint
    assert str(pos) == "<uninitialized position>"


def test_encode_cartesian_round_trip():
    pos = Position.cartesian(500, 0, 400, 180, 0, 0, config=Config(flip=True, turn4=-1))
    words = codec.encode_cartesian(pos)
    assert len(words) == 25
    back = codec.decode_position(words + [1] + [0] * 24)
    assert back.xyzwpr == (500, 0, 400, 180, 0, 0)
    assert back.config == pos.config


def test_encode_joints():
    words = codec.encode_joints(Position.joint(10, 20, -30, 0, -60, 5))
    assert codec.words_to_floats(words) == [10, 20, -30, 0, -60, 5]
