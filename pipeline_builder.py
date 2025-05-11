import uuid
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple


class Task(ABC):
    input_category: Optional[str] = None
    output_category: Optional[str] = None

    @abstractmethod
    def run(self, input_path: Optional[str] = None, output_dir: Optional[str] = None) -> str:
        """
        Execute the task using input data and write to the output directory.
        :param input_path: Path to input data.
        :param output_dir: Directory to store output.
        :return: Path to output data.
        """
        pass


class Pipeline:
    def __init__(self, pipeline_id: str, tasks: List[Task], task_names: List[str]):
        self.id = pipeline_id
        self.tasks = tasks
        self.task_names = task_names

    def run(self, input_path: Optional[str] = None, output_dir: Optional[str] = None) -> str:
        """
        Executes the pipeline by running each task sequentially.
        """
        for task in self.tasks:
            input_path = task.run(input_path, output_dir)
        return input_path

    def __repr__(self):
        return f"Pipeline(id={self.id}, tasks={self.task_names})"


class Repository:
    def __init__(self, task_list: Optional[List[Tuple[str, Task]]] = None):
        self.task_dict: Dict[str, Task] = {}
        self.pipeline_list: List[Pipeline] = []
        if task_list:
            self.fill_repository(task_list)

    def fill_repository(self, task_list: List[Tuple[str, Task]]):
        for task_name, task in task_list:
            self._add_task(task_name, task)

    def _add_task(self, task_name: str, task: Task):
        if task_name in self.task_dict:
            raise ValueError(f"Task '{task_name}' already exists in repository.")
        self.task_dict[task_name] = task

    def build_pipelines(self) -> List[Pipeline]:
        root_tasks = self._get_root_tasks()
        for task_name, task in root_tasks:
            self._build_recursive([task_name], task.output_category)
        if not self.pipeline_list:
            raise ValueError("No viable pipelines found. Check task input and output categories.")
        return self.pipeline_list

    def _get_root_tasks(self) -> List[Tuple[str, Task]]:
        roots = [(name, task) for name, task in self.task_dict.items() if task.input_category is None]
        if not roots:
            raise ValueError("No root tasks found (tasks with no input category).")
        return roots

    def _build_recursive(self, current_chain: List[str], next_category: Optional[str]):
        if next_category is None:
            self._create_pipeline(current_chain)
            return

        available_tasks = set(self.task_dict) - set(current_chain)
        next_tasks = [
            (name, task)
            for name, task in self.task_dict.items()
            if name in available_tasks and task.input_category == next_category
        ]

        if not next_tasks:
            self._create_pipeline(current_chain)
            return

        for name, task in next_tasks:
            self._build_recursive(current_chain + [name], task.output_category)

    def _create_pipeline(self, task_names: List[str]):
        pipeline_id = str(uuid.uuid4())
        tasks = [self.task_dict[name] for name in task_names]
        self.pipeline_list.append(Pipeline(pipeline_id, tasks, task_names))


class CachedExecutor:
    def __init__(self, cache_dir: str, pipelines: List[Pipeline]):
        self.cache_dir = cache_dir
        self.cache: Dict[str, str] = {}
        self.pipelines = pipelines
        self.results: List[Dict] = []

    def run(self):
        for pipeline in self.pipelines:
            output_path = self._run_pipeline(pipeline)
            self.results.append({
                "pipeline_id": pipeline.id,
                "output_path": output_path,
                "tasks": pipeline.task_names
            })
            print(f"Pipeline {pipeline.id} completed.")

    def _run_pipeline(self, pipeline: Pipeline, input_path: Optional[str] = None) -> str:
        """
        Runs a pipeline with caching: if a task chain has already been run, it reuses the output.
        """
        task_signature = ""
        for task, name in zip(pipeline.tasks, pipeline.task_names):
            task_signature += f"_{name}"
            if task_signature in self.cache:
                input_path = self.cache[task_signature]
            else:
                input_path = task.run(input_path, self.cache_dir)
                self.cache[task_signature] = input_path
        return input_path
