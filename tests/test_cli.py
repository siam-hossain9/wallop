import pytest

from wallop.cli import build_parser, parse_duration, parse_header


def test_parse_duration():
    assert parse_duration("30s") == 30.0
    assert parse_duration("90") == 90.0
    assert parse_duration("2m") == 120.0
    assert parse_duration("500ms") == 0.5
    assert parse_duration("1.5s") == 1.5
    with pytest.raises(Exception):
        parse_duration("soon")


def test_parse_header():
    assert parse_header("Authorization: Bearer x") == ("Authorization", "Bearer x")
    assert parse_header("X-Key:value") == ("X-Key", "value")
    with pytest.raises(Exception):
        parse_header("nocolon")


def test_run_args_parse():
    parser = build_parser()
    args = parser.parse_args(
        ["run", "http://x/", "-c", "100", "-d", "30s", "-H", "A: b", "-H", "C: d"]
    )
    assert args.url == "http://x/"
    assert args.concurrency == 100
    assert args.duration == 30.0
    assert dict(args.header) == {"A": "b", "C": "d"}


def test_demo_args_parse():
    parser = build_parser()
    args = parser.parse_args(["demo", "--port", "9000", "-c", "20"])
    assert args.command == "demo"
    assert args.port == 9000
    assert args.concurrency == 20
