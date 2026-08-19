import pytest

from documenter import run


def test_takes_the_first_port_nothing_else_is_using(monkeypatch):
    monkeypatch.setattr(run, "_taken", lambda port: port in (8000, 8001))
    assert run._first_free_port() == 8002


def test_refuses_to_start_when_every_port_is_taken(monkeypatch):
    monkeypatch.setattr(run, "_taken", lambda port: True)
    with pytest.raises(SystemExit):
        run._first_free_port()
