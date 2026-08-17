"""The command line, end to end and offline."""

import json

from agentic_os.cli import main


def run_cli(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_demo_runs_offline(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out, _ = run_cli(capsys, "demo")
    assert code == 0
    assert "ontology grounding" in out
    assert "belongs_to" in out
    assert "[DENIED]" in out
    assert "no-spend-after-denial" in out
    runs = list((tmp_path / "runs").glob("*.json"))
    assert len(runs) == 1
    trace = json.loads(runs[0].read_text(encoding="utf-8"))
    assert trace["summary"]["steps_denied"] == 2


def test_trace_command_renders_stored_run(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out, _ = run_cli(capsys, "demo")
    assert code == 0
    run_id = list((tmp_path / "runs").glob("*.json"))[0].stem
    code, out, _ = run_cli(capsys, "trace", run_id, "--verbose")
    assert code == 0
    assert "check policy: FAIL" in out


def test_trace_unknown_run_fails_cleanly(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, _, err = run_cli(capsys, "trace", "no-such-run")
    assert code == 1
    assert "no trace" in err


def test_capabilities_list(capsys):
    code, out, _ = run_cli(capsys, "capabilities", "list")
    assert code == 0
    for name in (
        "lookup_customer",
        "list_open_work_orders",
        "schedule_technician",
        "draft_invoice",
        "send_notification",
    ):
        assert name in out
    assert "spend" in out


def test_grants_show(capsys):
    code, out, _ = run_cli(capsys, "grants", "show", "dispatch-agent")
    assert code == 0
    assert "max risk tier: spend" in out
    assert "5 act/day" in out


def test_grants_show_unknown_principal(capsys):
    code, _, err = run_cli(capsys, "grants", "show", "rogue")
    assert code == 1
    assert "unknown principal" in err


def test_agents_list(capsys):
    code, out, _ = run_cli(capsys, "agents", "list")
    assert code == 0
    assert "dispatcher" in out
    assert "billing-clerk" in out


def test_agents_validate_valid_and_invalid(tmp_path, capsys):
    from agentic_os.agents.loader import packaged_definition_paths

    dispatcher = next(p for p in packaged_definition_paths() if p.stem == "dispatcher")
    code, out, _ = run_cli(capsys, "agents", "validate", str(dispatcher))
    assert code == 0
    assert "valid" in out

    bad = tmp_path / "bad.yaml"
    bad.write_text(
        dispatcher.read_text(encoding="utf-8").replace("risk_ceiling: act", "risk_ceiling: read"),
        encoding="utf-8",
    )
    code, out, _ = run_cli(capsys, "agents", "validate", str(bad))
    assert code == 1
    assert "above the declared risk ceiling" in out


def test_run_defined_agent(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out, _ = run_cli(capsys, "run", "--agent", "dispatcher")
    assert code == 0
    assert "4 allowed, 0 denied" in out


def test_run_unknown_agent(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, _, err = run_cli(capsys, "run", "--agent", "phantom")
    assert code == 1
    assert "no agent definition" in err


def test_run_without_goal_or_agent(capsys):
    code, _, err = run_cli(capsys, "run")
    assert code == 1
    assert "--goal" in err


def test_run_llm_mode_fails_cleanly_without_keys(capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    code, _, err = run_cli(capsys, "run", "--goal", "invoice everything")
    assert code == 1
    assert "no API key" in err
