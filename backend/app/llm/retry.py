import asyncio
import functools


def with_retries(times: int = 2, delay: float = 1.0):
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(times + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt < times:
                        await asyncio.sleep(delay * (attempt + 1))
            raise last_exc

        return wrapper

    return decorator
