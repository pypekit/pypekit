"""pypekit.core
================
Core building blocks for *pypekit*.

* **Task** - the abstract base every processing step inherits from.
* **Pipeline** - a linear chain of tasks.
* **Repository** - a tree builder that discovers all possible pipelines
  from a set of tasks.
* **CachedExecutor** - a convenience wrapper to run many pipelines while
  caching intermediate results.
"""

import sys
import time
import traceback
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional, Tuple, Type

from .hashing import stable_hash

SOURCE_TYPE = "source"
SINK_TYPE = "sink"


class Task(ABC):
    """Abstract base class for every processing step.

    Subclasses must implement :py:meth:`run` and override the
    *class attributes* ``input_types`` and ``output_types`` to describe
    which data types they consume and emit.  These strings are free-form
    but should be consistent across your project so that
    :class:`Repository` can wire tasks together automatically.

    Attributes
    ----------
    run_config : dict or None, class variable
        Configuration passed down from a :class:`Pipeline` or
        :class:`CachedExecutor` at runtime.
    input_types: list[str], class variable
        Declared input type identifiers.
    output_types: list[str], class variable
        Declared output type identifiers.
    id : str
        Randomly generated UUID assigned when the task is inserted into a
        pipeline or repository.
    kwargs : dict
        Keyword arguments used at instantiation time.
    """

    run_config: Optional[Dict[str, Any]] = None
    input_types: List[str] = []
    output_types: List[str] = []
    id: str = ""
    kwargs: Dict[str, Any] = {}

    @abstractmethod
    def run(self, input_: Optional[Any] = None) -> Any:
        """Execute the task.

        Parameters
        ----------
        input_ : Any, optional
            Input object consumed by the task.

        Returns
        -------
        Any
            The task's output.
        """

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.kwargs.items())
        return f"{self.__class__.__name__}({args})"


class Root(Task):
    """A dummy task representing the root of a task tree.
    This task does not perform any operation and simply returns the
    input unchanged. It is used to start the task tree in a
    :class:`Repository`.
    """

    input_types: List[str] = []
    output_types: List[str] = [SOURCE_TYPE]

    def run(self, input_: Optional[Any] = None) -> Any:
        """Return the input unchanged."""

        return input_


class Node:
    """Tree node holding a :class:`Task` instance."""

    def __init__(self, task: Task, parent: Optional["Node"] = None) -> None:
        """
        Parameters
        ----------
        task : Task
            The task wrapped by this node.
        parent : Node or None, optional
            Parent node in the tree (``None`` for the root).
        """

        self.task = task
        self.parent = parent
        self.children: List["Node"] = []

    def add_child(self, child: "Node") -> None:
        """Attach *child* to the current node.

        Parameters
        ----------
        child : Node
            The node to attach.

        Raises
        ------
        ValueError
            If the task types are incompatible - i.e. none of the
            current node's ``output_types`` matches any of the child's
            ``input_types``.
        """

        if not any(
            output_type in child.task.input_types
            for output_type in self.task.output_types
        ):
            raise ValueError(
                f"Child cannot be added. Output types {self.task.output_types} of {self.task} "
                f"do not match input types {child.task.input_types} of {child.task}."
            )
        self.children.append(child)


class Pipeline(Task):
    """A linear sequence of :class:`Task` objects.

    The class itself derives from :class:`Task` so that pipelines can be
    nested if desired.  Its public interface mirrors a single task:
    instantiate it, then call :py:meth:`run`.
    """

    def __init__(self, tasks: Optional[List[Task]] = None):
        """Create a pipeline.

        Parameters
        ----------
        tasks : list[Task] or None, optional
            Tasks that make up the pipeline in order.
        """

        self.id = uuid.uuid4().hex
        self.tasks: List[Task] = []
        if tasks:
            self._build_pipeline(tasks)

    def run(self, input_: Optional[Any] = None) -> Any:
        """Execute all tasks sequentially.

        Parameters
        ----------
        input_ : Any, optional
            The argument passed to the *first* task in the chain.

        Returns
        -------
        Any
            Output of the *last* task.
        """

        for task in self.tasks:
            task.run_config = self.run_config
            input_ = task.run(input_)
        return input_

    def __iter__(self) -> Iterator[Task]:
        return iter(self.tasks)

    def __repr__(self) -> str:
        return f"Pipeline(tasks={self.tasks})"

    def _build_pipeline(self, tasks: List[Task]) -> None:
        self.tasks = []
        for task in tasks:
            self._add_task(task)

    def _add_task(self, task: Task) -> None:
        if not isinstance(task, Task):
            raise TypeError(f"Expected Task instance, got {type(task)}.")
        is_first = not self.tasks
        if not is_first and not self._types_fit(task):
            raise ValueError(
                f"Task {task} cannot be added to the pipeline. "
                f"Output types {self.tasks[-1].output_types} of {self.tasks[-1]} "
                f"do not match input types {task.input_types} of {task}."
            )
        task.id = uuid.uuid4().hex
        self.tasks.append(task)
        if is_first:
            self.input_types = task.input_types
        self.output_types = task.output_types

    def _types_fit(self, task: Task) -> bool:
        return any(
            output_type in task.input_types
            for output_type in self.tasks[-1].output_types
        )


class Repository:
    """Utility class that builds every valid pipeline from a task pool."""

    def __init__(
        self,
        tasks: Optional[
            List[Task | Type[Task] | Tuple[Type[Task], Dict[str, Any]]]
        ] = None,
    ) -> None:
        """
        Create a repository.
        Parameters
        ----------
        tasks : list[Task | Type[Task] | tuple[Type[Task], dict[str, Any]]] or None, optional
            Tasks to include in the repository.  Each task can be either
            an instance of a :class:`Task` subclass, a subclass itself or
            a tuple of (subclass, kwargs) to instantiate it with.
        Raises
        ------
        ValueError
            If the provided tasks are not valid (i.e. not instances of
            :class:`Task`, subclasses or tuples of (subclass, kwargs)).
        TypeError
            If the provided tasks are not of the expected type (i.e. not
            instances of :class:`Task`, subclasses or tuples of
            (subclass, kwargs)).
        """

        self.tasks: List[Task | Type[Task] | Tuple[Type[Task], Dict[str, Any]]] = []
        self.root: Optional[Node] = None
        self.leaves: List[Node] = []
        self.pipelines: List[Pipeline] = []
        self.tree_string: str = ""
        if tasks:
            self._build_repository(tasks)

    def _build_repository(
        self, tasks: List[Task | Type[Task] | Tuple[Type[Task], Dict[str, Any]]]
    ) -> None:
        self.tasks = []
        for task in tasks:
            self._add_task(task)

    def _add_task(
        self, task: Task | Type[Task] | Tuple[Type[Task], Dict[str, Any]]
    ) -> None:
        if (
            isinstance(task, tuple)
            and len(task) == 2
            and issubclass(task[0], Task)
            and isinstance(task[1], dict)
        ):
            task_class, task_kwargs = task
            self.tasks.append((task_class, task_kwargs))
        elif isinstance(task, type) and issubclass(task, Task):
            self.tasks.append(task)
        elif isinstance(task, Task):
            self.tasks.append(task)
        else:
            raise ValueError(
                "Tasks must be either an instance of a Task subclass, a Task "
                "subclass or a tuple of (Task subclass, Dict[str, Any])."
            )

    def build_tree(self, max_depth: int = sys.getrecursionlimit()) -> Node:
        """Generate a tree where paths map to potential pipelines.

        Starting from an implicit :class:`Root` node, the method attaches
        every task whose ``input_types`` match the current node's
        ``output_types``.  Branches that *do not* end in a task with
        ``output_types == [\"sink\"]`` are pruned afterwards.

        Parameters
        ----------
        max_depth : int, default ``sys.getrecursionlimit()``
            Maximum depth of the tree.

        Returns
        -------
        Node
            The tree's root node.

        Raises
        ------
        ValueError
            If no valid leaf (sink) can be found.
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
        available_tasks: List[Task | Type[Task] | Tuple[Type[Task], Dict[str, Any]]],
        depth: int,
        max_depth: int,
    ) -> None:
        if depth > max_depth:
            self.leaves.append(node)
            return
        found_valid_task = False
        for i, task in enumerate(available_tasks):
            if not self._type_fits(node, task):
                continue
            found_valid_task = True
            task_instance = self._instantiate_task(task)
            new_node = Node(task_instance, parent=node)
            node.add_child(new_node)
            new_available_task = available_tasks[:i] + available_tasks[i + 1 :]
            self._build_tree_recursive(
                new_node, new_available_task, depth + 1, max_depth
            )
        if not found_valid_task:
            self.leaves.append(node)

    def _instantiate_task(
        self, task: Task | Type[Task] | Tuple[Type[Task], Dict[str, Any]]
    ) -> Task:
        if isinstance(task, tuple):
            task_class, task_kwargs = task
            task_instance = task_class(**task_kwargs)
        elif isinstance(task, type):
            task_instance = task()
            task_kwargs = {}
        else:
            task_instance = task
            task_kwargs = task.kwargs.copy() if hasattr(task, "kwargs") else {}
        task_instance.kwargs = task_kwargs
        task_instance.id = uuid.uuid4().hex
        return task_instance

    def _type_fits(
        self, node: Node, task: Task | Type[Task] | Tuple[Type[Task], Dict[str, Any]]
    ) -> bool:
        if isinstance(task, tuple):
            return any(
                output_type in task[0].input_types
                for output_type in node.task.output_types
            )
        else:
            return any(
                output_type in task.input_types
                for output_type in node.task.output_types
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
        """Generate a human-readable string representation of the task tree.

        Returns
        -------
        str
            A string representation of the task tree, where each line
            represents a task and its children, indented according to
            their depth in the tree.

        Raises
        ------
        ValueError
            If the tree has not been built yet (i.e. no root node exists).
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
        self.tree_string += prefix + connector + str(node.task) + "\n"
        continuation = "    " if is_last else "│   "
        child_prefix = prefix + continuation
        total = len(node.children)
        for idx, child in enumerate(node.children):
            self._tree_string_recursive(child, child_prefix, idx == total - 1)

    def build_pipelines(self) -> List[Pipeline]:
        """Generate a list of all valid pipelines from the task tree.

        Each pipeline is a linear sequence of tasks starting from the
        root node and ending at a leaf node (sink).

        Returns
        -------
        list[Pipeline]
            A list of pipelines, each represented as a :class:`Pipeline`
            instance containing the tasks in order.

        Raises
        ------
        ValueError
            If the tree has not been built yet (i.e. no root node exists).
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
    """Run many pipelines while memoising intermediate results."""

    def __init__(
        self,
        pipelines: List[Pipeline],
        cache: Optional[Dict[Tuple[str, ...], Any]] = None,
        verbose: bool = False,
    ) -> None:
        """Create an executor.

        Parameters
        ----------
        pipelines : list[Pipeline]
            Pipelines to execute.
        cache : dict or None, optional
            Pre-populated cache mapping *task signatures* to cached
            outputs and runtimes.  If ``None`` (default) an empty dict is
            created.
        verbose : bool, default ``False``
            Emit human-readable progress to *stdout*.
        """

        self.pipelines = pipelines
        self.cache: Dict[Tuple[str, ...], Any] = cache or {}
        self.verbose = verbose
        self.results: Dict[str, Dict[str, Any]] = {}

    def run(
        self, input_: Optional[Any] = None, run_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Execute every pipeline and return a nested results dict.

        Caching is keyed by a *signature* consisting of a stable hash of
        ``input_`` and ``run_config`` followed by the UUIDs of every task
        executed up to that point.  If the signature already exists, the
        cached value is used instead of re-running the task.

        Parameters
        ----------
        input_ : Any, optional
            Input object forwarded to the first task of each pipeline.
        run_config : dict or None, optional
            Extra configuration propagated to *every* task via its
            ``run_config`` attribute.

        Returns
        -------
        dict[str, dict[str, Any]]
            Mapping **pipeline ID → {output, runtime, tasks}** where
            *runtime* is a ``float`` in seconds and *tasks* is a list of
            the string representations of all tasks in the pipeline.
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
                    "tasks": [str(task) for task in pipeline.tasks],
                }
                continue
            self.results[pipeline.id] = {
                "output": output,
                "runtime": runtime,
                "tasks": [str(task) for task in pipeline.tasks],
            }
            if self.verbose:
                print(
                    f"Pipeline {i + 1}/{len(self.pipelines)} completed. "
                    f"Runtime: {runtime:.2f}s."
                )
        return self.results

    def _run_pipeline(
        self,
        pipeline: Pipeline,
        input_: Optional[Any] = None,
        run_config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, float]:
        runtime = 0.0
        task_signature: Tuple[str, ...] = (
            stable_hash(
                {"input_": input_, "run_config": run_config}, verbose=self.verbose
            ),
        )
        for task in pipeline:
            task.run_config = run_config
            task_signature = (*task_signature, task.id)
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
