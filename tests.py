import pytest

from pypekit import Task, Pipeline, Repository, CachedExecutor 


class ConstantTask(Task):
    """A task that ignores its input and returns a constant output."""

    def __init__(self, output, output_types, input_types=None):
        self._output = output
        self._output_types = list(output_types)
        self._input_types = list(input_types or ["source"])

    @property
    def input_types(self):
        return self._input_types

    @property
    def output_types(self):
        return self._output_types

    def run(self, _):
        return self._output


class CountingPassthroughTask(Task):
    """Records how many times it was executed and returns its input unmodified."""

    def __init__(self, input_types, output_types):
        self._input_types = list(input_types)
        self._output_types = list(output_types)
        self.run_count = 0

    @property
    def input_types(self):
        return self._input_types

    @property
    def output_types(self):
        return self._output_types

    def run(self, input_):
        self.run_count += 1
        return input_


# ---------------------------------------------------------------------------
# Task tests
# ---------------------------------------------------------------------------

def test_task_id_property_validation():
    """Non‑string ids should raise ``ValueError``; valid strings must be kept."""
    task = ConstantTask("out", ["raw"], ["source"])

    task.id = "my_task"
    assert task.id == "my_task"

    with pytest.raises(ValueError):
        task.id = 123


# ---------------------------------------------------------------------------
# Pipeline tests
# ---------------------------------------------------------------------------

def _build_simple_pipeline():
    """Utility that returns a ready-to-run 3-stage pipeline and its tasks."""
    t_source = ConstantTask("raw", ["raw"], ["source"])
    t_mid = ConstantTask("processed", ["processed"], ["raw"])
    t_sink = ConstantTask("final", ["sink"], ["processed"])
    pipeline = Pipeline([
        ("source", t_source),
        ("mid", t_mid),
        ("sink", t_sink),
    ])
    return pipeline, (t_source, t_mid, t_sink)


def test_pipeline_input_and_output_types_reflect_endpoints():
    pipeline, _ = _build_simple_pipeline()
    assert pipeline.input_types == ["source"]
    assert pipeline.output_types == ["sink"]


def test_pipeline_run_executes_sequentially_and_returns_last_result():
    pipeline, _ = _build_simple_pipeline()
    assert pipeline.run(None) == "final"


def test_pipeline_duplicate_task_id_is_rejected():
    t1 = ConstantTask("raw", ["raw"], ["source"])
    pipeline = Pipeline([("dup", t1)])

    with pytest.raises(ValueError):
        pipeline.add_tasks([("dup", ConstantTask("other", ["raw"], ["raw"]))])


def test_pipeline_type_incompatibility_is_rejected():
    t1 = ConstantTask("raw", ["raw"], ["source"])
    pipeline = Pipeline([("first", t1)])

    bad_task = ConstantTask("oops", ["bad"], ["unmatched"])
    with pytest.raises(ValueError):
        pipeline.add_tasks([("bad", bad_task)])


def test_pipeline_iterator_preserves_insertion_order():
    pipeline, _ = _build_simple_pipeline()
    ids = [task_id for task_id, _ in pipeline]
    assert ids == ["source", "mid", "sink"]


def test_pipeline_repr_contains_pipeline_id_and_task_ids():
    pipeline, _ = _build_simple_pipeline()
    rep = repr(pipeline)
    assert pipeline.id in rep
    for task_id, _ in pipeline:
        assert task_id in rep


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------

def _build_repository():
    """Create a repository with a simple source→mid→sink chain."""
    return Repository([
        ("loader", ConstantTask("raw", ["raw"], ["source"])),
        ("processor", ConstantTask("processed", ["processed"], ["raw"])),
        ("classifier", ConstantTask("done", ["sink"], ["processed"])),
    ])


def test_repository_builds_non_empty_pipeline_dict():
    repo = _build_repository()
    pipelines = repo.build_pipelines()

    assert isinstance(pipelines, dict)
    assert pipelines, "Expected at least one viable pipeline"

    for pipeline in pipelines.values():
        assert "source" in pipeline.input_types
        assert "sink" in pipeline.output_types


def test_repository_fill_repository_rejects_duplicate_ids():
    repo = _build_repository()
    with pytest.raises(ValueError):
        repo.fill_repository([("loader", ConstantTask("x", ["raw"], ["source"]))])


def test_repository_build_pipelines_requires_source_tasks():
    repo = Repository([("t", ConstantTask("out", ["sink"], ["raw"]))])
    with pytest.raises(ValueError):
        repo.build_pipelines()


def test_repository_repr_lists_tasks_and_pipeline_count():
    repo = _build_repository()
    repo.build_pipelines()
    rep = repr(repo)
    assert "tasks=" in rep and "pipelines=" in rep
    for task_id in ["loader", "processor", "classifier"]:
        assert task_id in rep


# ---------------------------------------------------------------------------
# CachedExecutor tests
# ---------------------------------------------------------------------------

def test_cached_executor_avoids_recomputation_with_identical_input():
    loader = CountingPassthroughTask(["source"], ["raw"])
    processor = CountingPassthroughTask(["raw"], ["sink"])

    repo = Repository([
        ("loader", loader),
        ("processor", processor),
    ])
    pipelines = repo.build_pipelines()

    executor = CachedExecutor(pipelines)

    # First run – tasks should execute once each.
    executor.run(input_="data")
    assert loader.run_count == 1
    assert processor.run_count == 1

    # Second run with identical input – results come from cache, no new runs.
    executor.run(input_="data")
    assert loader.run_count == 1, "Loader should not re-run due to caching"
    assert processor.run_count == 1, "Processor should not re-run due to caching"

    # Results dictionary must contain one entry per pipeline with the expected keys.
    for result in executor.results.values():
        assert set(result) == {"pipeline_id", "output", "tasks", "runtime"}


def test_cached_executor_repr_returns_readable_string():
    repo = _build_repository()
    pipelines = repo.build_pipelines()
    executor = CachedExecutor(pipelines)
    rep = repr(executor)
    assert rep.startswith("CachedExecutor(")
    assert str(len(pipelines)) in rep
