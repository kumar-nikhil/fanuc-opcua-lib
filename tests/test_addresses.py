import pytest

from fanuc_opcua.addresses import IO_AREAS, check_count, parse_address
from fanuc_opcua.errors import AddressError


@pytest.mark.parametrize("text, kind, index, group, member", [
    ("DO[1]", "DO", 1, 1, None),
    ("do[10000]", "DO", 10000, 1, None),
    (" R[5] ", "R", 5, 1, None),
    ("PR[3]", "PR", 3, 1, None),
    ("PR[G2:3]", "PR", 3, 2, None),
    ("PR[1].X", "PR", 1, 1, "x"),
    ("PR[1].j6", "PR", 1, 1, "j6"),
    ("POS", "POS", 0, 1, None),
    ("POS[-1]", "POS", -1, 1, None),
    ("POS[G2:0].z", "POS", 0, 2, "z"),
    ("SI[0]", "SI", 0, 1, None),
])
def test_parse(text, kind, index, group, member):
    a = parse_address(text)
    assert (a.kind, a.index, a.group, a.member) == (kind, index, group, member)


def test_var_name():
    assert parse_address("PR[G2:3]").var_name == "PR[G2:3]"
    assert parse_address("PR[3]").var_name == "PR[3]"
    assert parse_address("POS").var_name == "POS[0]"
    assert str(parse_address("pr[1].x")) == "PR[1].x"


def test_sysvar():
    a = parse_address("$MCR.$GENOVERRIDE")
    assert a.kind == "$" and a.var_name == "$MCR.$GENOVERRIDE"


@pytest.mark.parametrize("text", [
    "DO", "DO[0]", "DO[10001]", "SI[1000]", "XX[1]", "R[0]", "DO[1].x", "R[G2:1]",
    "PR[1].q", "POS[62]", "$BAD NAME", "PR[1", "",
])
def test_invalid(text):
    with pytest.raises(AddressError):
        parse_address(text)


def test_array_index_matches_manual():
    # Array index = Modbus address - 1 (manual 55.2.3).
    assert IO_AREAS["DI"].array_index(1) == 0
    assert IO_AREAS["RI"].array_index(1) == 10000
    assert IO_AREAS["UI"].array_index(1) == 20000
    assert IO_AREAS["UO"].array_index(1) == 21000
    assert IO_AREAS["SI"].array_index(0) == 21999
    assert IO_AREAS["SO"].array_index(0) == 22999
    assert IO_AREAS["F"].array_index(1) == 20000
    assert IO_AREAS["GO"].array_index(1) == 1000
    assert IO_AREAS["AO"].array_index(1000) == 3999


def test_check_count():
    check_count(parse_address("DO[9999]"), 2)
    with pytest.raises(AddressError):
        check_count(parse_address("DO[9999]"), 3)
    with pytest.raises(AddressError):
        check_count(parse_address("POS"), 2)
    with pytest.raises(AddressError):
        check_count(parse_address("R[1]"), 0)
