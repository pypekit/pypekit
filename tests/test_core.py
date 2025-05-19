import pytest

from src.pypekit.core import (
    Task,
    Pipeline,
    Repository,
    CachedExecutor,
    Node,
    SOURCE_TYPE,
    SINK_TYPE,
)



# ─────────────────────────── helpers ────────────────────────────
class TaskA(Task):
    @property
    def input_types(self):   return {SOURCE_TYPE}
    @property
    def output_types(self):  return {"a"}
    def run(self, input_=None): return (input_ or "") + "A"

class TaskB(Task):
    @property
    def input_types(self):   return {"a"}
    @property
    def output_types(self):  return {"b"}
    def run(self, input_=None): return input_ + "B"

class TaskC(Task):
    @property
    def input_types(self):   return {"b"}
    @property
    def output_types(self):  return {SINK_TYPE}
    def run(self, input_=None): return input_ + "C"

class CountingTask(Task):
    calls = 0
    @property
    def input_types(self):   return {SOURCE_TYPE}
    @property
    def output_types(self):  return {SINK_TYPE}
    def run(self, input_=None):
        type(self).calls += 1
        return (input_ or 0) + 1


# ───────────────────────────── tests ─────────────────────────────
def test_pipeline_execution():
    pl = Pipeline([TaskA(), TaskB(), TaskC()])
    assert pl.input_types  == {SOURCE_TYPE}
    assert pl.output_types == {SINK_TYPE}
    assert pl.run("") == "ABC"


def test_pipeline_invalid_add():
    pl = Pipeline([TaskA()])
    with pytest.raises(ValueError):
        pl.add_tasks([TaskA()])          # A cannot follow A


def test_node_child_validation():
    parent = Node(TaskA())
    with pytest.raises(ValueError):
        parent.add_child(Node(TaskC()))  # types don’t match


def test_repository_build_and_pipelines():
    repo = Repository({TaskA, TaskB, TaskC})
    repo.build_tree()
    pipes = repo.build_pipelines()
    assert len(pipes) == 1
    assert [t.__class__ for t in pipes[0]] == [TaskA, TaskB, TaskC]


def test_cached_executor_uses_cache():
    pipe = Pipeline([CountingTask()])
    exec_ = CachedExecutor([pipe])

    CountingTask.calls = 0
    exec_.run(0)
    assert CountingTask.calls == 1                       # task executed
    exec_.run(0)
    assert CountingTask.calls == 1                       # result came from cache

    key = "0>CountingTask"
    assert key in exec_.cache
    assert exec_.cache[key]["output"] == 1
