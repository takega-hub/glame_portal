import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.hermes_agent_runtime import HermesRunResult
from app.services.hermes_task_execution_service import (
    HermesTaskExecutionService,
    RuntimeMode,
    agent_runtime_mode_from_env,
    agent_runtime_status_from_env,
)


class HermesTaskExecutionServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_runtime_status_reports_effective_mode_without_secrets(self):
        legacy_status = agent_runtime_status_from_env({})
        self.assertEqual(legacy_status["runtime_mode"], "legacy")
        self.assertFalse(legacy_status["hermes_enabled"])
        self.assertFalse(legacy_status["raw_env_present"])

        hermes_status = agent_runtime_status_from_env({"GLAME_AGENT_RUNTIME": "hermes"})
        self.assertEqual(hermes_status["runtime_mode"], "hermes")
        self.assertTrue(hermes_status["hermes_enabled"])
        self.assertTrue(hermes_status["raw_env_present"])
        self.assertNotIn("GLAME_API_TOKEN", hermes_status)

    def test_should_handle_only_when_flag_enabled_and_task_supported(self):
        service = HermesTaskExecutionService(runtime_mode=RuntimeMode.HERMES)

        self.assertTrue(service.should_handle(SimpleNamespace(target_agent="crm-agent")))
        self.assertTrue(service.should_handle(SimpleNamespace(target_agent="traffic-growth-agent")))
        self.assertFalse(HermesTaskExecutionService(runtime_mode=RuntimeMode.LEGACY).should_handle(
            SimpleNamespace(target_agent="crm-agent")
        ))

    def test_build_payload_preserves_task_passport_without_pii_expansion(self):
        task = SimpleNamespace(
            id="task-1",
            source_agent="director-agent",
            target_agent="crm-agent",
            task_type="birthday_message",
            task_context={"approval_required": True},
            input_data={"segment": "VIP"},
            target_metrics={"conversion": "reply"},
            requirements={"tone": "premium"},
            constraints={"no_auto_send": True},
            priority=2,
            status="approved",
            deadline_at=None,
        )

        payload = HermesTaskExecutionService().build_task_payload(task)

        self.assertEqual(payload["id"], "task-1")
        self.assertEqual(payload["target_agent"], "crm-agent")
        self.assertEqual(payload["input_data"], {"segment": "VIP"})
        self.assertEqual(payload["constraints"], {"no_auto_send": True})
        self.assertEqual(payload["status"], "approved")

    async def test_execute_marks_task_completed_and_logs_result_on_success(self):
        task = SimpleNamespace(
            id="task-1",
            source_agent="director-agent",
            target_agent="crm-agent",
            task_type="birthday_message",
            task_context={},
            input_data={},
            target_metrics={},
            requirements={},
            constraints={},
            priority=2,
            status="approved",
            deadline_at=None,
            output_data=None,
            output_metadata=None,
            error_message=None,
            error_details=None,
        )
        prompt = SimpleNamespace(system_prompt="CRM system prompt")
        db = FakeDb(prompt)

        async def fake_run_task(agent_id, system_prompt, task_payload):
            return HermesRunResult(
                success=True,
                profile="glame-crm",
                command=["hermes", "--profile", "glame-crm", "chat", "-q", "..."],
                output="CRM result",
                error="",
                exit_code=0,
            )

        runtime = SimpleNamespace(run_task=fake_run_task)
        service = HermesTaskExecutionService(runtime_mode=RuntimeMode.HERMES, runtime=runtime)

        handled = await service.execute(task, db)

        self.assertTrue(handled)
        self.assertEqual(task.status, "completed")
        self.assertEqual(task.output_data["runtime"], "hermes")
        self.assertEqual(task.output_data["result"], "CRM result")
        self.assertEqual(task.output_metadata["hermes_profile"], "glame-crm")
        self.assertEqual(db.commits, 1)
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.added[0].event_type, "hermes_task_completed")

    async def test_execute_marks_task_failed_when_hermes_returns_error(self):
        task = SimpleNamespace(
            id="task-2",
            source_agent="director-agent",
            target_agent="crm-agent",
            task_type="crm",
            task_context={},
            input_data={},
            target_metrics={},
            requirements={},
            constraints={},
            priority=3,
            status="approved",
            deadline_at=None,
            output_data=None,
            output_metadata=None,
            error_message=None,
            error_details=None,
        )
        db = FakeDb(SimpleNamespace(system_prompt="CRM system prompt"))

        async def fake_run_task(agent_id, system_prompt, task_payload):
            return HermesRunResult(
                success=False,
                profile="glame-crm",
                command=["hermes"],
                output="",
                error="Hermes binary not found",
                exit_code=127,
            )

        service = HermesTaskExecutionService(
            runtime_mode=RuntimeMode.HERMES,
            runtime=SimpleNamespace(run_task=fake_run_task),
        )

        handled = await service.execute(task, db)

        self.assertTrue(handled)
        self.assertEqual(task.status, "failed")
        self.assertEqual(task.error_message, "Hermes binary not found")
        self.assertEqual(task.error_details["runtime"], "hermes")
        self.assertEqual(db.added[0].event_type, "hermes_task_failed")


class FakeScalarResult:
    def __init__(self, item):
        self.item = item

    def first(self):
        return self.item


class FakeDbResult:
    def __init__(self, item):
        self.item = item

    def scalars(self):
        return FakeScalarResult(self.item)


class FakeDb:
    def __init__(self, prompt):
        self.prompt = prompt
        self.added = []
        self.commits = 0

    async def execute(self, query):
        return FakeDbResult(self.prompt)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commits += 1


if __name__ == "__main__":
    unittest.main()
