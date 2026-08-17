"""Working memory and the episodic JSONL log."""

from agentic_os.memory import EpisodicLog, WorkingMemory


def test_working_memory_roundtrip():
    memory = WorkingMemory()
    memory.remember("customer", {"id": "cust-001"})
    assert memory.recall("customer") == {"id": "cust-001"}
    assert memory.recall("missing", "fallback") == "fallback"
    assert memory.keys() == ["customer"]
    memory.forget("customer")
    assert memory.recall("customer") is None


def test_working_memory_context_rendering():
    memory = WorkingMemory()
    assert "empty" in memory.as_context()
    memory.remember("note", "site visit booked")
    assert "site visit booked" in memory.as_context()


def test_episodic_log_appends_jsonl(tmp_path):
    log = EpisodicLog(tmp_path / "memory")
    log.append("agent-a", "run_started", {"run_id": "r1", "goal": "g"})
    log.append("agent-a", "run_finished", {"run_id": "r1"})
    log.append("agent-b", "run_started", {"run_id": "r2"})
    events_a = log.read("agent-a")
    assert [event["event"] for event in events_a] == ["run_started", "run_finished"]
    assert events_a[0]["goal"] == "g"
    assert len(log.read("agent-b")) == 1
    assert log.read("agent-unknown") == []


def test_runtime_writes_episodic_events(runtime):
    from agentic_os.runtime.planner import PlannedStep, ScriptedPlanner

    steps = [
        PlannedStep(
            capability="lookup_customer",
            purpose="service_delivery",
            params={"name": "Harbour Bakery"},
        )
    ]
    runtime.run("dispatch-agent", "check a customer", ScriptedPlanner(steps))
    events = runtime.episodic.read("dispatch-agent")
    assert [event["event"] for event in events] == [
        "run_started",
        "invocation_allowed",
        "run_finished",
    ]
