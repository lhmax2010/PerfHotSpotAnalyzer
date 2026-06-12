# A3 Tizen Symbolize Test Guide

## Scope

A3 validates Tizen device capture and host-side cross-symbolization:

- ssh+scp as the primary DeviceRunner backend
- sdb as the fallback backend
- target-side `perf record`, `perf script`, and `perf buildid-list`
- offline host analysis from `perf-script.txt`
- build-id/sysroot/debuginfo mapping into `tizen.path_mapping`

It does not validate workflow orchestration, Skill B patch generation, or
automatic build/test/rerun on the device.

## Prerequisites

- Linux host with Python test dependencies installed.
- Target Tizen image with `perf`.
- For ssh backend: root-capable image, `openssh-server`, running `sshd`, and
  host public key in target `~/.ssh/authorized_keys`.
- For sdb fallback: Tizen Studio `sdb` on host and `sdb devices` showing the
  target.
- Host-side sysroot and debuginfo roots matching the target build IDs.

Tizen images often do not ship with sshd enabled. On target, use the image's
package manager or build image tooling to install OpenSSH, then run:

```bash
systemctl enable sshd
systemctl start sshd
mkdir -p ~/.ssh
cat /tmp/host_id.pub >> ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

## Deterministic CI Path

```bash
pytest tests/functional/test_a3_tizen_symbolize.py -q
```

Expected result: 2 passed.

Manual equivalent:

```bash
python3 -m cli.perf_hotspot_analyzer analyze \
  --bundle-dir tests/fixtures/golden/live-perf/tizen-arm/bundle \
  --repo-root tests/fixtures/golden/live-perf/tizen-arm \
  --ownership tests/fixtures/golden/live-perf/tizen-arm/.perf-skill/ownership.yaml \
  --output /tmp/a3-postprocess.json \
  --output-dir /tmp/a3-analyze

python3 -m cli.perf_hotspot_analyzer report \
  --analysis /tmp/a3-postprocess.json \
  --repo-root tests/fixtures/golden/live-perf/tizen-arm \
  --output-dir /tmp/a3-report
```

Pass criteria:

- `/tmp/a3-report/performance-findings.json` validates with
  `common/schema_validate.py`.
- `target.platform.os` is `tizen`.
- `target.platform.arch` is `aarch64`.
- Top-1 finding is `tizen_hot`.
- Top-1 anchor file is `src/tizen_hot.c`.
- Top-1 `anchor_confidence` is at least `0.7`.
- `tizen.path_mapping` contains target path, host sysroot path, debuginfo path,
  source path, and build-id.

## SSH Device Profile

Create `.perf-skill/devices/tizen-arm-ssh.yaml` in the profiled repository:

```yaml
name: tizen-arm-ssh
backend: ssh
host: 192.0.2.20
user: root
ssh_opts: "-o BatchMode=yes -o StrictHostKeyChecking=accept-new"
scp_opts: "-o BatchMode=yes -o StrictHostKeyChecking=accept-new"
remote_workdir: /tmp/perf-skill
perf_path: /usr/bin/perf
needs_sudo: false
arch: aarch64
tizen_version: "7.0"
sysroot: /opt/tizen/sysroot
debuginfo_roots:
  - /opt/tizen/debuginfo
target_has_stackcollapse: false
```

Check connectivity before capture:

```bash
ssh -o BatchMode=yes root@192.0.2.20 'uname -a; command -v perf'
scp tests/fixtures/golden/live-perf/tizen-arm/capture-job.yaml root@192.0.2.20:/tmp/
```

If ssh fails with connection refused, install/start `openssh-server` on the
image. If it fails with public key denied, refresh `authorized_keys`. The skill
does not retry silently or elevate privileges.

## SSH Capture

Create a capture job:

```yaml
device: tizen-arm-ssh
target:
  kind: command
  command: "/usr/bin/a3-demo --workload"
perf:
  events: [cycles]
  freq_hz: 499
  callgraph: dwarf
  duration_s: 10
  repeat: 1
  warmup: 0
output:
  bundle_name: tizen-a3-live
```

Run capture:

```bash
python3 -m cli.perf_hotspot_analyzer capture \
  --job .perf-skill/jobs/tizen-a3-live.yaml \
  --repo-root . \
  --output-dir out/captures \
  --verbose
```

Expected bundle:

- `perf.data`
- `perf-script.txt`
- `out.folded`
- `perf-report.txt`
- `kallsyms`
- `proc-<pid>-maps`
- `dso-list.txt`
- `run-context.json`
- `exec.log`
- `manifest.json`
- `capture-job.yaml`

Then analyze and report:

```bash
python3 -m cli.perf_hotspot_analyzer analyze \
  --bundle-dir out/captures/tizen-a3-live \
  --repo-root . \
  --ownership .perf-skill/ownership.yaml \
  --output out/a3-postprocess.json \
  --output-dir out/a3-analyze

python3 -m cli.perf_hotspot_analyzer report \
  --analysis out/a3-postprocess.json \
  --repo-root . \
  --output-dir out/a3-report
```

## SDB Fallback

Create `.perf-skill/devices/tizen-arm-sdb.yaml`:

```yaml
name: tizen-arm-sdb
backend: sdb
sdb_serial: "TARGET_SERIAL"
remote_workdir: /tmp/perf-skill
perf_path: /usr/bin/perf
needs_sudo: false
arch: aarch64
tizen_version: "7.0"
sysroot: /opt/tizen/sysroot
debuginfo_roots:
  - /opt/tizen/debuginfo
target_has_stackcollapse: false
```

Smoke check:

```bash
sdb devices
sdb -s TARGET_SERIAL shell 'uname -a; command -v perf'
```

Use the same capture job shape with `device: tizen-arm-sdb`.

## Debug Logs

Each command writes:

- `<output-dir>/run-<trace_id>.jsonl`
- `<output-dir>/run-report.json`

For transport failures, inspect trace events named `shell`, `push`, or `pull`.
The stderr includes backend-specific remediation for host reachability, ssh key
denials, missing sshd, missing `sdb`, timeouts, or target permission problems.

## Feedback Attachments

Attach these files for review:

- device profile yaml
- capture job yaml
- bundle `manifest.json`
- bundle `perf-script.txt`
- bundle `dso-list.txt`
- bundle `exec.log`
- postprocess JSON
- `performance-findings.json`
- `analysis-report.md`
- both `run-report.json` files
