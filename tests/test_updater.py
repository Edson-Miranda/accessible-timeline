import io
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from src.core.updater import (
    parse_version_tuple,
    get_application_directory,
    download_update_archive,
    extract_update_archive,
    apply_update_and_restart,
)
import zipfile


class TestUpdater(unittest.TestCase):
    def test_parse_version_tuple(self):
        self.assertEqual(parse_version_tuple("0.1.0"), (0, 1, 0))
        self.assertEqual(parse_version_tuple("v0.2.0"), (0, 2, 0))
        self.assertEqual(parse_version_tuple("v1.0.0-dev.1"), (1, 0, 0))
        self.assertTrue(parse_version_tuple("v0.2.1") > parse_version_tuple("0.2.0"))
        self.assertTrue(parse_version_tuple("0.2.1A") > parse_version_tuple("0.2.0"))
        self.assertTrue(parse_version_tuple("0.2.1B") > parse_version_tuple("0.2.1A"))
        self.assertTrue(parse_version_tuple("0.3.0") > parse_version_tuple("0.2.9"))
        self.assertFalse(parse_version_tuple("0.2.0") > parse_version_tuple("0.2.0"))

    def test_get_application_directory(self):
        app_dir = get_application_directory()
        self.assertTrue(os.path.isdir(app_dir))
        self.assertTrue(os.path.exists(os.path.join(app_dir, "src")))

    def test_download_update_archive_success(self):
        fake_content = b"PK\x03\x04fake_zip_content"
        mock_response = MagicMock()
        mock_response.headers = {"content-length": str(len(fake_content))}
        mock_response.read.side_effect = [fake_content, b""]
        mock_response.__enter__.return_value = mock_response

        progress_calls = []

        def callback(downloaded, total):
            progress_calls.append((downloaded, total))
            return True

        with tempfile.TemporaryDirectory() as tmp_dir:
            target_file = os.path.join(tmp_dir, "update.zip")
            with patch("urllib.request.urlopen", return_value=mock_response):
                success = download_update_archive(
                    "https://example.com/update.zip",
                    target_file,
                    progress_callback=callback
                )
                self.assertTrue(success)
                self.assertTrue(os.path.exists(target_file))
                with open(target_file, "rb") as f:
                    self.assertEqual(f.read(), fake_content)
                self.assertGreater(len(progress_calls), 0)
                self.assertEqual(progress_calls[-1], (len(fake_content), len(fake_content)))

    def test_download_update_archive_cancellation(self):
        fake_content = b"PK\x03\x04chunk1"
        mock_response = MagicMock()
        mock_response.headers = {"content-length": "1000"}
        mock_response.read.side_effect = [fake_content, b"chunk2"]
        mock_response.__enter__.return_value = mock_response

        # Callback cancela imediatamente
        def callback(downloaded, total):
            return False

        with tempfile.TemporaryDirectory() as tmp_dir:
            target_file = os.path.join(tmp_dir, "update_cancelled.zip")
            with patch("urllib.request.urlopen", return_value=mock_response):
                success = download_update_archive(
                    "https://example.com/update.zip",
                    target_file,
                    progress_callback=callback
                )
                self.assertFalse(success)
                self.assertFalse(os.path.exists(target_file))
                self.assertFalse(os.path.exists(target_file + ".part"))

    def test_extract_update_archive_success(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = os.path.join(tmp_dir, "test.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("AccessibleTimeline.exe", b"fake_binary")
                zf.writestr("sub/nested.txt", b"nested_data")

            extract_dest = os.path.join(tmp_dir, "extracted")
            progress_calls = []

            def _cb(cur, tot):
                progress_calls.append((cur, tot))
                return True

            res_path = extract_update_archive(zip_path, extract_dest, progress_callback=_cb)
            self.assertIsNotNone(res_path)
            self.assertTrue(os.path.exists(os.path.join(extract_dest, "AccessibleTimeline.exe")))
            self.assertTrue(os.path.exists(os.path.join(extract_dest, "sub", "nested.txt")))
            self.assertGreater(len(progress_calls), 0)

    def test_extract_update_archive_single_root_folder(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = os.path.join(tmp_dir, "test_root.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("AccessibleTimeline-v0.4.0/AccessibleTimeline.exe", b"binary")

            extract_dest = os.path.join(tmp_dir, "extracted")
            res_path = extract_update_archive(zip_path, extract_dest)
            self.assertEqual(res_path, os.path.join(extract_dest, "AccessibleTimeline-v0.4.0"))
            self.assertTrue(os.path.exists(os.path.join(res_path, "AccessibleTimeline.exe")))

    def test_extract_update_archive_cancellation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = os.path.join(tmp_dir, "test_cancel.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("file1.txt", b"data")
                zf.writestr("file2.txt", b"data2")

            extract_dest = os.path.join(tmp_dir, "extracted")
            res_path = extract_update_archive(zip_path, extract_dest, progress_callback=lambda c, t: False)
            self.assertIsNone(res_path)

    def test_apply_update_and_restart_generates_batch_script(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_dir = os.path.join(tmp_dir, "extracted_source")
            os.makedirs(source_dir, exist_ok=True)
            with open(os.path.join(source_dir, "AccessibleTimeline.exe"), "wb") as f:
                f.write(b"EXE")

            target_dir = os.path.join(tmp_dir, "app_dir")
            os.makedirs(target_dir, exist_ok=True)

            with patch("subprocess.Popen") as mock_popen:
                success = apply_update_and_restart(source_dir, target_dir, current_pid=12345)
                self.assertTrue(success)
                self.assertTrue(mock_popen.called)

                # Verifica se o script .bat foi gerado no tempdir
                expected_script = os.path.join(tempfile.gettempdir(), "update_at_12345.bat")
                self.assertTrue(os.path.exists(expected_script))
                with open(expected_script, "r", encoding="utf-8") as f:
                    content = f.read()
                    self.assertIn("12345", content)
                    self.assertIn(source_dir, content)
                    self.assertIn(target_dir, content)
                    self.assertIn("AccessibleTimeline.exe", content)
                    self.assertIn("robocopy", content)

                # Limpa o arquivo temporário gerado no teste
                try:
                    os.remove(expected_script)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()

