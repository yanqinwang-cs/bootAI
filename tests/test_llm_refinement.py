from pathlib import Path
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from urllib import error

from organizer.llm_refinement import (
    ALLOWED_SUBFOLDERS,
    build_group_refinement_messages,
    build_group_refinement_payload,
    build_refined_organization_suggestion,
    parse_json_object,
    refine_group_with_response,
    refine_project_groups_with_ollama,
    validate_refinement_data,
)
from organizer.models import ProjectGroup
from organizer.ollama_client import OllamaClient
from organizer.scanner import scan_directory


def make_group(root: Path) -> ProjectGroup:
    (root / "evosim_notes.txt").write_text("notes", encoding="utf-8")
    (root / "results" / "evosim_output.csv").parent.mkdir()
    (root / "results" / "evosim_output.csv").write_text("value", encoding="utf-8")
    files_by_path = {file.relative_path.as_posix(): file for file in scan_directory(root)}
    return ProjectGroup(
        group_name="Evosim",
        files=[
            files_by_path["evosim_notes.txt"],
            files_by_path["results/evosim_output.csv"],
        ],
        reason="files share filename token evosim",
        confidence=70,
    )


def valid_response_for(group: ProjectGroup) -> str:
    return json.dumps(
        {
            "folder_name": "EvoSim_Project",
            "confidence": 82,
            "reason": "suggested grouping based on provided paths",
            "subfolders": {
                file.relative_path.as_posix(): "notes"
                for file in group.files
            },
            "warnings": ["review suggested folder name before applying later"],
        }
    )


class PayloadPromptTests(unittest.TestCase):
    def test_payload_contains_compact_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            group = make_group(root)

            payload = build_group_refinement_payload(group)
            payload_json = json.dumps(payload)

            self.assertEqual(payload["group_name"], "Evosim")
            self.assertIn("relative_path", payload["files"][0])
            self.assertIn("name", payload["files"][0])
            self.assertIn("extension", payload["files"][0])
            self.assertIn("deterministic_subfolder", payload["files"][0])
            self.assertNotIn(str(root), payload_json)
            self.assertNotIn("value", payload_json)

    def test_messages_include_schema_and_allowed_subfolders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            group = make_group(root)

            messages = build_group_refinement_messages(group)
            combined = "\n".join(message["content"] for message in messages)

            self.assertIn("Schema:", combined)
            self.assertIn("Allowed subfolders:", combined)
            for subfolder in ALLOWED_SUBFOLDERS:
                self.assertIn(subfolder, combined)
            self.assertLess(len(combined), 3000)


class ParseValidateTests(unittest.TestCase):
    def test_valid_json_response_becomes_refinement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            group = make_group(Path(directory))

            refinement = refine_group_with_response(group, valid_response_for(group))

            self.assertEqual(refinement.original_group_name, "Evosim")
            self.assertEqual(refinement.folder_name, "EvoSim_Project")
            self.assertEqual(refinement.confidence, 82)

    def test_surrounding_whitespace_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            group = make_group(Path(directory))

            refinement = refine_group_with_response(
                group,
                f"  \n{valid_response_for(group)}\n  ",
            )

            self.assertEqual(refinement.folder_name, "EvoSim_Project")

    def test_invalid_json_and_non_object_raise_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_json_object("{invalid")
        with self.assertRaises(ValueError):
            parse_json_object("[]")

    def test_invalid_fields_raise_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            group = make_group(Path(directory))
            base = json.loads(valid_response_for(group))
            invalid_cases = [
                {"folder_name": ""},
                {"folder_name": "../bad"},
                {"confidence": 101},
                {"subfolders": {"invented.txt": "notes"}},
                {"subfolders": {file.relative_path.as_posix(): "bad" for file in group.files}},
                {"reason": "safe to delete later"},
                {"warnings": ["ok", 123]},
            ]

            for override in invalid_cases:
                data = dict(base)
                data.update(override)
                with self.assertRaises(ValueError):
                    validate_refinement_data(data, group)

    def test_missing_file_path_in_subfolders_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            group = make_group(Path(directory))
            data = json.loads(valid_response_for(group))
            first_key = next(iter(data["subfolders"]))
            del data["subfolders"][first_key]

            with self.assertRaises(ValueError):
                validate_refinement_data(data, group)


class RefinedSuggestionTests(unittest.TestCase):
    def test_refinement_does_not_mutate_original_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            group = make_group(Path(directory))
            before = (group.group_name, group.reason, group.confidence, list(group.files))

            refine_group_with_response(group, valid_response_for(group))

            self.assertEqual(before, (group.group_name, group.reason, group.confidence, list(group.files)))

    def test_refined_suggestion_keeps_original_group_and_uses_refinement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            group = make_group(root)
            refinement = refine_group_with_response(group, valid_response_for(group))

            suggestion = build_refined_organization_suggestion(group, refinement, root)
            item = suggestion.plan_items[0]

            self.assertIs(suggestion.group, group)
            self.assertEqual(suggestion.suggested_root, root / "Organized" / "EvoSim_Project")
            self.assertEqual(item.operation, "dry-run move")
            self.assertEqual(item.confidence, 82)
            self.assertTrue(item.reason.startswith("LLM refinement:"))
            self.assertFalse((root / "Organized").exists())

    def test_overwrite_risk_and_collision_handling_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a").mkdir()
            (root / "b").mkdir()
            (root / "a" / "evosim.py").write_text("a", encoding="utf-8")
            (root / "b" / "evosim.py").write_text("b", encoding="utf-8")
            files_by_path = {file.relative_path.as_posix(): file for file in scan_directory(root)}
            group = ProjectGroup(
                group_name="Evosim",
                files=[files_by_path["a/evosim.py"], files_by_path["b/evosim.py"]],
                reason="files share filename token evosim",
                confidence=70,
            )
            data = {
                "folder_name": "EvoSim Project",
                "confidence": 80,
                "reason": "suggested code grouping",
                "subfolders": {"a/evosim.py": "code", "b/evosim.py": "code"},
                "warnings": [],
            }
            destination = root / "Organized" / "EvoSim_Project" / "code" / "evosim.py"
            destination.parent.mkdir(parents=True)
            destination.write_text("existing", encoding="utf-8")
            refinement = validate_refinement_data(data, group)

            suggestion = build_refined_organization_suggestion(group, refinement, root)

            self.assertEqual(
                [item.destination.name for item in suggestion.plan_items],
                ["evosim.py", "b_evosim.py"],
            )
            self.assertTrue(suggestion.plan_items[0].overwrite_risk)


class OllamaClientTests(unittest.TestCase):
    def test_chat_returns_message_content_for_valid_response(self) -> None:
        fake_response = FakeResponse(
            200,
            json.dumps({"message": {"content": "{\"ok\": true}"}}).encode("utf-8"),
        )
        with mock.patch("organizer.ollama_client.request.urlopen", return_value=fake_response) as mocked:
            content = OllamaClient("model").chat([{"role": "user", "content": "hi"}])

        request_object = mocked.call_args.args[0]
        body = json.loads(request_object.data.decode("utf-8"))
        self.assertEqual(content, "{\"ok\": true}")
        self.assertEqual(body["model"], "model")
        self.assertFalse(body["stream"])
        self.assertEqual(body["options"]["temperature"], 0)

    def test_chat_errors_raise_runtime_error(self) -> None:
        client = OllamaClient("model")
        with mock.patch(
            "organizer.ollama_client.request.urlopen",
            side_effect=error.URLError("no server"),
        ):
            with self.assertRaises(RuntimeError):
                client.chat([])
        with mock.patch(
            "organizer.ollama_client.request.urlopen",
            return_value=FakeResponse(500, b"{}"),
        ):
            with self.assertRaises(RuntimeError):
                client.chat([])
        with mock.patch(
            "organizer.ollama_client.request.urlopen",
            return_value=FakeResponse(200, b"not json"),
        ):
            with self.assertRaises(RuntimeError):
                client.chat([])
        with mock.patch(
            "organizer.ollama_client.request.urlopen",
            return_value=FakeResponse(200, b"{}"),
        ):
            with self.assertRaises(RuntimeError):
                client.chat([])


class RefinementOrchestrationTests(unittest.TestCase):
    def test_refine_project_groups_with_fake_client_preserves_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            group = make_group(Path(directory))
            client = FakeClient([valid_response_for(group), valid_response_for(group)])

            refinements = refine_project_groups_with_ollama([group, group], client)

            self.assertEqual([refinement.original_group_name for refinement in refinements], ["Evosim", "Evosim"])
            self.assertEqual(len(client.messages), 2)

    def test_invalid_client_response_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            group = make_group(Path(directory))

            with self.assertRaises(ValueError):
                refine_project_groups_with_ollama([group], FakeClient(["not json"]))


class LLMCliTests(unittest.TestCase):
    def test_refine_groups_without_provider_or_model_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_cli(Path(directory), "--refine-groups")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--llm-provider ollama is required", result.stderr)

    def test_unsupported_provider_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_cli(
                Path(directory),
                "--refine-groups",
                "--llm-provider",
                "openai",
                "--llm-model",
                "model",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--llm-provider ollama is required", result.stderr)

    def test_help_includes_new_flags(self) -> None:
        result = run_cli(Path("."), "--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("--refine-groups", result.stdout)
        self.assertIn("--plan-refined-organization", result.stdout)
        self.assertIn("--llm-provider", result.stdout)

    def test_existing_grouping_cli_paths_still_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evosim_notes.txt").write_text("notes", encoding="utf-8")
            (root / "evosim_report.pdf").write_text("report", encoding="utf-8")

            project_groups = run_cli(root, "--project-groups")
            organization = run_cli(root, "--plan-organization")

            self.assertEqual(project_groups.returncode, 0, project_groups.stderr)
            self.assertEqual(organization.returncode, 0, organization.stderr)


class FakeResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


class FakeClient:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.messages: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]]) -> str:
        self.messages.append(messages)
        return self.responses.pop(0)


def run_cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    return subprocess.run(
        [sys.executable, "-m", "organizer.cli", str(root), *args],
        check=False,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
    )


if __name__ == "__main__":
    unittest.main()
