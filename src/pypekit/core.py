import time
import sys
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple, Any, Type, Set

from .utils import _stable_hash


SOURCE_TYPE = "source"
SINK_TYPE = "sink"


class Task(ABC):

    @property
    @abstractmethod
    def input_types(self) -> Set[str]:
        """
        Returns the input types of the task.
        :return: Set of input types.
        """
        pass

    @property
    @abstractmethod
    def output_types(self) -> Set[str]:
        """
        Returns the output types of the task.
        :return: Set of output types.
        """
        pass

    @abstractmethod
    def run(self, input_: Optional[Any] = None) -> Any:
        """
        Execute the task.
        :param input_: Input for the task.
        :return: Output of the task.
        """
        pass


class Root(Task):
    @property
    def input_types(self) -> Set[str]:
        return set()

    @property
    def output_types(self) -> Set[str]:
        return {SOURCE_TYPE}

    def run(self, input_: Optional[Any] = None) -> Any:
        return input_


class Node():
    def __init__(self, task: Task, parent: Optional['Node'] = None):
        self.task = task
        self.parent = parent
        self.children: List['Node'] = []

    def add_child(self, child: 'Node'):
        if not any(output_type in child.task.input_types for output_type in self.task.output_types):
            raise ValueError(
                f"Child cannot be added to node. Output types of the child task do not match input types of the node task.")
        self.children.append(child)


class Pipeline(Task):
    def __init__(self, tasks: Optional[List[Task]] = None):
        self.tasks: List[Task] = []
        if tasks:
            self.add_tasks(tasks)

    @property
    def input_types(self) -> Set[str]:
        """
        Returns the input types of the first task in the pipeline.
        :return: Set of input types.
        """
        if not self.tasks:
            return set()
        return self.tasks[0].input_types

    @property
    def output_types(self) -> Set[str]:
        """
        Returns the output types of the last task in the pipeline.
        :return: Set of output types.
        """
        if not self.tasks:
            return set()
        return self.tasks[-1].output_types

    def add_tasks(self, tasks: List[Task]):
        """
        Adds tasks to the pipeline.
        :param tasks: List of tasks to be added.
        """
        for task in tasks:
            self._add_task(task)

    def run(self, input_: Optional[Any] = None) -> Any:
        """
        Executes the pipeline by running each task sequentially.
        :param input_: Input to the first task in the pipeline.
        :return: Output of the last task in the pipeline.
        """
        for task in self.tasks:
            input_ = task.run(input_)
        return input_

    def _add_task(self, task: Task):
        if task.input_types.intersection(self.output_types) or not self.tasks:
            self.tasks.append(task)
        else:
            raise ValueError(
                f"Task {task.__class__.__name__} cannot be added to the pipeline. Input types do not match the output types of {self.tasks[-1].__class__.__name__}.")

    def __iter__(self):
        return iter(self.tasks)

    def __repr__(self):
        return f"Pipeline(tasks={[task.__class__.__name__ for task in self.tasks]})"
    

class Repository:
    def __init__(self, task_classes: Optional[Set[Type[Task]]] = None):
        self.root: Optional[Node] = None
        self.leaves: List[Node] = []
        self.task_classes: Set[Type[Task]] = task_classes or set()
        self.pipelines: List[Pipeline] = []
        self.tree_string: str = ""

    def build_tree(self, max_depth: int = sys.maxsize) -> Node:
        """
        Builds a tree structure from the tasks in the repository.
        It starts from tasks with input type "source" and recursively builds the tree.
        Branches are then pruned if they do not lead to tasks with output type "sink".
        :return: Root node of the tree.
        """
        self.root = Node(Root())
        self._build_tree_recursive(self.root, set(), 0, max_depth)
        self._prune_tree()
        return self.root

    def _build_tree_recursive(self, node: Node, visited_nodes: Set[Type[Task]], depth: int, max_depth: int):
        if depth > max_depth:
            self.leaves.append(node)
            return
        available_task_classes = self.task_classes - visited_nodes
        next_task_classes = [task_class for task_class in available_task_classes if node.task.output_types.intersection(task_class().input_types)]
        if not next_task_classes:
            self.leaves.append(node)
        for task_class in next_task_classes:
            new_node = Node(task_class(), parent=node)
            node.add_child(new_node)
            self._build_tree_recursive(
                new_node, visited_nodes | {task_class}, depth + 1, max_depth)

    def _prune_tree(self):
        for node in self.leaves.copy():
            self._prune_tree_recursive(node)

    def _prune_tree_recursive(self, node: Node):
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

    def _tree_string_recursive(self, node: Node, prefix: str = "", is_last: bool = True):
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
    
    def _build_pipelines_recursive(self, node: Node, tasks: List[Task]):
        if not node.children:
            self.pipelines.append(Pipeline(tasks[1:] + [node.task]))
            return
        for child in node.children:
            self._build_pipelines_recursive(child, tasks + [node.task])


class CachedExecutor:
    def __init__(self, pipelines: List[Pipeline], cache: Optional[Dict[str, Any]] = None, verbose: bool = False):
        self.pipelines = pipelines
        self.verbose = verbose
        self.cache: Dict[str, Any] = cache or {}
        self.results: List[Dict] = []

    def run(self, input_: Optional[Any] = None) -> List[Dict]:
        """
        Runs all pipelines in the executor, caching results to avoid redundant computations.
        """
        self.results = []
        for i, pipeline in enumerate(self.pipelines):
            try:
                output, runtime = self._run_pipeline(pipeline, input_)
            except Exception as e:
                print(f"Error in pipeline {i + 1}: {e}")
                self.results.append({
                    "output": None,
                    "runtime": None,
                    "tasks": [task.__class__.__name__ for task in pipeline],
                })
                continue
            self.results.append({
                "output": output,
                "runtime": runtime,
                "tasks": [task.__class__.__name__ for task in pipeline],
            })
            if self.verbose: 
                print(f"Pipeline {i + 1}/{len(self.pipelines)} completed. Runtime: {runtime:.2f}s.")
        return self.results

    def _run_pipeline(self, pipeline: Pipeline, input_: Optional[Any] = None) -> Tuple[Any, float]:
        runtime = 0.0
        task_signature = _stable_hash(input_)
        for task in pipeline:
            task_signature += f">{task.__class__.__name__}"
            if task_signature in self.cache:
                input_ = self.cache[task_signature]["output"]
                runtime += self.cache[task_signature]['runtime']
            else:
                start_time = time.perf_counter ()
                input_ = task.run(input_)
                end_time = time.perf_counter ()
                self.cache[task_signature] = {
                    "output": input_, "runtime": end_time - start_time}
                runtime += end_time - start_time
        return input_, runtime
