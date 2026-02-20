# Changelog

All notable changes to TIDE will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1](https://github.com/Klazomenai/tide/compare/v0.1.0...v0.1.1) (2026-02-20)


### Added

* add build configuration ([25582a5](https://github.com/Klazomenai/tide/commit/25582a5cace4c60e11134b24f491812c6ff71817))
* add Helm chart ([7533669](https://github.com/Klazomenai/tide/commit/7533669e3c8cf9d0f2368c329c78b93ab6bddbd1))
* add release-please for automated release management ([bc4b036](https://github.com/Klazomenai/tide/commit/bc4b036b0d954dec9d8d39eb2d758c91051fead7)), closes [#12](https://github.com/Klazomenai/tide/issues/12)
* add release-please for automated release management ⛵ ([2aff36c](https://github.com/Klazomenai/tide/commit/2aff36c6db1d7b7b18d8ee1f4336a146060df115))
* add test suite ([5f0cd86](https://github.com/Klazomenai/tide/commit/5f0cd865f1cf08050e09554820056364c99b4252))
* add TIDE service source code ([a917b0b](https://github.com/Klazomenai/tide/commit/a917b0b7d84afa0d69b5fd2e5a202636170e0cc8))


### Fixed

* add commitlint config for conventional commit enforcement ([7c3ed6f](https://github.com/Klazomenai/tide/commit/7c3ed6fc735425287b9007fac4197ff53813c678)), closes [#12](https://github.com/Klazomenai/tide/issues/12)
* **ci:** gate version tag to default branch only ([efef5eb](https://github.com/Klazomenai/tide/commit/efef5ebaccc36f7b0d1faeda86f0df0945e17d57)), closes [#10](https://github.com/Klazomenai/tide/issues/10)
* **ci:** resolve GHCR publish permission and consolidate build job ([de51bfe](https://github.com/Klazomenai/tide/commit/de51bfe0eeec1da3df39898cdde384c8cc8b0329)), closes [#10](https://github.com/Klazomenai/tide/issues/10)
* **ci:** resolve GHCR publish permission and consolidate build job 🐛 ([92c9560](https://github.com/Klazomenai/tide/commit/92c956069de143ac71e6807f6cad9732f583d6dc))
* **docs:** correct default NTN amount from 1 to 10 ([5698037](https://github.com/Klazomenai/tide/commit/5698037289ac4430a311bb8166beb13a29454a9f))
* harden commitlint npm install against supply-chain attacks ([0d7d3f5](https://github.com/Klazomenai/tide/commit/0d7d3f5cf41726b148f23e552f2fd9f1d03eaf50)), closes [#12](https://github.com/Klazomenai/tide/issues/12)
* **helm:** default serviceMonitor.enabled to false ([9924185](https://github.com/Klazomenai/tide/commit/992418514cc8cdc4d2aa653a8461851a961be66f))
* **helm:** suppress secret echo in create-secret prompts ([404a70e](https://github.com/Klazomenai/tide/commit/404a70eaa295447f869130bac6584d582cfe7e77))
* **helm:** use /ready for readiness probe instead of /health ([468ac32](https://github.com/Klazomenai/tide/commit/468ac32066c031fe4318fbb9afe3be7953c29d0d))
* **logging:** use structured logging in service runtime ([47e24f3](https://github.com/Klazomenai/tide/commit/47e24f313e2045ca7b9854986dce42041b8e3a30))
* sync helm chart version with release-please ([c118786](https://github.com/Klazomenai/tide/commit/c118786704c9d39d7e23e2ebba78421fd50fed21)), closes [#12](https://github.com/Klazomenai/tide/issues/12)
* use bare version for docker image tags to match helm chart ([da0cab4](https://github.com/Klazomenai/tide/commit/da0cab42af8dc1ddd041614a50be53977cea0e7b)), closes [#12](https://github.com/Klazomenai/tide/issues/12)
* use github.ref_name for manual publish image tags ([c699086](https://github.com/Klazomenai/tide/commit/c6990869803891bda08e78d0c11d5d1796acfc0f)), closes [#12](https://github.com/Klazomenai/tide/issues/12)
* **wallet:** use fchmod for file descriptor and guard double-close ([52539fc](https://github.com/Klazomenai/tide/commit/52539fca162bf8d5aad6eb4436a152ce4ef6f349))


### Changed

* **ci:** split build and publish for least-privilege permissions ([9aee235](https://github.com/Klazomenai/tide/commit/9aee235f35a4e3fdb5b9f42d61580028abc51218)), closes [#10](https://github.com/Klazomenai/tide/issues/10)
* **tests:** extract shared test constants to tests/constants.py ([278278c](https://github.com/Klazomenai/tide/commit/278278c8f8fe9e7dd6d97d7419f828eca6e9b15e))

## [Unreleased]

### Added

- **feat(tide)**: Service foundation with Pydantic configuration
  - Configuration management via environment variables
  - CDP mode and emergency action enums
  - Faucet limits configuration
  - Slack and Redis configuration
  - Observability settings (metrics port, log level, log format)
