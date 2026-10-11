#!/usr/bin/env python3
"""Require immutable image pins and weekly Dependabot coverage for tracked manifests."""

from pathlib import Path
import re
import subprocess
import sys

import yaml

COMPOSE_NAMES = {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}
PIN = re.compile(r"(?P<repository>[^\s@]+):(?P<tag>[^\s:@/]+)@sha256:[0-9a-f]{64}")


def image_errors(image: str) -> list[str]:
    match = PIN.fullmatch(image)
    if not match:
        return [f"{image}: use an explicit tag plus a full sha256 digest"]
    repository, tag = match.group("repository", "tag")
    # LinuxServer's four-part/version-* aliases can be mistaken for prereleases
    # when compared with the three-part stable alias behind its latest tag.
    if repository.startswith(("lscr.io/linuxserver/", "linuxserver/", "ghcr.io/linuxserver/")):
        if not re.fullmatch(r"\d+\.\d+\.\d+", tag):
            return [f"{image}: use LinuxServer's stable three-part numeric alias"]
    return []


def dockerfile_images(content: str) -> list[str]:
    stages: set[str] = set()
    images: list[str] = []
    for line in content.splitlines():
        words = line.split()
        if not words or words[0].upper() != "FROM":
            continue
        arguments = [word for word in words[1:] if not word.startswith("--")]
        image = arguments[0]
        if image.lower() != "scratch" and image.lower() not in stages:
            images.append(image)
        if len(arguments) >= 3 and arguments[1].upper() == "AS":
            stages.add(arguments[2].lower())
    return images


def audit(root: Path, paths: list[str]) -> list[str]:
    config = yaml.safe_load((root / ".github/dependabot.yml").read_text(encoding="utf-8"))
    coverage: set[tuple[str, str]] = set()
    for update in config["updates"]:
        if update.get("schedule", {}).get("interval") == "weekly" and update.get("open-pull-requests-limit", 5) > 0:
            directories = update.get("directories", [update.get("directory", "")])
            coverage.update((update["package-ecosystem"], directory.rstrip("/") or "/") for directory in directories)

    errors: list[str] = []
    for name in sorted(paths):
        path = Path(name)
        if path.name in COMPOSE_NAMES:
            data = yaml.safe_load((root / path).read_text(encoding="utf-8"))
            images = [service["image"] for service in data.get("services", {}).values() if "image" in service]
            ecosystem = "docker-compose"
        elif path.name == "Dockerfile" or path.name.startswith("Dockerfile."):
            images = dockerfile_images((root / path).read_text(encoding="utf-8"))
            ecosystem = "docker"
        else:
            continue
        for image in images:
            errors.extend(f"{name}: {error}" for error in image_errors(image))
        directory = "/" + path.parent.as_posix().strip(".").strip("/")
        if images and (ecosystem, directory) not in coverage:
            errors.append(f"{name}: missing enabled weekly {ecosystem} Dependabot entry for {directory}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    errors = audit(root, [path for path in paths if path])
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("All tracked Compose images and Dockerfile bases have digest pins and weekly update coverage")
    return 0


if __name__ == "__main__":
    sys.exit(main())
