import asyncio

from fastapi import FastAPI

from app.main import lifespan


def test_startup_attempts_catchup_and_shuts_down_scheduler(monkeypatch) -> None:
    calls: list[str] = []

    class FakeScheduler:
        def start(self) -> None:
            calls.append("scheduler-start")

        def add_job(self, function, **options) -> None:
            calls.append(options["id"])

        def shutdown(self, wait: bool = True) -> None:
            calls.append("scheduler-stop")

    monkeypatch.setattr("app.main.create_scheduler", FakeScheduler)

    async def run_lifespan() -> None:
        async with lifespan(FastAPI()):
            calls.append("serving")

    asyncio.run(run_lifespan())

    assert calls == [
        "scheduler-start",
        "startup-data-catchup",
        "serving",
        "scheduler-stop",
    ]
