import uuid
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple, Sequence, Any


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
    def name(self) -> str:
        """
        Returns the explicit name of the task if set, otherwise the class name. 
        :return: Name of the task.
        """
        return getattr(self, "_name", self.__class__.__name__)

    @name.setter
    def name(self, value: str):
        if not isinstance(value, str):
            raise ValueError("Task name must be a string.")
        self._name = value

    @abstractmethod
    def run(self, input_: Optional[Any] = None) -> Any:
        """
        Execute the task.
        :param input_: Input for the task.
        :return: Output of the task.
        """
        pass

    def __repr__(self):
        return f"Task(name={self.name}, input_types={self.input_types}, output_types={self.output_types})"


class Pipeline(Task):
    def __init__(self, task_tuples: Optional[Sequence[Tuple[str, Task]]] = None, pipeline_id: Optional[str] = None):
        self._task_dict: Dict[str, Task] = {}
        if task_tuples:
            self.add_tasks(task_tuples)
        self._id: str = pipeline_id if pipeline_id else str(uuid.uuid4())

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
        :param task_tuples: Sequence of task names and tasks in the form (name, task).
        """
        for task_name, task in task_tuples:
            self._add_task(task_name, task)

    def run(self, input_: Optional[Any] = None) -> Any:
        """
        Executes the pipeline by running each task sequentially.
        :param input_: Input to the first task in the pipeline.
        :return: Output of the last task in the pipeline.
        """
        for task in self._task_dict.values():
            output = task.run(input_)
            input_ = output
        return output

    def _add_task(self, task_name: str, task: Task):
        if task_name in self._task_dict:
            raise ValueError(
                f"Task '{task_name}' already exists in pipeline.")
        if self._task_dict and not set(self.output_types).intersection(set(task.input_types)):
            raise ValueError(
                f"Task '{task_name}' cannot be added to pipeline. Output types of the previous task do not match input types of the new task.")
        task.name = task_name
        self._task_dict[task_name] = task

    def __iter__(self):
        return iter(self._task_dict.values())

    def __repr__(self):
        return f"Pipeline(id={self._id}, tasks={list(self._task_dict)})"


class Repository:
    def __init__(self, task_tuples: Optional[Sequence[Tuple[str, Task]]] = None):
        self._task_dict: Dict[str, Task] = {}
        self._pipelines: List[Pipeline] = []
        if task_tuples:
            self.fill_repository(task_tuples)

    def fill_repository(self, task_tuples: Sequence[Tuple[str, Task]]):
        """
        Fills the repository with tasks.
        :param task_tuples: Sequence of task names and tasks in the form (name, task).
        """
        for task_name, task in task_tuples:
            self._add_task(task_name, task)

    def build_pipelines(self) -> List[Pipeline]:
        """
        Builds pipelines from the tasks in the repository.
        It starts from tasks with input type "source" and recursively builds the pipeline ending with output type "sink".
        :return: List of pipelines.
        """
        self._pipelines = []
        source_tasks = self._get_source_tasks()
        for task in source_tasks:
            for output_type in task.output_types:
                self._build_recursive([task.name], output_type)
        if not self._pipelines:
            raise ValueError(
                "No viable pipelines found. Check task input and output types.")
        return self._pipelines

    def _add_task(self, task_name: str, task: Task):
        if task_name in self._task_dict:
            raise ValueError(
                f"Task '{task_name}' already exists in repository.")
        task.name = task_name
        self._task_dict[task_name] = task

    def _get_source_tasks(self) -> List[Task]:
        source_tasks = [task for task in self._task_dict.values()
                        if "source" in task.input_types]
        if not source_tasks:
            raise ValueError(
                "No source tasks found (tasks with input type \"source\").")
        return source_tasks

    def _build_recursive(self, current_chain: List[str], next_type: Optional[str]):
        if next_type == "sink":
            self._create_pipeline(current_chain)
            return

        available_tasks = set(self._task_dict) - set(current_chain)
        next_tasks = [
            task
            for task in self._task_dict.values()
            if task.name in available_tasks and next_type in task.input_types
        ]

        for task in next_tasks:
            for output_type in task.output_types:
                self._build_recursive(current_chain + [task.name], output_type)

    def _create_pipeline(self, task_names: List[str]):
        tasks = [(name, self._task_dict[name]) for name in task_names]
        self._pipelines.append(Pipeline(tasks))

    def __repr__(self):
        return f"Repository(tasks={list(self._task_dict)}, pipelines={len(self._pipelines)})"


class CachedExecutor:
    def __init__(self, pipelines: Sequence[Pipeline], verbose: bool = False):
        self._pipelines = pipelines
        self._cache: Dict[str, Any] = {}
        self._verbose = verbose
        self.results: List[Dict] = []

    def run(self, input_: Optional[Any] = None) -> List[Dict]:
        """
        Runs all pipelines in the executor, caching results to avoid redundant computations.
        """
        for pipeline in self._pipelines:
            output = self._run_pipeline(pipeline, input_)
            self.results.append({
                "pipeline_id": pipeline._id,
                "output": output,
                "tasks": list(pipeline._task_dict),
            })
            if self._verbose:
                print(f"Pipeline {pipeline._id} completed.")
        return self.results

    def _run_pipeline(self, pipeline: Pipeline, input_: Optional[Any] = None) -> Any:
        task_signature = ""
        for task in pipeline._task_dict.values():
            task_signature += f">{task.name}"
            if task_signature in self._cache:
                input_ = self._cache[task_signature]
            else:
                output = task.run(input_)
                self._cache[task_signature] = output
                input_ = output
        return output

    def __repr__(self):
        return f"CachedExecutor(pipelines={len(self._pipelines)})"
