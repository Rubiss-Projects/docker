"""Check the security and scheduling failures the image audit must catch."""

from pathlib import Path
import tempfile
import unittest

import yaml

from check_image_pins import audit, dockerfile_images, image_errors

DIGEST = "@sha256:" + "a" * 64


class ImagePinTests(unittest.TestCase):
    def test_requires_both_discoverable_tag_and_immutable_digest(self):
        for image in ["vendor/app:1.2.3", "vendor/app" + DIGEST, "vendor/app:1@sha256:abc"]:
            with self.subTest(image=image):
                self.assertTrue(image_errors(image))
        for tag in ["1.2.3", "pg18", "java25", "latest-full"]:
            self.assertEqual(image_errors("registry:5000/vendor/app:" + tag + DIGEST), [])

    def test_linuxserver_uses_alias_that_matches_stable_version_detection(self):
        for tag in ["version-4.0.19.2979", "4.0.19.2979", "version-3.4.2-r0", "latest"]:
            with self.subTest(tag=tag):
                self.assertTrue(image_errors("lscr.io/linuxserver/sonarr:" + tag + DIGEST))
        self.assertEqual(image_errors("lscr.io/linuxserver/sonarr:4.0.20" + DIGEST), [])

    def test_local_build_stage_is_not_a_registry_dependency(self):
        image = "vendor/base:1" + DIGEST
        self.assertEqual(dockerfile_images(f"FROM --platform=$BUILDPLATFORM {image} AS build\nFROM build AS final\nFROM scratch"), [image])

    def test_compose_job_does_not_cover_dockerfile_and_disabled_jobs_do_not_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".github").mkdir()
            (root / "app").mkdir()
            (root / "app/Dockerfile").write_text("FROM vendor/base:1" + DIGEST)
            (root / "app/docker-compose.yml").write_text("services:\n  app:\n    build: .\n")
            update = {"package-ecosystem": "docker-compose", "directory": "/app", "schedule": {"interval": "weekly"}}
            config = root / ".github/dependabot.yml"
            paths = ["app/Dockerfile", "app/docker-compose.yml"]
            config.write_text(yaml.safe_dump({"updates": [update]}))
            self.assertIn("weekly docker Dependabot", audit(root, paths)[0])
            update["package-ecosystem"] = "docker"
            config.write_text(yaml.safe_dump({"updates": [update]}))
            self.assertEqual(audit(root, paths), [])
            for disabled in [{"schedule": {"interval": "monthly"}}, {"open-pull-requests-limit": 0}]:
                config.write_text(yaml.safe_dump({"updates": [update | disabled]}))
                self.assertTrue(audit(root, paths))


if __name__ == "__main__":
    unittest.main()
