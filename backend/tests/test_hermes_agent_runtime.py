import unittest

from app.services.hermes_agent_runtime import (
    DEFAULT_HERMES_PROFILE_BY_AGENT_ID,
    HermesAgentRuntime,
    HermesRuntimeConfig,
    hermes_runtime_config_from_env,
)


class HermesAgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def test_default_profiles_map_core_glame_agents_to_dedicated_profiles(self):
        self.assertEqual(DEFAULT_HERMES_PROFILE_BY_AGENT_ID["director-agent"], "glame-director")
        self.assertEqual(DEFAULT_HERMES_PROFILE_BY_AGENT_ID["crm-agent"], "glame-crm")
        self.assertEqual(DEFAULT_HERMES_PROFILE_BY_AGENT_ID["brand-media-agent"], "glame-brand-media")
        self.assertEqual(DEFAULT_HERMES_PROFILE_BY_AGENT_ID["analytics-agent"], "glame-analytics")
        self.assertEqual(DEFAULT_HERMES_PROFILE_BY_AGENT_ID["assortment-agent"], "glame-assortment")
        self.assertEqual(DEFAULT_HERMES_PROFILE_BY_AGENT_ID["stylist-agent"], "glame-stylist")

    def test_resolves_legacy_aliases_to_canonical_hermes_profiles(self):
        runtime = HermesAgentRuntime(HermesRuntimeConfig(default_profile="glame-agent-worker"))

        self.assertEqual(runtime.profile_for_agent("content-agent"), "glame-brand-media")
        self.assertEqual(runtime.profile_for_agent("communication-agent"), "glame-crm")
        self.assertEqual(runtime.profile_for_agent("unknown-agent"), "glame-agent-worker")

    def test_builds_non_shell_hermes_cli_command_for_profile(self):
        runtime = HermesAgentRuntime(HermesRuntimeConfig(binary="/usr/local/bin/hermes"))

        command = runtime.build_command("crm-agent", "Сформируй CRM ответ")

        self.assertEqual(command[:5], [
            "/usr/local/bin/hermes",
            "--profile",
            "glame-crm",
            "chat",
            "--quiet",
        ])
        self.assertEqual(command[-1], "Сформируй CRM ответ")

    def test_builds_no_glame_write_smoke_check_command(self):
        runtime = HermesAgentRuntime(HermesRuntimeConfig(binary="/usr/local/bin/hermes"))

        command = runtime.build_smoke_check_command("director-agent")

        self.assertEqual(command[:5], [
            "/usr/local/bin/hermes",
            "--profile",
            "glame-director",
            "chat",
            "--quiet",
        ])
        self.assertIn("Do not call GLAME API", command[-1])
        self.assertIn("Do not modify files", command[-1])

    def test_config_from_env_allows_safe_runtime_overrides(self):
        env = {
            "GLAME_HERMES_BINARY": "/opt/hermes/bin/hermes",
            "GLAME_HERMES_DEFAULT_PROFILE": "glame-agent-worker-dev",
            "GLAME_HERMES_TIMEOUT_SECONDS": "42",
            "GLAME_HERMES_PROFILE_CRM_AGENT": "glame-crm-dev",
        }

        config = hermes_runtime_config_from_env(env)
        runtime = HermesAgentRuntime(config)

        self.assertEqual(config.binary, "/opt/hermes/bin/hermes")
        self.assertEqual(config.default_profile, "glame-agent-worker-dev")
        self.assertEqual(config.timeout_seconds, 42)
        self.assertEqual(runtime.profile_for_agent("crm-agent"), "glame-crm-dev")

    async def test_readiness_check_reports_binary_and_profile_statuses_without_task_execution(self):
        calls = []

        async def fake_executor(command, timeout_seconds):
            calls.append((command, timeout_seconds))
            if command == ["/opt/hermes", "--version"]:
                return {"exit_code": 0, "stdout": "hermes 1.2.3", "stderr": ""}
            if command == ["/opt/hermes", "profile", "list"]:
                return {"exit_code": 0, "stdout": "glame-crm\nglame-brand-media\n", "stderr": ""}
            raise AssertionError(f"unexpected command: {command}")

        runtime = HermesAgentRuntime(
            HermesRuntimeConfig(
                binary="/opt/hermes",
                profile_by_agent_id={"crm-agent": "glame-crm", "brand-media-agent": "glame-brand-media"},
            ),
            executor=fake_executor,
        )

        readiness = await runtime.check_readiness(["crm-agent", "brand-media-agent", "analytics-agent"])

        self.assertTrue(readiness["binary"]["available"])
        self.assertEqual(readiness["binary"]["version"], "hermes 1.2.3")
        self.assertTrue(readiness["profiles"]["crm-agent"]["exists"])
        self.assertTrue(readiness["profiles"]["brand-media-agent"]["exists"])
        self.assertFalse(readiness["profiles"]["analytics-agent"]["exists"])
        self.assertEqual(readiness["profiles"]["analytics-agent"]["profile"], "glame-analytics")
        self.assertEqual([call[0] for call in calls], [["/opt/hermes", "--version"], ["/opt/hermes", "profile", "list"]])

    async def test_smoke_check_runs_no_glame_write_prompt(self):
        calls = []

        async def fake_executor(command, timeout_seconds):
            calls.append((command, timeout_seconds))
            return {"exit_code": 0, "stdout": '{"status":"ok"}', "stderr": ""}

        runtime = HermesAgentRuntime(
            HermesRuntimeConfig(binary="/opt/hermes", timeout_seconds=77),
            executor=fake_executor,
        )

        result = await runtime.run_smoke_check("director-agent")

        self.assertTrue(result["success"])
        self.assertEqual(result["profile"], "glame-director")
        self.assertEqual(result["command_preview"], ["/opt/hermes", "--profile", "glame-director", "chat", "--quiet"])
        self.assertIn("Do not call GLAME API", calls[0][0][-1])
        self.assertEqual(calls[0][1], 77)

    async def test_run_task_sends_structured_prompt_to_injected_executor(self):
        calls = []

        async def fake_executor(command, timeout_seconds):
            calls.append((command, timeout_seconds))
            return {"exit_code": 0, "stdout": "готовый результат", "stderr": ""}

        runtime = HermesAgentRuntime(
            HermesRuntimeConfig(binary="hermes", timeout_seconds=123),
            executor=fake_executor,
        )

        result = await runtime.run_task(
            agent_id="crm-agent",
            system_prompt="Ты CRM агент GLAME.",
            task_payload={"task_type": "birthday_message", "input_data": {"segment": "VIP"}},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.profile, "glame-crm")
        self.assertEqual(result.output, "готовый результат")
        self.assertEqual(calls[0][1], 123)
        prompt = calls[0][0][-1]
        self.assertIn("Ты CRM агент GLAME.", prompt)
        self.assertIn('"task_type": "birthday_message"', prompt)
        self.assertIn('"segment": "VIP"', prompt)
        self.assertIn("Верни проверяемый результат", prompt)


if __name__ == "__main__":
    unittest.main()
