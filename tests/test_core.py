import pytest

import src.pypekit.core as pm
from src.pypekit.core import (
    SINK_TYPE,
    SOURCE_TYPE,
    CachedExecutor,
    Node,
    Pipeline,
    Repository,
    Root,
    Task,
)


class DummySource(Task):
    input_types = [SOURCE_TYPE]
    output_types = ["a"]

    def run(self, input_=None):
        return "data"


class DummyTransform(Task):
    input_types = ["a"]
    output_types = ["b"]

    def run(self, input_):
        return input_ + "_transformed"


class DummySink(Task):
    input_types = ["b"]
    output_types = [SINK_TYPE]

    def run(self, input_):
        return input_ + "_sink"


class FaultyTask(Task):
    input_types = ["a"]
    output_types = ["b"]

    def run(self, input_=None):
        raise RuntimeError("fail")


class ConfigTask(Task):
    input_types = [SOURCE_TYPE]
    output_types = [SOURCE_TYPE]

    def run(self, input_=None):
        return self.run_config.get("x", None)


def test_root_passes_input():
    r = Root()
    assert r.run(5) == 5


def test_node_add_child_valid():
    parent = Node(DummySource())
    child = Node(DummyTransform())
    parent.add_child(child)
    assert child in parent.children


def test_node_add_child_invalid():
    parent = Node(DummyTransform())
    child = Node(DummySource())
    with pytest.raises(ValueError):
        parent.add_child(child)


def test_pipeline_add_and_run():
    # correct chain: Source -> Transform -> Sink
    p = Pipeline(tasks=[DummySource(), DummyTransform(), DummySink()])
    output = p.run(None)
    assert output == "data_transformed_sink"


def test_pipeline_add_task_mismatch():
    p = Pipeline(tasks=[DummySource()])
    with pytest.raises(ValueError):
        p.add_tasks([DummySource()])


def test_pipeline_iter_repr():
    p = Pipeline(tasks=[DummySource(), DummyTransform()])
    assert list(p) == p.tasks
    repr_str = repr(p)
    assert "Pipeline(tasks=" in repr_str
    assert "DummySource" in repr_str and "DummyTransform" in repr_str


def test_repository_build_tree_and_pipelines():
    repo = Repository(tasks=[DummySource, DummyTransform, DummySink])
    root = repo.build_tree()
    # Check tree string contains expected nodes
    ts = repo.build_tree_string()
    assert "Root" in ts and "DummySource" in ts and "DummySink" in ts
    pipelines = repo.build_pipelines()
    assert len(pipelines) == 1
    pipeline = pipelines[0]
    assert [t.__class__.__name__ for t in pipeline] == [
        "DummySource",
        "DummyTransform",
        "DummySink",
    ]


def test_repository_no_sink():
    repo = Repository(tasks=[DummySource])
    with pytest.raises(ValueError):
        repo.build_tree()


def test_repository_invalid_tasks():
    with pytest.raises(ValueError):
        Repository(tasks=[123])


def test_run_config_propagation():
    t = ConfigTask()
    p = Pipeline([t])
    out = p.run(None, run_config={"x": 42})
    assert out == 42
    assert t.run_config == {"x": 42}


def test_cached_executor_runs_and_caches(monkeypatch):
    # Monkey-patch stable_hash to a fixed signature for reproducibility
    monkeypatch.setattr(pm, "_stable_hash", lambda x: "sig")
    dummy1 = DummySource()
    dummy2 = DummyTransform()
    dummy3 = DummySink()
    pipelines = [Pipeline([dummy1, dummy2, dummy3])]
    executor = CachedExecutor(pipelines)
    res1 = executor.run(None)
    pid = pipelines[0].id
    assert pid in res1
    out1 = res1[pid]["output"]
    runtime1 = res1[pid]["runtime"]
    # Run again; should use cache
    res2 = executor.run(None)
    out2 = res2[pid]["output"]
    runtime2 = res2[pid]["runtime"]
    assert out1 == out2
    assert pytest.approx(runtime1, rel=1e-6) == runtime2


def test_cached_executor_error(capsys):
    repo = Repository(tasks=[DummySource, FaultyTask, DummySink])
    root = repo.build_tree()
    pipelines = repo.build_pipelines()
    executor = CachedExecutor(pipelines, verbose=True)
    res = executor.run(None)
    pid = pipelines[0].id
    assert res[pid]["output"] is None
    assert res[pid]["runtime"] is None
    captured = capsys.readouterr().out
    assert "Error running pipeline" in captured
