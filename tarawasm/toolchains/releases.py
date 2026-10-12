"""Verified release SHA256 values, keyed by tool, version, OS and architecture.

TinyGo/Binaryen: official GitHub release asset digests (or .sha256 for 116).
Go: https://go.dev/dl/?mode=json&include=all.
This stdlib-only module is also used by the Docker toolchain build.
"""

RELEASE_CHECKSUMS = {
    "tinygo": {
        "0.42.0": {
            "darwin": {
                "arm64": "493da3585e66c5da677a4be39402faf2041b4e45a61eb456e4547eca753a544e",
                "amd64": "ef7b96cf59de5714a7493a696e9db141a85a99459620b00c42cb3bad14be2af2",
            },
            "linux": {
                "amd64": "b87688fa2e19cee7d813cad7fd7dadb71dff3198e47125aba66ba4af5e490438",
            },
        },
        "0.43.0": {
            "darwin": {
                "arm64": "f5e0161f212fb69ad4650a4809e3ca66856e184892e80058f0d47abc64151812",
                "amd64": "e544fe732d7b81f058ac8d2c7303e22031eff734c027295e7a53c3037e4d9e89",
            },
            "linux": {
                "amd64": "ca9fc6d055e3889462dea4450a2e42a92242d88b5c362a7ec39bdb563413d78a",
            },
        },
    },
    "go": {
        "1.27.1": {
            "darwin": {
                "arm64": "ee215d57e0ec269c60cc9ceca68e6bda321ba9ee5afe24f4b0988703c2d87d12",
                "amd64": "8f8f52c6649542cf027bbc9b9c68d1ec042f9f34808a40413f0b8b3f66f3caa4",
            },
            "linux": {
                "amd64": "63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445",
            },
        },
        "1.27.2": {
            "darwin": {
                "arm64": "76812b213b1b2302c978d28fa52fa92d541704b9e7d9d5db8002c50e4018c4c5",
                "amd64": "587b59182488b23aa6e5fc25110405a3e0e5b38ed2f5b2f46ed13c32aee356fe",
            },
            "linux": {
                "amd64": "ecbadb99091a3f46e31f5f934b068b1864eafa7995211b39eaddf76996045fe5",
            },
        },
    },
    "binaryen": {
        "116": {
            "darwin": {
                "arm64": "d8c978aec366629eae6fefbcedaf5093b829e4c5ab0e2990973b6e337c544867",
                "amd64": "266f63d3d8d9e17d5e532b8fc6c5340f92b3fea2020a634957a6dd938294ba56",
            },
            "linux": {
                "amd64": "c55b74f3109cdae97490faf089b0286d3bba926bb6ea5ed00c8c784fc53718fd",
            },
        },
        "133": {
            "darwin": {
                "arm64": "ad66da82ac13f163e424b1643f16c6dfcccc98b5966296b43e52d3cab04f84a8",
                "amd64": "13a9b90be775c6389ce3d1f879cb8627bea56708ba8c122983941d53a8199b95",
            },
            "linux": {
                "amd64": "2dc9c7813f5375db93d96ead4b78222fcc3e2677bbb832297af4797782a37489",
            },
        },
    },
}


def checksum_for(tool: str, version: str, system: str, architecture: str) -> str:
    try:
        return RELEASE_CHECKSUMS[tool][version][system][architecture]
    except KeyError as exc:
        raise ValueError(
            f"No verified SHA256 for {tool} {version} on {system}/{architecture}"
        ) from exc
