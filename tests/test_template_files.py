"""Drop-in template files: overrides and folder-added downloads."""

from pathlib import Path

from helpers import ServerCase


class TemplateFileTests(ServerCase):
    def setUp(self):
        self.learner = self.login_demo()
        status, body, _ = self.learner.get("/api/module/strategy")
        self.assertEqual(status, 200, body)
        self.module = body["module"]
        self.slug = self.module["templates"][0]["slug"]
        self.folder = Path(self.tmpdir) / "templates"
        self.folder.mkdir(exist_ok=True)

    def test_file_overrides_generated_template(self):
        payload = b"%PDF-1.4 bizready test template"
        (self.folder / f"{self.slug}.pdf").write_bytes(payload)

        status, body, _ = self.learner.get("/api/module/strategy")
        self.assertEqual(status, 200, body)
        row = next(t for t in body["module"]["templates"] if t["slug"] == self.slug)
        self.assertEqual(row["source"], "file")
        self.assertEqual(row["format"], "PDF")
        self.assertEqual(row["filename"], f"{self.slug}.pdf")

        status, raw, headers = self.learner.get_raw(f"/api/templates/{self.slug}")
        self.assertEqual(status, 200)
        self.assertEqual(raw, payload)
        self.assertIn("application/pdf", headers.get("Content-Type", ""))
        self.assertIn(f"{self.slug}.pdf", headers.get("Content-Disposition", ""))

    def test_folder_adds_extra_template(self):
        module_folder = self.folder / "strategy"
        module_folder.mkdir()
        (module_folder / "Stock-Count.csv").write_bytes(b"item,count\nflour,4\n")

        status, body, _ = self.learner.get("/api/module/strategy")
        self.assertEqual(status, 200, body)
        extra = next(t for t in body["module"]["templates"] if t["filename"] == "Stock-Count.csv")
        self.assertEqual(extra["title"], "Stock Count")
        self.assertEqual(extra["format"], "CSV")
        self.assertEqual(extra["source"], "file")

        status, raw, headers = self.learner.get_raw(f"/api/templates/{extra['slug']}")
        self.assertEqual(status, 200)
        self.assertEqual(raw, b"item,count\nflour,4\n")
        self.assertIn("text/csv", headers.get("Content-Type", ""))

    def test_unknown_template_is_not_served(self):
        status, raw, _ = self.learner.get_raw("/api/templates/../../server/config")
        self.assertEqual(status, 404)
