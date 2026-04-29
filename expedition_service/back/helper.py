from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Protocol

from fastapi import FastAPI


class LifeSpanInterface(Protocol):
    async def _ainit_(self):
        ...

    async def _adel_(self):
        ...


class LifeSpanHandler:
    def __init__(self):
        self.span_objects: list[LifeSpanInterface] = []
        self.extra_async_objects: list[Any] = []

    def add_span_object(self, span_object: LifeSpanInterface):
        self.span_objects.append(span_object)

    def add_extra_async_object(self, extra_async_object: Any):
        self.extra_async_objects.append(extra_async_object)

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        async with AsyncExitStack() as stack:
            for span_object in self.span_objects:
                await span_object._ainit_()
            for async_obj in self.extra_async_objects:
                await stack.enter_async_context(async_obj(app))
            yield
        for span_object in self.span_objects:
            await span_object._adel_()
