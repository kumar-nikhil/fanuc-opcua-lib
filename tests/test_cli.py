import pytest

from fanuc_opcua.cli import build_parser, parse_assignment
from fanuc_opcua.errors import FanucError


@pytest.mark.parametrize("text, expected", [
    ("DO[1]=on", ("DO[1]", True)),
    ("DO[1]=0", ("DO[1]", False)),
    ("GO[1]=0x10", ("GO[1]", 16)),
    ("R[5]=3", ("R[5]", 3)),
    ("R[5]=-3.5", ("R[5]", -3.5)),
    ("SR[1]=a=b", ("SR[1]", "a=b")),
    ("PR[1].x=500", ("PR[1].x", 500.0)),
])
def test_parse_assignment(text, expected):
    assert parse_assignment(text, None) == expected


def test_parse_sysvar_types():
    assert parse_assignment("$A.$B=1.5", "real") == ("$A.$B", 1.5)
    assert parse_assignment("$A.$B=true", "bool") == ("$A.$B", True)
    assert parse_assignment("$A.$B=7", None) == ("$A.$B", 7)


@pytest.mark.parametrize("text", ["DO[1]", "PR[1]=1", "POS=1", "DO[1]=maybe"])
def test_parse_assignment_errors(text):
    with pytest.raises((FanucError, ValueError)):
        parse_assignment(text, None)


def test_options_before_or_after_subcommand(monkeypatch):
    monkeypatch.delenv("FANUC_HOST", raising=False)
    p = build_parser()
    a = p.parse_args(["--host", "10.0.0.1", "read", "DO[1]"])
    assert a.host == "10.0.0.1" and not a.json
    a = p.parse_args(["read", "DO[1]", "--json", "--host", "10.0.0.2"])
    assert a.host == "10.0.0.2" and a.json
    assert p.parse_args(["info"]).host == "127.0.0.2"
