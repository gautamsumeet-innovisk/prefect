# Licensed under LICENSE.md; also available at https://www.prefect.io/licenses/alpha-eula

import logging
import sys

if sys.version_info < (3, 5):
    raise ImportError(
        """The DaskExecutor is only locally compatible with Python 3.5+"""
    )

import datetime
from contextlib import contextmanager
from distributed import Client, fire_and_forget, Future, Queue, worker_client
from typing import Any, Callable, Iterable, Iterator, List

import queue
import warnings

from prefect import config
from prefect.engine.executors.base import Executor
from prefect.utilities.executors import dict_to_list


class DaskExecutor(Executor):
    """
    An executor that runs all functions using the `dask.distributed` scheduler on
    a (possibly local) dask cluster.  If you already have one running, simply provide the
    address of the scheduler upon initialization; otherwise, one will be created
    (and subsequently torn down) within the `start()` contextmanager.

    Args:
        - address (string, optional): address of a currently running dask
            scheduler; if one is not provided, a `distributed.LocalCluster()` will be created in `executor.start()`.
            Defaults to `None`
        - processes (bool, optional): whether to use multiprocessing or not
            (computations will still be multithreaded). Ignored if address is provided.
            Defaults to `False`. Note that timeouts are not supported if `processes=True`
        - debug (bool, optional): whether to operate in debug mode; `debug=True`
            will produce many additional dask logs. Defaults to the `debug` value in your Prefect configuration
        - **kwargs (dict, optional): additional kwargs to be passed to the
            `dask.distributed.Client` upon initialization (e.g., `n_workers`)
    """

    def __init__(
        self,
        address: str = None,
        processes: bool = False,
        debug: bool = config.debug,
        **kwargs: Any
    ) -> None:
        self.address = address
        self.processes = processes
        self.debug = debug
        self.is_started = False
        self.kwargs = kwargs
        super().__init__()

    @contextmanager
    def start(self) -> Iterator[None]:
        """
        Context manager for initializing execution.

        Creates a `dask.distributed.Client` and yields it.
        """
        try:
            self.kwargs.update(
                silence_logs=logging.CRITICAL if not self.debug else logging.WARNING
            )
            with Client(
                self.address, processes=self.processes, **self.kwargs
            ) as client:
                self.client = client
                self.is_started = True
                yield self.client
        finally:
            self.client = None
            self.is_started = False

    def queue(self, maxsize: int = 0, client: Client = None) -> Queue:
        """
        Creates an executor-compatible Queue object which can share state
        across tasks.

        Args:
            - maxsize (int, optional): `maxsize` for the Queue; defaults to 0
                (interpreted as no size limitation)
            - client (dask.distributed.Client, optional): which client to
                associate the Queue with; defaults to `self.client`
        """
        q = Queue(maxsize=maxsize, client=client or self.client)
        return q

    def map(
        self, fn: Callable, *args: Any, upstream_states: dict = None, **kwargs: Any
    ) -> Future:
        def mapper(
            fn: Callable, *args: Any, upstream_states: dict, **kwargs: Any
        ) -> List[Future]:
            states = dict_to_list(upstream_states)

            with worker_client(separate_thread=False) as client:
                futures = []
                for elem in states:
                    futures.append(
                        client.submit(fn, *args, upstream_states=elem, **kwargs)
                    )
                fire_and_forget(
                    futures
                )  # tells dask we dont expect worker_client to track these
            return futures

        if self.is_started and hasattr(self, "client"):
            future_list = self.client.submit(
                mapper, fn, *args, upstream_states=upstream_states, **kwargs
            )
        elif self.is_started:
            with worker_client(separate_thread=False) as client:
                future_list = client.submit(
                    mapper, fn, *args, upstream_states=upstream_states, **kwargs
                )
        else:
            raise ValueError("Executor must be started")
        return future_list

    def __getstate__(self):
        state = self.__dict__.copy()
        if "client" in state:
            del state["client"]
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

    def submit(self, fn: Callable, *args: Any, **kwargs: Any) -> Future:
        """
        Submit a function to the executor for execution. Returns a Future object.

        Args:
            - fn (Callable): function which is being submitted for execution
            - *args (Any): arguments to be passed to `fn`
            - **kwargs (Any): keyword arguments to be passed to `fn`

        Returns:
            - Future: a Future-like object which represents the computation of `fn(*args, **kwargs)`
        """

        if self.is_started and hasattr(self, "client"):
            return self.client.submit(fn, *args, pure=False, **kwargs)
        elif self.is_started:
            with worker_client(separate_thread=False) as client:
                return client.submit(fn, *args, pure=False, **kwargs)

    def wait(self, futures: Iterable, timeout: datetime.timedelta = None) -> Iterable:
        """
        Resolves the Future objects to their values. Blocks until the computation is complete.

        Args:
            - futures (Iterable): iterable of future-like objects to compute
            - timeout (datetime.timedelta, optional): maximum length of time to allow for
                execution

        Returns:
            - Iterable: an iterable of resolved futures
        """
        num_futures = len(self.client.futures)
        res = self.client.gather(
            self.client.gather(self.client.gather(self.client.gather(futures)))
        )
        return res
