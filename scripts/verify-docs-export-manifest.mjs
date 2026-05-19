#!/usr/bin/env node
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

const repoRoot = process.cwd();
const manifestPath = 'conformance/docs_export_manifest.json';
const examplesManifestPath = 'conformance/examples_manifest.json';
const exampleDocPattern = /^examples\/(patterns|integrations|apps)\/([^/]+)\/(.+\.md)$/;
const immediateCompanionPattern = /^examples\/(patterns|integrations|apps)\/([^/]+)\/(?!README\.md$)[^/]+\.md$/;

const trackedMarkdown = gitTrackedMarkdown();
const examplesManifest = readJson(examplesManifestPath);
const docsManifest = readJson(manifestPath);

const canonicalReadmes = new Set();
for (const example of examplesManifest.examples ?? []) {
  if (!example?.category || !example?.name) {
    throw new Error(`examples_manifest entry is missing category/name: ${JSON.stringify(example)}`);
  }
  canonicalReadmes.add(`examples/${example.category}/${example.name}/README.md`);
}

const approvedCompanions = new Set();
const approvedRoutes = new Set();

if (docsManifest.schema_version !== 1) {
  throw new Error(`${manifestPath}: schema_version must be 1`);
}

for (const [index, doc] of (docsManifest.companion_docs ?? []).entries()) {
  const source = normalizeRepoPath(doc.source);
  const label = `${manifestPath}: companion_docs[${index}]`;

  if (!source) throw new Error(`${label}: source is required`);
  if (!doc.title) throw new Error(`${label}: title is required`);
  if (!doc.description) throw new Error(`${label}: description is required`);
  if (!immediateCompanionPattern.test(source)) {
    throw new Error(`${label}: source must be an immediate non-README Markdown file under examples/{patterns,integrations,apps}/{example}/`);
  }
  if (!trackedMarkdown.has(source)) {
    throw new Error(`${label}: source is not a tracked Markdown file: ${source}`);
  }
  if (!existsSync(path.join(repoRoot, source))) {
    throw new Error(`${label}: source does not exist: ${source}`);
  }

  const match = source.match(exampleDocPattern);
  const parentReadme = `examples/${match[1]}/${match[2]}/README.md`;
  if (!canonicalReadmes.has(parentReadme)) {
    throw new Error(`${label}: companion parent is not a manifest example: ${parentReadme}`);
  }

  const slug = doc.slug ? slugify(doc.slug) : slugFromMarkdown(source);
  const routeKey = `${match[1]}/${match[2]}/${slug}`;
  if (approvedRoutes.has(routeKey)) {
    throw new Error(`${label}: duplicate docs route slug: ${routeKey}`);
  }

  approvedRoutes.add(routeKey);
  approvedCompanions.add(source);
}

const unapprovedImmediateCompanions = [...trackedMarkdown]
  .filter((source) => immediateCompanionPattern.test(source))
  .filter((source) => !approvedCompanions.has(source))
  .sort();

if (unapprovedImmediateCompanions.length > 0) {
  console.error('Unapproved immediate companion doc candidates:');
  for (const source of unapprovedImmediateCompanions) console.error(`- ${source}`);
  console.error(`Add approved companion docs to ${manifestPath}, or move/support them as non-doc implementation notes.`);
  process.exit(1);
}

const canonicalMissing = [...canonicalReadmes]
  .filter((source) => !trackedMarkdown.has(source))
  .sort();

if (canonicalMissing.length > 0) {
  console.error('Manifest examples missing canonical README docs:');
  for (const source of canonicalMissing) console.error(`- ${source}`);
  process.exit(1);
}

const nestedMarkdown = [...trackedMarkdown]
  .filter((source) => source.startsWith('examples/'))
  .filter((source) => !canonicalReadmes.has(source))
  .filter((source) => !approvedCompanions.has(source))
  .filter((source) => !immediateCompanionPattern.test(source))
  .sort();

console.log(`docs export manifest: ${canonicalReadmes.size} canonical example README page(s)`);
console.log(`docs export manifest: ${approvedCompanions.size} approved companion page(s)`);
console.log(`docs export manifest: ${nestedMarkdown.length} nested/template Markdown file(s) intentionally not exported`);

function readJson(relativePath) {
  const fullPath = path.join(repoRoot, relativePath);
  return JSON.parse(readFileSync(fullPath, 'utf8'));
}

function gitTrackedMarkdown() {
  const output = execFileSync('git', ['ls-files', '*.md'], {
    cwd: repoRoot,
    encoding: 'utf8',
  });
  return new Set(output.split('\n').filter(Boolean).map(normalizeRepoPath));
}

function normalizeRepoPath(value) {
  const normalized = path.posix.normalize(String(value ?? '').replace(/\\/g, '/'));
  if (!normalized || normalized === '.' || normalized.startsWith('../') || path.posix.isAbsolute(normalized)) {
    throw new Error(`Invalid repo-relative path: ${value}`);
  }
  if (normalized.includes('/.tmp/') || normalized.includes('/internal/') || normalized.includes('/.')) {
    throw new Error(`Path is not eligible for docs export: ${value}`);
  }
  return normalized;
}

function slugFromMarkdown(source) {
  return slugify(path.posix.basename(source, '.md'));
}

function slugify(value) {
  return String(value)
    .trim()
    .toLowerCase()
    .replace(/_/g, '-')
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/^-+|-+$/g, '');
}
