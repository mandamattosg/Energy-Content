from collections.abc import Callable
import time


def retry_call(
    func: Callable[[], object],
    attempts: int = 3,
    delay_seconds: float = 1.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> object:
    last_error: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            return func()
        except exceptions as error:  # pragma: no cover - retry control flow
            last_error = error
            if attempt < attempts:
                time.sleep(delay_seconds * attempt)

    if last_error is not None:
        raise last_error

    raise RuntimeError("retry_call failed without capturing an exception")
