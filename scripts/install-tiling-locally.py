#!/usr/bin/env python3
"""Extract verified APT packages into the repository for user-local tiling."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO = Path(__file__).resolve().parent.parent
PACKAGES = REPO / "state/tiling/packages"
BIN = REPO / "state/bin"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--test-display", action="store_true", help="Also download the optional Xvfb verification server")
    args = parser.parse_args()
    names = ["bspwm", "sxhkd"] + (["xvfb"] if args.test_display else [])
    versions = {}
    for name in names:
        policy = subprocess.run(["apt-cache", "policy", name], check=True, capture_output=True, text=True).stdout
        match = re.search(r"Candidate:\s+(\S+)", policy)
        if not match or match[1] == "(none)":
            raise RuntimeError("No APT candidate for " + name)
        versions[name] = match[1]
    print("User-local packages:", ", ".join(f"{name}={version}" for name, version in versions.items()))
    if not args.apply:
        print("Preview only. Use --apply to download and extract; no root privileges required.")
        return
    if (REPO / "state/tiling/ready").exists():
        raise RuntimeError("Restore XFWM before replacing binaries used by the active tiling session.")
    PACKAGES.mkdir(parents=True, exist_ok=True)
    BIN.mkdir(parents=True, exist_ok=True)
    subprocess.run(["apt-get", "download", *[f"{name}={version}" for name, version in versions.items()]],
                   cwd=PACKAGES, check=True)
    manifest = []
    for name, version in versions.items():
        choices = []
        for package in PACKAGES.glob(name + "_*.deb"):
            found = subprocess.run(["dpkg-deb", "--field", str(package), "Version"],
                                   check=True, capture_output=True, text=True).stdout.strip()
            if found == version:
                choices.append(package)
        if len(choices) != 1:
            raise RuntimeError("Expected one downloaded package for " + name)
        package, target = choices[0], PACKAGES / name
        subprocess.run(["dpkg-deb", "--extract", str(package), str(target)], check=True)
        binaries = {"bspwm": ("bspwm", "bspc"), "sxhkd": ("sxhkd",), "xvfb": ("Xvfb",)}[name]
        for binary in binaries:
            path, source = BIN / binary, (target / "usr/bin" / binary).resolve()
            if path.is_symlink() and path.resolve() == source:
                continue
            if path.exists() or path.is_symlink():
                raise RuntimeError("Refusing to replace an existing binary: " + str(path))
            dependencies = subprocess.run(["ldd", str(source)], capture_output=True, text=True, check=True).stdout
            if "not found" in dependencies:
                raise RuntimeError("Missing libraries for " + binary + ":\n" + dependencies)
            path.symlink_to(source)
        manifest.append({"package": name, "version": version,
                         "sha256": hashlib.sha256(package.read_bytes()).hexdigest()})
    (REPO / "state/tiling/local-packages.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Local binaries ready; apply with python3 scripts/configure-tiling.py --apply")


if __name__ == "__main__":
    main()
