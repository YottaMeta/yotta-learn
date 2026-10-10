'use strict';
// v0.5.0: bin/yotta-learn.js runtime dispatcher (runtime commands -> Python, install -> installer).
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const BIN = path.join(__dirname, '..', 'bin', 'yotta-learn.js');
const ROOT = path.join(__dirname, '..');

function run(args, opts = {}) {
  return spawnSync(process.execPath, [BIN, ...args], {
    encoding: 'utf8',
    cwd: opts.cwd || ROOT,
    env: Object.assign({}, process.env, opts.env || {}),
  });
}

test('--version prints the package version', () => {
  const r = run(['--version']);
  assert.strictEqual(r.status, 0, r.stderr);
  const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8'));
  assert.strictEqual(r.stdout.trim(), 'yotta-learn v' + pkg.version);
});

test('--help prints runtime help with install guidance', () => {
  const r = run(['--help']);
  assert.strictEqual(r.status, 0, r.stderr);
  assert.match(r.stdout, /运行时命令/);
  assert.match(r.stdout, /yotta-learn view/);
  assert.match(r.stdout, /yotta-learn install --agent/);
  assert.match(r.stdout, /yotta-learn-install/);
  assert.match(r.stdout, /YOTTA_LEARN_PYTHON/);
});

test('install subcommand forwards to the installer', () => {
  const r = run(['install', '--help']);
  assert.strictEqual(r.status, 0, r.stderr);
  assert.match(r.stdout, /用法:/);
  assert.match(r.stdout, /--agent/);
});

test('legacy installer flags still forward to the installer', () => {
  const r = run(['--list']);
  assert.strictEqual(r.status, 0, r.stderr);
  assert.match(r.stdout, /智能体 -> 默认技能目录/);
});

test('runtime commands forward to the Python CLI (kb --help)', () => {
  const r = run(['kb', '--help']);
  assert.strictEqual(r.status, 0, r.stderr);
  assert.match(r.stdout, /category/);
  assert.match(r.stdout, /query/);
});

test('view --help forwards to the runtime and does not start a server', () => {
  const r = run(['view', '--help']);
  assert.strictEqual(r.status, 0, r.stderr);
  assert.match(r.stdout, /--port/);
  assert.doesNotMatch(r.stdout, /已启动/);
});

test('a broken YOTTA_LEARN_PYTHON override falls back to auto-detection', () => {
  const r = run(['kb', '--help'], { env: { YOTTA_LEARN_PYTHON: 'definitely-not-a-python-xyz' } });
  assert.strictEqual(r.status, 0, r.stderr);
  assert.match(r.stdout, /category/);
});

test('an override that fails the probe is skipped (non-zero exit does not leak)', () => {
  // node 不是 Python：探测应判失败并回退到真实解释器，而不是把退出码当脚本结果。
  const r = run(['kb', '--help'], { env: { YOTTA_LEARN_PYTHON: process.execPath } });
  assert.strictEqual(r.status, 0, r.stderr);
  assert.match(r.stdout, /category/);
});
