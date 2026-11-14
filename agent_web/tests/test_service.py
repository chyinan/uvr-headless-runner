import json
import tempfile
import unittest
import wave
from pathlib import Path

from agent_web.agent import Agent, LLMError
from agent_web.argv import build_argv
from agent_web.audio_util import probe, trim_to_wav
from agent_web.db import Database
from agent_web.executor import _parse_progress
from agent_web.intent import message_requests_adjustment, message_requests_full
from agent_web.service import ServiceError, TaskService
from agent_web.spec import SpecError, make_spec, output_menu, training_stems


class Settings:
    def __init__(self, root: Path):
        self.repo_root = root
        self.data_dir = root / "data"
        self.inference_python = ["python"]
        self.device = "cpu"
        self.llm_configured = False
        self.llm_base_url = ""
        self.llm_api_key = ""
        self.llm_model = ""


class Catalog:
    def __init__(self):
        self.installed = {("mdx", "UVR-MDX-NET Inst HQ 3"), ("mdx", "UVR-MDX-NET Voc FT")}
        self.known = set(self.installed)

    def is_known(self, arch, name):
        return (arch, name) in self.known

    def is_installed(self, arch, name):
        return (arch, name) in self.installed

    def invalidate(self):
        return None


class Downloads:
    def __init__(self):
        self.requested = []

    def enqueue(self, arch, name, request_key=None):
        self.requested.append((arch, name, request_key))
        return {"id": "dl", "status": "queued", "arch": arch, "model_name": name, "progress": None, "stage": "queued", "error": ""}

    def stop(self):
        return None


class Executor:
    def __init__(self):
        self.started = []
        self.busy_flag = False
        self.leftover = False
        self.last = None
        self.on_exit = None

    def busy(self):
        return self.busy_flag

    def leftover_blocking(self):
        return self.leftover

    def start(self, job, task, argv, cwd, on_progress, on_exit, stop_requested):
        self.busy_flag = True
        self.started.append(job["id"])
        self.last = argv
        self.on_exit = on_exit
        self.job_id = job["id"]

    def finish(self, code=0, outputs=None, tail=""):
        self.busy_flag = False
        self.on_exit(self.job_id, code, outputs or [], tail)

    def cancel(self, job_id):
        self.cancelled = job_id

    def shutdown(self):
        self.busy_flag = False


def wav(path: Path, frames: int = 8000) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * frames)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.settings = Settings(self.root)
        self.db = Database(self.root / "data" / "test.sqlite3")
        self.catalog = Catalog()
        self.downloads = Downloads()
        self.executor = Executor()
        self.service = TaskService(self.settings, self.db, self.catalog, self.executor, self.downloads)
        self.sample = self.root / "in.wav"
        wav(self.sample)
        self.output = self.root / "out.wav"
        wav(self.output, 4000)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def task(self, name="song.wav"):
        target = self.root / name
        wav(target)
        return self.service.create_task(target, name)

    def test_preview_is_single_and_replay_safe(self):
        created = self.task()
        first = self.service.create_preview(created["id"], None, "preview01", "manual", "手动提交试听")
        second = self.service.create_preview(created["id"], None, "preview01", "manual", "手动提交试听")
        self.assertEqual(first["id"], second["id"])
        self.service.tick()
        self.assertEqual(self.executor.started, [first["id"]])
        self.assertIn("--primary-only", self.executor.last)
        self.assertIn("--cpu", self.executor.last)
        self.assertNotIn("--vocals-only", self.executor.last)
        self.service.tick()
        self.assertEqual(len(self.executor.started), 1)
        self.executor.finish(0, [self.output])
        again = self.service.create_preview(created["id"], None, None, "manual", "手动提交试听")
        self.assertEqual(again["id"], first["id"])
        task = self.service.get_task(created["id"])
        self.assertEqual(len(task["variants"]), 1)
        self.assertEqual(task["variants"][0]["label"], "方案 1")

    def test_adjustment_gate_and_batch_size(self):
        created = self.task()
        self.service.add_message(created["id"], "user", "做一版伴奏试听")
        job = self.service.create_preview(created["id"], None, None, "agent", "默认试听")
        self.service.tick()
        self.executor.finish(0, [self.output])
        self.service.add_message(created["id"], "user", "先这样")
        with self.assertRaises(ServiceError):
            self.service.create_preview(
                created["id"],
                {"params": {"overlap": 0.75}},
                None,
                "agent",
                "用户没要求调整",
            )
        self.service.add_message(created["id"], "user", "再干净一点")
        with self.assertRaises(ServiceError):
            self.service.create_preview(
                created["id"],
                {"params": {"batch_size": 4}},
                None,
                "agent",
                "只改了 batch",
            )
        adjusted = self.service.create_preview(
            created["id"],
            {"params": {"overlap": 0.75}},
            None,
            "agent",
            "提高 overlap",
        )
        self.assertNotEqual(adjusted["id"], job["id"])
        task = self.service.get_task(created["id"])
        self.assertEqual(len(task["variants"]), 2)
        self.assertEqual(task["selected_variant_id"], task["variants"][1]["id"])
        self.assertEqual(task["variants"][0]["spec"]["params"]["overlap"], 0.25)

    def test_full_and_batch_do_not_add_previews(self):
        first = self.task("one.wav")
        second = self.task("two.wav")
        with self.assertRaises(ServiceError):
            self.service.run_full(first["id"], None, None, None, "agent", [first["id"]], "整首")
        self.service.add_message(first["id"], "user", "用这个处理整首")
        jobs = self.service.run_full(first["id"], None, [first["id"], second["id"]], "batchkey01", "agent", [first["id"], second["id"]], "批量")
        self.assertEqual(len(jobs), 2)
        self.assertTrue(all(job["kind"] == "full" for job in jobs))
        replay = self.service.run_full(first["id"], None, [first["id"], second["id"]], "batchkey01", "agent", [first["id"], second["id"]], "批量")
        self.assertEqual([job["id"] for job in jobs], [job["id"] for job in replay])
        self.assertEqual(self.service.get_task(second["id"])["variants"][0]["jobs"][0]["kind"], "full")
        self.assertEqual(len(self.service.get_task(first["id"])["variants"][0]["jobs"]), 1)

    def test_select_cancel_retry_and_restart(self):
        created = self.task()
        job = self.service.create_preview(created["id"], None, None, "manual", "试听")
        before = len(self.service.get_task(created["id"])["variants"][0]["jobs"])
        self.service.select_variant(created["id"], job["variant_id"])
        self.assertEqual(len(self.service.get_task(created["id"])["variants"][0]["jobs"]), before)
        self.service.cancel_job(job["id"])
        self.service.tick()
        self.assertEqual(self.executor.started, [])
        retried = self.service.retry_job(job["id"])
        self.service.tick()
        self.assertEqual(self.executor.started, [retried["id"]])
        self.service.recover_after_restart()
        self.assertEqual(self.service.job(retried["id"])["status"], "interrupted")
        paused = self.service.create_preview(created["id"], {"params": {"overlap": 0.5}}, None, "manual", "另一版")
        self.service.recover_after_restart()
        self.executor.busy_flag = False
        self.service.tick()
        self.assertNotIn(paused["id"], self.executor.started)
        self.service.continue_job(paused["id"])
        self.service.tick()
        self.assertIn(paused["id"], self.executor.started)

    def test_failure_keeps_previous_success_and_model_wait(self):
        created = self.task()
        self.service.create_preview(created["id"], None, None, "manual", "试听")
        self.service.tick()
        self.executor.finish(0, [self.output])
        failed = self.service.create_preview(created["id"], {"params": {"overlap": 0.8}}, None, "manual", "调整")
        self.service.tick()
        self.executor.finish(1, [], "CUDA out of memory")
        task = self.service.get_task(created["id"])
        self.assertEqual(task["variants"][0]["jobs"][0]["status"], "succeeded")
        self.assertEqual(task["variants"][1]["jobs"][0]["status"], "failed")
        self.assertIn("GPU", task["variants"][1]["jobs"][0]["error"])
        self.catalog.installed.remove(("mdx", "UVR-MDX-NET Voc FT"))
        waiting = self.service.create_preview(
            created["id"],
            {"arch": "mdx", "model_name": "UVR-MDX-NET Voc FT", "output_target": "vocals", "primary_stem": "vocals"},
            None,
            "manual",
            "换模型",
        )
        started = list(self.executor.started)
        self.service.tick()
        self.assertEqual(self.executor.started, started)
        self.assertEqual(self.service.job(waiting["id"])["stage"], "waiting_model")
        self.catalog.installed.add(("mdx", "UVR-MDX-NET Voc FT"))
        self.service.on_download_finished("mdx", "UVR-MDX-NET Voc FT", True, "ok")
        self.executor.busy_flag = False
        self.service.tick()
        self.assertIn(waiting["id"], self.executor.started)
        self.assertEqual(self.service.job(failed["id"])["status"], "failed")

    def test_agent_submits_one_preview_and_llm_failure_is_isolated(self):
        created = self.task()
        self.service.add_message(created["id"], "user", "做一版 30 秒伴奏试听")

        def complete(_settings, _messages, _tools):
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {
                            "name": "create_preview",
                            "arguments": json.dumps(
                                {
                                    "arch": "mdx",
                                    "model_name": "UVR-MDX-NET Inst HQ 3",
                                    "output_target": "instrumental",
                                    "params": {"overlap": 0.25},
                                    "start_sec": 0,
                                    "end_sec": 1,
                                    "reason": "默认伴奏",
                                }
                            ),
                        },
                    }
                ],
            }

        agent = Agent(self.service, self.settings, self.catalog, complete=complete)
        agent.run(created["id"], [created["id"]])
        task = self.service.get_task(created["id"])
        self.assertEqual(len(task["variants"]), 1)
        self.assertIn("已提交试听", self.service.list_messages(created["id"])[-1]["content"])

        def broken(_settings, _messages, _tools):
            raise LLMError("接口超时")

        self.service.add_message(created["id"], "user", "再看看")
        Agent(self.service, self.settings, self.catalog, complete=broken).run(created["id"], [created["id"]])
        self.assertEqual(len(self.service.get_task(created["id"])["variants"]), 1)
        self.assertIn("接口超时", self.service.list_messages(created["id"])[-1]["content"])


class PureTests(unittest.TestCase):
    def test_intent(self):
        self.assertFalse(message_requests_full("先选方案 1"))
        self.assertTrue(message_requests_full("用方案 1 处理整首"))
        self.assertTrue(message_requests_adjustment("人声还有残留，换一版"))
        self.assertFalse(message_requests_adjustment("先听 30 秒"))

    def test_argv_uses_real_primary_stem(self):
        root = Path(".")
        instrumental = make_spec(
            "mdx",
            "UVR-MDX-NET Inst HQ 3",
            "instrumental",
            {"overlap": 0.25, "segment_size": 256, "batch_size": 1, "wav_type": "PCM_24"},
            "instrumental",
        )
        argv = build_argv(["python"], root, instrumental, "cpu", Path("in.wav"), Path("out"))
        self.assertIn("--primary-only", argv)
        vocals = make_spec("mdx", "UVR-MDX-NET Inst HQ 3", "vocals", instrumental["params"], "instrumental")
        argv = build_argv(["python"], root, vocals, "gpu", Path("in.wav"), Path("out"))
        self.assertIn("--secondary-only", argv)
        self.assertIn("--gpu", argv)
        demucs = make_spec("demucs", "htdemucs", "vocals", {"shifts": 2, "overlap": 0.25, "wav_type": "PCM_24"})
        argv = build_argv(["python"], root, demucs, "cpu", Path("in.wav"), Path("out"))
        self.assertIn("--stem", argv)
        self.assertIn("Vocals", argv)
        with self.assertRaises(SpecError):
            make_spec("demucs", "htdemucs", "instrumental", demucs["params"])
        six = make_spec("demucs", "htdemucs_6s", "guitar", demucs["params"])
        argv = build_argv(["python"], root, six, "cpu", Path("in.wav"), Path("out"))
        self.assertIn("Guitar", argv)
        pair = make_spec("demucs", "UVR_Model_1", "instrumental", demucs["params"])
        self.assertEqual(pair["output_target"], "instrumental")
        four = make_spec("mdx", "MDX23C-4-stems", "drums", instrumental["params"])
        argv = build_argv(["python"], root, four, "cpu", Path("in.wav"), Path("out"))
        self.assertIn("--stem", argv)
        self.assertIn("Drums", argv)
        with self.assertRaises(SpecError):
            make_spec("mdx", "UVR-MDX-NET Inst HQ 3", "instrumental", {"overlap": 0.1})

    def test_output_menu_follows_model(self):
        self.assertEqual(
            output_menu("demucs", "htdemucs_6s"),
            ["all", "vocals", "other", "bass", "drums", "guitar", "piano"],
        )
        self.assertEqual(output_menu("demucs", "htdemucs")[0], "all")
        self.assertNotIn("guitar", output_menu("demucs", "htdemucs"))
        target, stems = training_stems(Path("models/MDX_Net_Models/model_data/mdx_c_configs/modelB.yaml"))
        self.assertIsNone(target)
        self.assertEqual(output_menu("mdx", "modelB", stems, target)[:5], ["all", "vocals", "drums", "bass", "other"])
        target, stems = training_stems(Path("models/MDX_Net_Models/model_data/mdx_c_configs/model3.yaml"))
        self.assertEqual(output_menu("mdx", "model3", stems, target), ["vocals"])
        self.assertEqual(output_menu("mdx", "UVR-MDX-NET Inst HQ 3"), ["instrumental", "vocals", "all"])
        self.assertEqual(output_menu("demucs", "UVR Model"), ["vocals", "instrumental", "all"])

    def test_trim_and_progress_parser(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "in.wav"
            target = Path(folder) / "clip.wav"
            wav(source, 8000)
            trim_to_wav(source, target, 0.25, 0.75)
            meta = probe(target)
            self.assertGreater(meta["duration_sec"], 0.4)
            self.assertLess(meta["duration_sec"], 0.6)
        stage, progress = _parse_progress("Running inference 40%")
        self.assertEqual(stage, "inference")
        self.assertEqual(progress, 40.0)
        self.assertEqual(_parse_progress("Loading model")[1], None)


if __name__ == "__main__":
    unittest.main()
