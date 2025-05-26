import sys
import time
import traceback
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional, Tuple, Type

from .utils import _stable_hash

SOURCE_TYPE = "source"
SINK_TYPE = "sink"


class Task(ABC):

    run_config: Optional[Dict[str, Any]] = None
    input_types: List[str] = []
    output_types: List[str] = []

    @abstractmethod
    def run(self, input_: Optional[Any] = None) -> Any:
        """
        Execute the task.
        :param input_: Input for the task.
        :return: Output of the task.
        """
        pass


class Root(Task):
    input_types = []
    output_types = [SOURCE_TYPE]

    def run(self, input_: Optional[Any] = None) -> Any:
        return input_


class Node:
    def __init__(self, task: Task, parent: Optional["Node"] = None):
        self.task = task
        self.parent = parent
        self.children: List["Node"] = []

    def add_child(self, child: "Node") -> None:
        """
        Adds a child node to the current node.
        :param child: Child node to be added.
        """
        if not any(
            output_type in child.task.input_types
            for output_type in self.task.output_types
        ):
            raise ValueError(
                f"Child cannot be added to node. Output types of the child task do not match input types of the node task."
            )
        self.children.append(child)


class Pipeline(Task):
    def __init__(self, tasks: Optional[List[Task]] = None, id: Optional[str] = None):
        self.id = id or uuid.uuid4().hex
        self.tasks: List[Task] = []
        if tasks:
            self.add_tasks(tasks)

    def add_tasks(self, tasks: List[Task]) -> None:
        """
        Adds tasks to the pipeline.
        :param tasks: List of tasks to be added.
        """
        for task in tasks:
            self._add_task(task)

    def run(
        self, input_: Optional[Any] = None, run_config: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Executes the pipeline by running each task sequentially.
        :param input_: Input to the first task in the pipeline.
        :param run_config: Run configuration for the tasks.
        :return: Output of the last task in the pipeline.
        """
        for task in self.tasks:
            if run_config:
                task.run_config = run_config
            input_ = task.run(input_)
        return input_

    def _add_task(self, task: Task) -> None:
        if not self.tasks:
            self.tasks.append(task)
            self.input_types = task.input_types
            self.output_types = task.output_types
        elif self._types_fit(task):
            self.tasks.append(task)
            self.output_types = task.output_types
        else:
            raise ValueError(
                f"Task {task.__class__.__name__} cannot be added to the pipeline. Input types do not match the output types of {self.tasks[-1].__class__.__name__}."
            )

    def _types_fit(self, task: Task) -> bool:
        return any(output_type in task.input_types for output_type in self.output_types)

    def __iter__(self) -> Iterator[Task]:
        return iter(self.tasks)

    def __repr__(self) -> str:
        return f"Pipeline(tasks={[task.__class__.__name__ for task in self.tasks]})"


class Repository:
    def __init__(
        self,
        tasks: Optional[List[Type[Task]] | Tuple[Type[Task], Dict[str, Any]]] = None,
    ):
        self.tasks: List[Tuple[Type[Task], Dict[str, Any]]] = []
        self.root: Optional[Node] = None
        self.leaves: List[Node] = []
        self.pipelines: List[Pipeline] = []
        self.tree_string: str = ""
        if tasks:
            self._build_repository(tasks)

    def _build_repository(
        self, tasks: List[Type[Task]] | Tuple[Type[Task], Dict[str, Any]]
    ) -> None:
        self.tasks = []
        for task in tasks:
            if isinstance(task, tuple) and len(task) == 2:
                task_class, task_kwargs = task
                self.tasks.append((task_class, task_kwargs))
            elif isinstance(task, type) and issubclass(task, Task):
                self.tasks.append((task, {}))
            else:
                raise ValueError(
                    "Tasks must be either a Task subclass or a tuple of (Task subclass, Dict[str, Any])."
                )

    def build_tree(self, max_depth: int = sys.getrecursionlimit()) -> Node:
        """
        Builds a tree structure from the tasks in the repository.
        It starts from tasks with input type "source" and recursively builds the tree.
        Branches are then pruned if they do not lead to tasks with output type "sink".
        :param max_depth: Maximum depth of the tree.
        :return: Root node of the tree.
        """
        self.root = Node(Root())
        self._build_tree_recursive(self.root, self.tasks, 0, max_depth)
        self._prune_tree()
        if not self.leaves:
            self.root = None
            raise ValueError("Tree is empty. Check your input_types and output_types.")
        return self.root

    def _build_tree_recursive(
        self,
        node: Node,
        available_tasks: List[Tuple[Type[Task], Dict[str, Any]]],
        depth: int,
        max_depth: int,
    ) -> None:
        if depth > max_depth:
            self.leaves.append(node)
            return
        found_valid_task = False
        for i, (task_class, task_kwargs) in enumerate(available_tasks):
            if self._type_fits(node, task_class):
                found_valid_task = True
                new_node = Node(task_class(**task_kwargs), parent=node)
                node.add_child(new_node)
                new_available_task = available_tasks[:i] + available_tasks[i + 1 :]
                self._build_tree_recursive(
                    new_node, new_available_task, depth + 1, max_depth
                )
        if not found_valid_task:
            self.leaves.append(node)

    def _type_fits(self, node: Node, task: Type[Task]) -> bool:
        return any(
            output_type in task.input_types for output_type in node.task.output_types
        )

    def _prune_tree(self) -> None:
        for node in self.leaves.copy():
            self._prune_tree_recursive(node)

    def _prune_tree_recursive(self, node: Node) -> None:
        if not node.children and node not in self.leaves:
            self.leaves.append(node)
        if not SINK_TYPE in node.task.output_types and not node.children:
            self.leaves.remove(node)
            if node.parent:
                node.parent.children.remove(node)
                self._prune_tree_recursive(node.parent)

    def build_tree_string(self) -> str:
        """
        Creates a string representation of the tree structure.
        """
        if not self.root:
            raise ValueError("Tree has not been built yet.")
        self.tree_string = ""
        self._tree_string_recursive(self.root)
        return self.tree_string

    def _tree_string_recursive(
        self, node: Node, prefix: str = "", is_last: bool = True
    ) -> None:
        connector = "└── " if is_last else "├── "
        self.tree_string += prefix + connector + node.task.__class__.__name__ + "\n"
        continuation = "    " if is_last else "│   "
        child_prefix = prefix + continuation
        total = len(node.children)
        for idx, child in enumerate(node.children):
            self._tree_string_recursive(child, child_prefix, idx == total - 1)

    def build_pipelines(self) -> List[Pipeline]:
        """
        Builds pipelines from the tree structure.
        :return: List of pipelines.
        """
        if not self.root:
            raise ValueError("Tree has not been built yet.")
        self.pipelines = []
        tasks: List[Task] = []
        self._build_pipelines_recursive(self.root, tasks)
        return self.pipelines

    def _build_pipelines_recursive(self, node: Node, tasks: List[Task]) -> None:
        if not node.children:
            self.pipelines.append(Pipeline(tasks[1:] + [node.task]))
            return
        for child in node.children:
            self._build_pipelines_recursive(child, tasks + [node.task])


class CachedExecutor:
    def __init__(
        self,
        pipelines: List[Pipeline],
        cache: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ):
        self.pipelines = pipelines
        self.cache: Dict[str, Any] = cache or {}
        self.verbose = verbose
        self.results: Dict[str, Dict[str, Any]] = {}

    def run(
        self, input_: Optional[Any] = None, run_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Runs all pipelines in the executor, caching task outputs to avoid redundant computations.
        :param input_: Input for the first task in each pipeline.
        :param run_config: Run configuration for the tasks.
        :return: Dictionary of results for each pipeline.
        """
        self.results = {}
        for i, pipeline in enumerate(self.pipelines):
            try:
                output, runtime = self._run_pipeline(pipeline, input_, run_config)
            except Exception:
                if self.verbose:
                    print(f"Error running pipeline {i + 1}/{len(self.pipelines)}.")
                traceback.print_exc()
                self.results[pipeline.id] = {
                    "output": None,
                    "runtime": None,
                    "tasks": [task.__class__.__name__ for task in pipeline],
                }
                continue
            self.results[pipeline.id] = {
                "output": output,
                "runtime": runtime,
                "tasks": [task.__class__.__name__ for task in pipeline],
            }
            if self.verbose:
                print(
                    f"Pipeline {i + 1}/{len(self.pipelines)} completed. Runtime: {runtime:.2f}s."
                )
        return self.results

    def _run_pipeline(
        self,
        pipeline: Pipeline,
        input_: Optional[Any] = None,
        run_config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, float]:
        runtime = 0.0
        task_signature = _stable_hash({"input_": input_, "run_config": run_config})
        for task in pipeline:
            if run_config:
                task.run_config = run_config
            task_signature += f">{task.__class__.__name__}"
            if task_signature in self.cache:
                input_ = self.cache[task_signature]["output"]
                runtime += self.cache[task_signature]["runtime"]
            else:
                start_time = time.perf_counter()
                input_ = task.run(input_)
                end_time = time.perf_counter()
                self.cache[task_signature] = {
                    "output": input_,
                    "runtime": end_time - start_time,
                }
                runtime += end_time - start_time
        return input_, runtime
