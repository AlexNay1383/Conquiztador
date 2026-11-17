import threading

from django.db import close_old_connections, connection


def run_concurrently(*callables, timeout=30):
    """Run each callable in its own thread and database connection, released together by a barrier.

    Returns one ("ok", value) or ("error", exception) tuple per callable, in order.
    """
    barrier = threading.Barrier(len(callables))
    results = [None] * len(callables)

    def worker(index, func):
        try:
            barrier.wait()
            results[index] = ("ok", func())
        except Exception as error:  # noqa: BLE001 - the caller inspects every outcome
            results[index] = ("error", error)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(index, func)) for index, func in enumerate(callables)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout)
    close_old_connections()
    return results
