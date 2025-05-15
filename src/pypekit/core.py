import uuid
import time
import sys
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple, Sequence, Any
from collections import OrderedDict

from .utils import _stable_hash


SOURCE_TYPE = "source"
SINK_TYPE = "sink"


class Task(ABC):
    @property
    @abstractmethod
    def input_types(self) -> Sequence[str]:
        """
        Returns the input types of the task.
        :return: Sequence of input types.
        """
        pass

    @property
    @abstractmethod
    def output_types(self) -> Sequence[str]:
        """
        Returns the output types of the task.
        :return: Sequence of output types.
        """
        pass

    @property
    def id(self) -> str:
        return getattr(self, "_id")

    @id.setter
    def id(self, value: str):
        if not isinstance(value, str):
            raise ValueError("Task id must be a string.")
        self._id = value

    @abstractmethod
    def run(self, input_: Optional[Any] = None) -> Any:
        """
        Execute the task.
        :param input_: Input for the task.
        :return: Output of the task.
        """
        pass

    def __repr__(self):
        return f"Task(id={getattr(self, '_id', 'NOT ASSIGNED')}, input_types={self.input_types}, output_types={self.output_types})"


class Pipeline(Task):
    def __init__(self, task_tuples: Optional[Sequence[Tuple[str, Task]]] = None, pipeline_id: Optional[str] = None):
        self._task_dict: OrderedDict[str, Task] = OrderedDict()
        if task_tuples:
            self.add_tasks(task_tuples)
        self.id = pipeline_id if pipeline_id else uuid.uuid4().hex

    @property
    def input_types(self) -> Sequence[str]:
        """
        Returns the input types of the first task in the pipeline.
        :return: List of input types.
        """
        if not self._task_dict:
            return ()
        return list(self._task_dict.values())[0].input_types

    @property
    def output_types(self) -> Sequence[str]:
        """
        Returns the output types of the last task in the pipeline.
        :return: List of output types.
        """
        if not self._task_dict:
            return ()
        return list(self._task_dict.values())[-1].output_types

    def add_tasks(self, task_tuples: Sequence[Tuple[str, Task]]):
        """
        Adds tasks to the pipeline.
        :param task_tuples: Sequence of task ids and tasks in the form (id, task).
        """
        for task_id, task in task_tuples:
            self._add_task(task_id, task)

    def run(self, input_: Optional[Any] = None) -> Any:
        """
        Executes the pipeline by running each task sequentially.
        :param input_: Input to the first task in the pipeline.
        :return: Output of the last task in the pipeline.
        """
        for task in self._task_dict.values():
            input_ = task.run(input_)
        return input_

    def _add_task(self, task_id: str, task: Task):
        if task_id in self._task_dict:
            raise ValueError(
                f"Task '{task_id}' already exists in pipeline.")
        if not self._types_compatible(task):
            raise ValueError(
                f"Task '{task_id}' cannot be added to pipeline. Output types of the previous task do not match input types of the new task.")
        task.id = task_id
        self._task_dict[task_id] = task

    def _types_compatible(self, task: Task) -> bool:
        if not self._task_dict:
            return True
        last_task = list(self._task_dict.values())[-1]
        return any(
            output_type in task.input_types for output_type in last_task.output_types
        )

    def __iter__(self):
        return iter(self._task_dict.items())

    def __repr__(self):
        return f"Pipeline(id={self.id}, tasks={list(self._task_dict)})"


class Repository:
    def __init__(self, task_tuples: Optional[Sequence[Tuple[str, Task]]] = None):
        self._task_dict: Dict[str, Task] = {}
        self._pipeline_dict: Dict[str, Pipeline] = {}
        if task_tuples:
            self.fill_repository(task_tuples)

    def fill_repository(self, task_tuples: Sequence[Tuple[str, Task]]):
        """
        Fills the repository with tasks.
        :param task_tuples: Sequence of task ids and tasks in the form (id, task).
        """
        for task_id, task in task_tuples:
            self._add_task(task_id, task)

    def build_pipelines(self, max_depth: int = sys.maxsize) -> Dict[str, Pipeline]:
        """
        Builds pipelines from the tasks in the repository.
        It starts from tasks with input type "source" and recursively builds the pipeline ending with output type "sink".
        :return: List of pipelines.
        """
        self._pipeline_dict = {}
        source_tasks = self._get_source_tasks()
        for task in source_tasks:
            for output_type in task.output_types:
                self._build_recursive([task.id], output_type, 0, max_depth)
        if not self._pipeline_dict:
            raise ValueError(
                "No viable pipelines found. Check task input and output types.")
        return self._pipeline_dict

    def _add_task(self, task_id: str, task: Task):
        if task_id in self._task_dict:
            raise ValueError(
                f"Task '{task_id}' already exists in repository.")
        task.id = task_id
        self._task_dict[task_id] = task

    def _get_source_tasks(self) -> List[Task]:
        source_tasks = [task for task in self._task_dict.values()
                        if SOURCE_TYPE in task.input_types]
        if not source_tasks:
            raise ValueError(
                "No source tasks found (tasks with input type \"source\").")
        return source_tasks

    def _build_recursive(self, current_chain: List[str], next_type: str, depth: int, max_depth: int):
        if depth > max_depth:
            return
        if next_type == SINK_TYPE:
            self._create_pipeline(current_chain)
            return

        available_tasks = set(self._task_dict) - set(current_chain)
        next_tasks = [
            task
            for task in self._task_dict.values()
            if task.id in available_tasks and next_type in task.input_types
        ]

        for task in next_tasks:
            for output_type in task.output_types:
                self._build_recursive(current_chain + [task.id], output_type, depth + 1, max_depth)

    def _create_pipeline(self, task_ids: List[str]):
        tasks = [(id, self._task_dict[id]) for id in task_ids]
        pipeline = Pipeline(tasks)
        self._pipeline_dict[pipeline.id] = pipeline

    def __repr__(self):
        return f"Repository(tasks={list(self._task_dict)}, pipelines={len(self._pipeline_dict)})"


class CachedExecutor:
    def __init__(self, pipeline_dict: Dict[str, Pipeline], cache: Optional[Dict[str, Any]] = None, verbose: bool = False):
        self._pipeline_dict = pipeline_dict
        self._verbose = verbose
        self.cache: Dict[str, Any] = cache or {}
        self.results: Dict[str, Any] = {}

    def run(self, input_: Optional[Any] = None) -> Dict[str, Any]:
        """
        Runs all pipelines in the executor, caching results to avoid redundant computations.
        """
        self.results = {}
        for i, pipeline in enumerate(self._pipeline_dict.values()):
            output, runtime = self._run_pipeline(pipeline, input_)
            self.results[pipeline.id] = {
                "pipeline_id": pipeline.id,
                "output": output,
                "runtime": runtime,
                "tasks": list(pipeline._task_dict),
            }
            if self._verbose:
                print(f"Ran pipeline {pipeline.id}. Runtime: {runtime:.2f}s. {i + 1}/{len(self._pipeline_dict)} pipelines completed.")
        return self.results

    def _run_pipeline(self, pipeline: Pipeline, input_: Optional[Any] = None) -> Tuple[Any, float]:
        runtime = 0.0
        task_signature = _stable_hash(input_)
        for task in pipeline._task_dict.values():
            task_signature += f">{task.id}"
            if task_signature in self.cache:
                input_ = self.cache[task_signature]["output"]
                runtime += self.cache[task_signature]['runtime']
            else:
                start_time = time.process_time()
                input_ = task.run(input_)
                end_time = time.process_time()
                self.cache[task_signature] = {"output": input_, "runtime": end_time - start_time}
                runtime += end_time - start_time
        return input_, runtime

    def __repr__(self):
        return f"CachedExecutor(pipelines={len(self._pipeline_dict)})"
