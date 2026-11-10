import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.phase0_inventory import (
    _collect_linux_graphics_adapters,
    _parse_linux_meminfo,
    _parse_os_release,
    _probe_executable,
    _probe_path_executable,
    collect_inventory,
)


from scripts.phase0_media_poc import map_local_interval_to_source

class ParseLinuxMeminfoTests(unittest.TestCase):
    def test_parses_total_and_available_memory_in_bytes(self):
        result = _parse_linux_meminfo(
            "MemTotal:       16384000 kB\n"
            "MemFree:         1024000 kB\n"
            "MemAvailable:    8192000 kB\n"
        )
        self.assertEqual(result["total_bytes"], 16_777_216_000)
        self.assertEqual(result["available_bytes"], 8_388_608_000)

    def test_missing_available_memory_falls_back_to_memfree(self):
        result = _parse_linux_meminfo("MemTotal: 100 kB\nMemFree: 20 kB\n")
        self.assertEqual(result["total_bytes"], 102_400)
        self.assertEqual(result["available_bytes"], 20_480)

    def test_missing_fields_return_none(self):
        self.assertEqual(
            _parse_linux_meminfo("MemTotal: invalid kB\n"),
            {"total_bytes": None, "available_bytes": None},
        )



class LinuxHostMetadataTests(unittest.TestCase):
    def test_parses_os_release_fields_without_evaluating_shell_content(self):
        result = _parse_os_release(
            'ID=linuxmint\n'
            'NAME="Linux Mint"\n'
            'VERSION_ID="22.1"\n'
            'PRETTY_NAME="Linux Mint 22.1"\n'
            'HOME_URL="$(touch /tmp/should-not-run)"\n'
        )
        self.assertEqual(result["id"], "linuxmint")
        self.assertEqual(result["name"], "Linux Mint")
        self.assertEqual(result["version_id"], "22.1")
        self.assertEqual(result["pretty_name"], "Linux Mint 22.1")
        self.assertEqual(set(result), {"id", "name", "version_id", "pretty_name"})

    def test_detects_amd_display_controller_from_sysfs(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            device = root / "display-amd-1"
            device.mkdir()
            (device / "class").write_text("0x030000", encoding="ascii")
            (device / "vendor").write_text("0x1002", encoding="ascii")
            (device / "device").write_text("0x9999", encoding="ascii")

            network = root / "network-device-2"
            network.mkdir()
            (network / "class").write_text("0x020000", encoding="ascii")
            (network / "vendor").write_text("0x1002", encoding="ascii")
            (network / "device").write_text("0x8888", encoding="ascii")

            result = _collect_linux_graphics_adapters(root)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["vendor"], "AMD")
        self.assertEqual(result[0]["vendor_id"], "0x1002")
        self.assertEqual(result[0]["device_id"], "0x9999")


class ExecutableProbeTests(unittest.TestCase):
    @patch("scripts.phase0_inventory.shutil.which", return_value=None)
    def test_missing_binary_is_reported_without_raising(self, _which):
        result = _probe_executable("ffmpeg", Path("/nonexistent/project"))
        self.assertFalse(result["available"])
        self.assertEqual(result["error"], "not_found")


class JavaScriptRuntimeProbeTests(unittest.TestCase):
    @patch("scripts.phase0_inventory.shutil.which", return_value=None)
    def test_missing_javascript_runtime_is_reported(self, _which):
        result = _probe_path_executable("deno")
        self.assertFalse(result["available"])
        self.assertEqual(result["error"], "not_found")


class MediaTimelineMappingTests(unittest.TestCase):
    def test_maps_local_word_times_to_global_source_timeline(self):
        start, end = map_local_interval_to_source(
            0.25,
            0.80,
            source_offset_seconds=1.25,
            chunk_offset_seconds=12.0,
        )
        self.assertAlmostEqual(start, 13.50)
        self.assertAlmostEqual(end, 14.05)

    def test_rejects_invalid_word_interval(self):
        with self.assertRaises(ValueError):
            map_local_interval_to_source(1.0, 1.0, source_offset_seconds=0.0)

    def test_rejects_non_finite_offsets(self):
        with self.assertRaises(ValueError):
            map_local_interval_to_source(
                0.0, 0.2, source_offset_seconds=float("nan")
            )


class InventoryTests(unittest.TestCase):
    @patch("scripts.phase0_inventory._collect_memory")
    @patch("scripts.phase0_inventory.shutil.disk_usage")
    @patch("scripts.phase0_inventory._package_versions", return_value={})
    @patch("scripts.phase0_inventory._probe_executable")
    @patch("scripts.phase0_inventory.shutil.which", return_value=None)
    def test_inventory_has_stable_top_level_sections(
        self, _which, _probe_executable, _packages, disk_usage, memory
    ):
        class DiskUsage:
            total = 1000
            used = 400
            free = 600

        disk_usage.return_value = DiskUsage()
        memory.return_value = {"total_bytes": 800, "available_bytes": 300}
        result = collect_inventory(Path("."), probe_torch=False)
        self.assertEqual(result["schema_version"], 1)
        self.assertIn("runtime", result)
        self.assertIn("system", result)
        self.assertIn("media_tools", result)
        self.assertIn("packages", result)
        self.assertEqual(result["torch_runtime"]["status"], "not_probed")
        self.assertNotIn("hostname", result["system"])


if __name__ == "__main__":
    unittest.main()
