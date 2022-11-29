from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

from cachetools import LRUCache
from celery import states

CELERY_MISSING_DATA = "undefined"
# name, state, runtime, queue
CollectOutcome = Tuple[Optional[str], Optional[str], Optional[float], Optional[str]]
# name, queue, latency
LatencyOutcome = Tuple[Optional[str], Optional[str], Optional[float]]


def is_task_event(kind: str) -> bool:
    return "task" in kind


class TaskState(Enum):
    PENDING = states.PENDING
    RECEIVED = states.RECEIVED
    STARTED = states.STARTED
    FAILURE = states.FAILURE
    RETRY = states.RETRY
    SUCCESS = states.SUCCESS
    REVOKED = states.REVOKED
    REJECTED = states.REJECTED
    UNDEFINED = "UNDEFINED"

    @classmethod
    def from_event(cls, event_kind: str) -> "TaskState":
        return MAPPING.get(event_kind, TaskState.UNDEFINED)


MAPPING = {
    "sent": TaskState.PENDING,
    "received": TaskState.RECEIVED,
    "started": TaskState.STARTED,
    "failed": TaskState.FAILURE,
    "retried": TaskState.RETRY,
    "succeeded": TaskState.SUCCESS,
    "revoked": TaskState.REVOKED,
    "rejected": TaskState.REJECTED,
}


@dataclass
class Task:
    uuid: str = CELERY_MISSING_DATA
    name: str = CELERY_MISSING_DATA
    local_received: float = 0.0
    runtime: Optional[float] = None
    state: TaskState = TaskState.UNDEFINED

    @classmethod
    def from_event(cls, event: Dict) -> "Task":
        kind: Optional[str] = event.get("type")
        if kind is None:
            raise ValueError("Invalid Event: missing type")
        elif not (isinstance(kind, str)):
            raise TypeError(f"Except type str for kind, found {type(kind)}")

        splitted = kind.split("-")
        state = splitted[1]

        if is_task_event(kind):
            uuid = event.get("uuid", CELERY_MISSING_DATA)
            state = TaskState.from_event(state)
            local_received = event.get("local_received")
            if local_received is None:
                raise ValueError("Invalid Event: missing local_received")
            elif not (isinstance(local_received, float)):
                raise TypeError(
                    f"Expected type float for local_received, found {type(local_received)}"
                )
            local_received = local_received

            name = event.get("name", CELERY_MISSING_DATA)
            runtime = event.get("runtime", cls.runtime)
            return cls(uuid, name, local_received, runtime, state)
        return cls()


class CeleryState:
    def __init__(
        self,
        event_count: int,
        task_count: int,
        queue_by_task: Dict[str, str],
        tasks: LRUCache[str, Task],
    ):
        self.event_count = event_count
        self.task_count = task_count
        self.queue_by_task = queue_by_task
        self.tasks = tasks

    @classmethod
    def new(cls, max_tasks_in_memory: int) -> "CeleryState":
        return cls(
            event_count=0,
            task_count=0,
            queue_by_task=defaultdict(),
            tasks=LRUCache(maxsize=max_tasks_in_memory),
        )

    def event(self, task: Task):
        self.event_count += 1

        if self.tasks.get(task.uuid) is None:
            self.tasks[task.uuid] = task

        if task.state == TaskState.RECEIVED:
            self.task_count += 1

    def collect(self, event: Dict) -> CollectOutcome:
        kind: Optional[str] = event.get("type")
        if kind is None:
            raise ValueError("Invalid Event: missing type")

        if not (is_task_event(kind)):
            return (None, None, None, None)

        task = Task.from_event(event)

        name: str
        queue: str
        if task.state in [TaskState.SUCCESS, TaskState.FAILURE, TaskState.REVOKED]:
            name = self.tasks.pop(task.uuid, task).name
            queue = self.queue_by_task.get(name, CELERY_MISSING_DATA)

            return (
                name,
                task.state.value,
                task.runtime,
                queue,
            )
        else:
            self.event(task)

            task_mut = self.tasks[task.uuid]
            task_mut.state = task.state
            name = task_mut.name
            event_queue = event.get("queue")
            if event_queue is not None:
                self.queue_by_task[name] = event_queue

            queue = self.queue_by_task.get(name, CELERY_MISSING_DATA)
            return (name, task.state.value, None, queue)

    def latency(self, event: Dict) -> LatencyOutcome:
        kind: Optional[str] = event.get("type")
        if kind is None:
            raise ValueError("Invalid Event: missing type")

        if not (is_task_event(kind)):
            return (None, None, None)

        task = Task.from_event(event)
        if task.state == TaskState.STARTED:
            prev_event = self.tasks.get(task.uuid)
            if prev_event is None:
                pass
            elif prev_event.state == TaskState.RECEIVED:
                name: str = prev_event.name
                queue: str = self.queue_by_task.get(name, CELERY_MISSING_DATA)
                latency = task.local_received - prev_event.local_received

                return (name, queue, latency)

        return (None, None, None)
