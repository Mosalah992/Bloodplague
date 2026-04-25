#!/usr/bin/env node

import fs from 'node:fs/promises';
import { createWriteStream } from 'node:fs';
import { once } from 'node:events';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  closeLbug,
  initLbug,
  streamQuery,
} from '../agents/shared/gitnexus/gitnexus/dist/core/lbug/lbug-adapter.js';
import { NODE_TABLES } from '../agents/shared/gitnexus/gitnexus-shared/dist/index.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..');
const repoName = path.basename(repoRoot);
const outputDir = path.join(repoRoot, 'reports', 'knowledge-graph');
const graphPath = path.join(outputDir, `${repoName}.graphml`);
const mermaidPath = path.join(outputDir, `${repoName}-overview.mmd`);
const summaryJsonPath = path.join(outputDir, `${repoName}-summary.json`);
const summaryReadmePath = path.join(outputDir, 'README.md');
const metaPath = path.join(repoRoot, '.gitnexus', 'meta.json');
const lbugPath = path.join(repoRoot, '.gitnexus', 'lbug');

const OVERVIEW_COMPONENT_LIMIT = 10;
const OVERVIEW_EDGE_LIMIT = 16;
const TOP_COMMUNITY_LIMIT = 15;
const TOP_PROCESS_LIMIT = 15;

const OVERVIEW_REL_TYPES = new Set([
  'CALLS',
  'IMPORTS',
  'EXTENDS',
  'IMPLEMENTS',
  'METHOD_IMPLEMENTS',
  'METHOD_OVERRIDES',
  'FETCHES',
  'HANDLES_ROUTE',
  'HANDLES_TOOL',
  'ENTRY_POINT_OF',
  'WRAPS',
  'QUERIES',
  'USES',
  'ACCESSES',
]);

const COMPONENT_COUNT_EXCLUSIONS = new Set(['Community', 'Process', 'Folder', 'File', 'Section']);
const ROOT_BUCKET = '(root)';
const NODE_QUERY_FIELDS = ['id', 'name', 'filePath', 'startLine', 'endLine'];
const COMMUNITY_FIELDS = ['id', 'label', 'heuristicLabel', 'cohesion', 'symbolCount'];
const PROCESS_FIELDS = [
  'id',
  'label',
  'heuristicLabel',
  'processType',
  'stepCount',
  'communities',
  'entryPointId',
  'terminalId',
];
const ROUTE_FIELDS = ['id', 'name', 'filePath', 'responseKeys', 'errorKeys', 'middleware'];
const TOOL_FIELDS = ['id', 'name', 'filePath', 'description'];
const EDGE_FIELDS = ['sourceId', 'targetId', 'type', 'confidence', 'reason', 'step'];

function quoteLabel(label) {
  return `\`${String(label).replace(/`/g, '``')}\``;
}

function getNodeQuery(table) {
  const label = quoteLabel(table);

  if (table === 'Community') {
    return `MATCH (n:${label}) RETURN n.id AS id, n.label AS label, n.heuristicLabel AS heuristicLabel, n.cohesion AS cohesion, n.symbolCount AS symbolCount`;
  }

  if (table === 'Process') {
    return `MATCH (n:${label}) RETURN n.id AS id, n.label AS label, n.heuristicLabel AS heuristicLabel, n.processType AS processType, n.stepCount AS stepCount, n.communities AS communities, n.entryPointId AS entryPointId, n.terminalId AS terminalId`;
  }

  if (table === 'Route') {
    return `MATCH (n:${label}) RETURN n.id AS id, n.name AS name, n.filePath AS filePath, n.responseKeys AS responseKeys, n.errorKeys AS errorKeys, n.middleware AS middleware`;
  }

  if (table === 'Tool') {
    return `MATCH (n:${label}) RETURN n.id AS id, n.name AS name, n.filePath AS filePath, n.description AS description`;
  }

  if (table === 'File' || table === 'Folder') {
    return `MATCH (n:${label}) RETURN n.id AS id, n.name AS name, n.filePath AS filePath`;
  }

  return `MATCH (n:${label}) RETURN n.id AS id, n.name AS name, n.filePath AS filePath, n.startLine AS startLine, n.endLine AS endLine`;
}

const EDGE_QUERY =
  "MATCH (a)-[r:CodeRelation]->(b) RETURN a.id AS sourceId, b.id AS targetId, r.type AS type, r.confidence AS confidence, r.reason AS reason, r.step AS step";

function normalizeRow(row, fields) {
  if (Array.isArray(row)) {
    return Object.fromEntries(fields.map((field, index) => [field, row[index]]));
  }

  return row ?? {};
}

function compactObject(value) {
  return Object.fromEntries(
    Object.entries(value).filter(([, entry]) => {
      if (entry === undefined || entry === null || entry === '') {
        return false;
      }

      if (Array.isArray(entry) && entry.length === 0) {
        return false;
      }

      return true;
    }),
  );
}

function xmlEscape(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function sanitizeMermaidId(value) {
  const sanitized = String(value).replace(/[^A-Za-z0-9_]/g, '_');
  return sanitized.length > 0 ? sanitized : 'node';
}

function formatNumber(value) {
  return new Intl.NumberFormat('en-US').format(value);
}

function increment(map, key, amount = 1) {
  map.set(key, (map.get(key) ?? 0) + amount);
}

function incrementNested(map, outerKey, innerKey, amount = 1) {
  let inner = map.get(outerKey);
  if (!inner) {
    inner = new Map();
    map.set(outerKey, inner);
  }

  inner.set(innerKey, (inner.get(innerKey) ?? 0) + amount);
}

function sortMapDescending(map) {
  return [...map.entries()].sort((left, right) => {
    if (right[1] !== left[1]) {
      return right[1] - left[1];
    }

    return String(left[0]).localeCompare(String(right[0]));
  });
}

function dominantTypes(typeMap) {
  if (!typeMap) {
    return [];
  }

  return [...typeMap.entries()]
    .sort((left, right) => {
      if (right[1] !== left[1]) {
        return right[1] - left[1];
      }

      return String(left[0]).localeCompare(String(right[0]));
    })
    .slice(0, 3)
    .map(([type]) => type);
}

function getTopLevel(filePath) {
  if (!filePath) {
    return null;
  }

  const normalized = String(filePath).replace(/\\/g, '/').replace(/^\.\//, '');
  const segments = normalized.split('/').filter(Boolean);

  if (segments.length === 0) {
    return null;
  }

  return segments.length === 1 ? ROOT_BUCKET : segments[0];
}

function getDisplayName(properties) {
  return properties.heuristicLabel || properties.name || '(anonymous)';
}

function isIgnorableGraphError(error) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    message.includes('does not exist') ||
    /(table|column|property).*not found/i.test(message) ||
    /binder exception/i.test(message)
  );
}

function mapNode(table, rawRow) {
  const row =
    table === 'Community'
      ? normalizeRow(rawRow, COMMUNITY_FIELDS)
      : table === 'Process'
        ? normalizeRow(rawRow, PROCESS_FIELDS)
        : table === 'Route'
          ? normalizeRow(rawRow, ROUTE_FIELDS)
          : table === 'Tool'
            ? normalizeRow(rawRow, TOOL_FIELDS)
            : normalizeRow(rawRow, NODE_QUERY_FIELDS);

  return {
    id: row.id,
    label: table,
    properties: compactObject({
      name: row.name ?? row.label,
      filePath: row.filePath,
      startLine: row.startLine,
      endLine: row.endLine,
      responseKeys: row.responseKeys,
      errorKeys: row.errorKeys,
      middleware: row.middleware,
      heuristicLabel: row.heuristicLabel,
      cohesion: row.cohesion,
      symbolCount: row.symbolCount,
      description: row.description,
      processType: row.processType,
      stepCount: row.stepCount,
      communities: row.communities,
      entryPointId: row.entryPointId,
      terminalId: row.terminalId,
    }),
  };
}

function mapEdge(rawRow) {
  const row = normalizeRow(rawRow, EDGE_FIELDS);

  return {
    id: `${row.sourceId}_${row.type}_${row.targetId}`,
    sourceId: row.sourceId,
    targetId: row.targetId,
    type: row.type,
    confidence: row.confidence,
    reason: row.reason,
    step: row.step,
  };
}

async function writeLine(stream, line) {
  if (!stream.write(line)) {
    await once(stream, 'drain');
  }
}

async function closeStream(stream) {
  await new Promise((resolve, reject) => {
    stream.on('error', reject);
    stream.end(resolve);
  });
}

function buildGraphMlHeader() {
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<graphml xmlns="http://graphml.graphdrawing.org/xmlns"',
    '         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
    '         xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">',
    '  <key id="d_label" for="node" attr.name="label" attr.type="string"/>',
    '  <key id="d_name" for="node" attr.name="name" attr.type="string"/>',
    '  <key id="d_filePath" for="node" attr.name="filePath" attr.type="string"/>',
    '  <key id="d_topLevel" for="node" attr.name="topLevel" attr.type="string"/>',
    '  <key id="d_startLine" for="node" attr.name="startLine" attr.type="int"/>',
    '  <key id="d_endLine" for="node" attr.name="endLine" attr.type="int"/>',
    '  <key id="d_properties" for="node" attr.name="properties" attr.type="string"/>',
    '  <key id="e_type" for="edge" attr.name="type" attr.type="string"/>',
    '  <key id="e_confidence" for="edge" attr.name="confidence" attr.type="double"/>',
    '  <key id="e_reason" for="edge" attr.name="reason" attr.type="string"/>',
    '  <key id="e_step" for="edge" attr.name="step" attr.type="int"/>',
    '  <graph id="BloodplagueKnowledgeGraph" edgedefault="directed">',
    '',
  ].join('\n');
}

function buildGraphMlNode(node, topLevel) {
  const properties = compactObject({
    ...node.properties,
    topLevel,
  });

  const lines = [`    <node id="${xmlEscape(node.id)}">`];
  lines.push(`      <data key="d_label">${xmlEscape(node.label)}</data>`);
  lines.push(`      <data key="d_name">${xmlEscape(getDisplayName(node.properties))}</data>`);

  if (node.properties.filePath) {
    lines.push(`      <data key="d_filePath">${xmlEscape(node.properties.filePath)}</data>`);
  }

  if (topLevel) {
    lines.push(`      <data key="d_topLevel">${xmlEscape(topLevel)}</data>`);
  }

  if (node.properties.startLine !== undefined) {
    lines.push(`      <data key="d_startLine">${xmlEscape(node.properties.startLine)}</data>`);
  }

  if (node.properties.endLine !== undefined) {
    lines.push(`      <data key="d_endLine">${xmlEscape(node.properties.endLine)}</data>`);
  }

  if (Object.keys(properties).length > 0) {
    lines.push(`      <data key="d_properties">${xmlEscape(JSON.stringify(properties))}</data>`);
  }

  lines.push('    </node>');
  return `${lines.join('\n')}\n`;
}

function buildGraphMlEdge(edge) {
  const lines = [
    `    <edge id="${xmlEscape(edge.id)}" source="${xmlEscape(edge.sourceId)}" target="${xmlEscape(edge.targetId)}">`,
    `      <data key="e_type">${xmlEscape(edge.type)}</data>`,
  ];

  if (edge.confidence !== undefined && edge.confidence !== null) {
    lines.push(`      <data key="e_confidence">${xmlEscape(edge.confidence)}</data>`);
  }

  if (edge.reason) {
    lines.push(`      <data key="e_reason">${xmlEscape(edge.reason)}</data>`);
  }

  if (edge.step !== undefined && edge.step !== null) {
    lines.push(`      <data key="e_step">${xmlEscape(edge.step)}</data>`);
  }

  lines.push('    </edge>');
  return `${lines.join('\n')}\n`;
}

function buildOverviewMermaid(components, crossComponentEdges) {
  const selected = new Set(components.map(({ name }) => name));
  const edges = crossComponentEdges
    .filter(({ source, target }) => selected.has(source) && selected.has(target))
    .slice(0, OVERVIEW_EDGE_LIMIT);

  const lines = [
    '%% Auto-generated from the GitNexus knowledge graph',
    'flowchart LR',
  ];

  for (const component of components) {
    const nodeId = sanitizeMermaidId(component.name);
    const label = `${component.name}\\n${formatNumber(component.symbolCount)} symbols`;
    lines.push(`  ${nodeId}["${label}"]`);
  }

  if (edges.length > 0) {
    lines.push('');
  }

  for (const edge of edges) {
    const source = sanitizeMermaidId(edge.source);
    const target = sanitizeMermaidId(edge.target);
    const label = `${formatNumber(edge.weight)} ${edge.dominantTypes.join('/')}`;
    lines.push(`  ${source} -->|"${label}"| ${target}`);
  }

  return `${lines.join('\n')}\n`;
}

function buildReadme({
  generatedAt,
  nodeCount,
  edgeCount,
  nodeLabelCounts,
  edgeTypeCounts,
  topComponents,
  crossComponentEdges,
  topCommunities,
  topProcesses,
  meta,
}) {
  const lines = [
    `# ${repoName} Knowledge Graph`,
    '',
    `Generated from GitNexus index data on ${generatedAt}.`,
    '',
    '## Artifacts',
    `- \`${path.relative(repoRoot, graphPath)}\` — full GraphML export for Gephi, Cytoscape, yEd, or Neo4j-adjacent tooling`,
    `- \`${path.relative(repoRoot, mermaidPath)}\` — reduced architecture view in Mermaid`,
    `- \`${path.relative(repoRoot, summaryJsonPath)}\` — machine-readable summary of this export`,
    '',
    '## Snapshot',
    `- Nodes: ${formatNumber(nodeCount)}`,
    `- Relationships: ${formatNumber(edgeCount)}`,
    `- Indexed files: ${meta?.stats?.files ? formatNumber(meta.stats.files) : 'n/a'}`,
    `- Indexed processes: ${meta?.stats?.processes ? formatNumber(meta.stats.processes) : 'n/a'}`,
    '',
    '## Node Labels',
    ...nodeLabelCounts.map(({ label, count }) => `- ${label}: ${formatNumber(count)}`),
    '',
    '## Relationship Types',
    ...edgeTypeCounts.map(({ type, count }) => `- ${type}: ${formatNumber(count)}`),
    '',
    '## Largest Code Areas',
    ...topComponents.map(
      ({ name, symbolCount }) => `- ${name}: ${formatNumber(symbolCount)} indexed symbols with file ownership`,
    ),
    '',
    '## Strongest Cross-Area Dependencies',
    ...crossComponentEdges.slice(0, 12).map(
      ({ source, target, weight, dominantTypes }) =>
        `- ${source} -> ${target}: ${formatNumber(weight)} edges (${dominantTypes.join(', ')})`,
    ),
    '',
    '## Largest Communities',
    ...topCommunities.map(
      ({ name, symbolCount, cohesion }) =>
        `- ${name}: ${formatNumber(symbolCount)} symbols, cohesion ${cohesion.toFixed(3)}`,
    ),
    '',
    '## Longest Execution Flows',
    ...topProcesses.map(
      ({ name, stepCount, processType }) =>
        `- ${name}: ${formatNumber(stepCount)} steps (${processType || 'unknown'})`,
    ),
    '',
  ];

  return `${lines.join('\n')}`;
}

async function prepareWorkingDb() {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), `${repoName}-gitnexus-`));
  const workingDbPath = path.join(tempDir, 'lbug');

  await fs.copyFile(lbugPath, workingDbPath);

  return { tempDir, workingDbPath };
}

async function main() {
  const meta = JSON.parse(await fs.readFile(metaPath, 'utf8'));
  await fs.mkdir(outputDir, { recursive: true });

  const { tempDir, workingDbPath } = await prepareWorkingDb();
  await initLbug(workingDbPath);

  const graphStream = createWriteStream(graphPath, { encoding: 'utf8' });
  const nodeIndex = new Map();
  const nodeLabelCounts = new Map();
  const edgeTypeCounts = new Map();
  const componentCounts = new Map();
  const crossComponentEdgeCounts = new Map();
  const crossComponentEdgeTypes = new Map();
  const communities = [];
  const processes = [];

  let nodeCount = 0;
  let edgeCount = 0;

  try {
    await writeLine(graphStream, buildGraphMlHeader());

    for (const table of NODE_TABLES) {
      try {
        await streamQuery(getNodeQuery(table), async (row) => {
          const node = mapNode(table, row);
          const topLevel = getTopLevel(node.properties.filePath);

          nodeIndex.set(node.id, {
            id: node.id,
            label: node.label,
            name: getDisplayName(node.properties),
            filePath: node.properties.filePath ?? null,
            topLevel,
          });

          nodeCount += 1;
          increment(nodeLabelCounts, node.label);

          if (topLevel && !COMPONENT_COUNT_EXCLUSIONS.has(node.label)) {
            increment(componentCounts, topLevel);
          }

          if (node.label === 'Community') {
            communities.push({
              id: node.id,
              name: getDisplayName(node.properties),
              cohesion: Number(node.properties.cohesion ?? 0),
              symbolCount: Number(node.properties.symbolCount ?? 0),
            });
          }

          if (node.label === 'Process') {
            processes.push({
              id: node.id,
              name: getDisplayName(node.properties),
              stepCount: Number(node.properties.stepCount ?? 0),
              processType: node.properties.processType ?? null,
            });
          }

          await writeLine(graphStream, buildGraphMlNode(node, topLevel));
        });
      } catch (error) {
        if (!isIgnorableGraphError(error)) {
          throw error;
        }
      }
    }

    try {
      await streamQuery(EDGE_QUERY, async (row) => {
        const edge = mapEdge(row);
        const source = nodeIndex.get(edge.sourceId);
        const target = nodeIndex.get(edge.targetId);

        edgeCount += 1;
        increment(edgeTypeCounts, edge.type);

        if (
          source?.topLevel &&
          target?.topLevel &&
          source.topLevel !== target.topLevel &&
          OVERVIEW_REL_TYPES.has(edge.type)
        ) {
          const pairKey = `${source.topLevel}|||${target.topLevel}`;
          increment(crossComponentEdgeCounts, pairKey);
          incrementNested(crossComponentEdgeTypes, pairKey, edge.type);
        }

        await writeLine(graphStream, buildGraphMlEdge(edge));
      });
    } catch (error) {
      if (!isIgnorableGraphError(error)) {
        throw error;
      }
    }

    await writeLine(graphStream, '  </graph>\n</graphml>\n');
  } finally {
    await closeStream(graphStream);
    await closeLbug();
    await fs.rm(tempDir, { recursive: true, force: true });
  }

  const sortedNodeLabels = sortMapDescending(nodeLabelCounts).map(([label, count]) => ({ label, count }));
  const sortedEdgeTypes = sortMapDescending(edgeTypeCounts).map(([type, count]) => ({ type, count }));
  const topComponents = sortMapDescending(componentCounts)
    .slice(0, OVERVIEW_COMPONENT_LIMIT)
    .map(([name, symbolCount]) => ({ name, symbolCount }));

  const crossComponentEdges = sortMapDescending(crossComponentEdgeCounts).map(([pair, weight]) => {
    const [source, target] = pair.split('|||');
    return {
      source,
      target,
      weight,
      dominantTypes: dominantTypes(crossComponentEdgeTypes.get(pair)),
    };
  });

  const topCommunities = communities
    .sort((left, right) => {
      if (right.symbolCount !== left.symbolCount) {
        return right.symbolCount - left.symbolCount;
      }

      if (right.cohesion !== left.cohesion) {
        return right.cohesion - left.cohesion;
      }

      return left.name.localeCompare(right.name);
    })
    .slice(0, TOP_COMMUNITY_LIMIT);

  const topProcesses = processes
    .sort((left, right) => {
      if (right.stepCount !== left.stepCount) {
        return right.stepCount - left.stepCount;
      }

      return left.name.localeCompare(right.name);
    })
    .slice(0, TOP_PROCESS_LIMIT);

  const summary = {
    repoName,
    generatedAt: new Date().toISOString(),
    source: {
      metaPath: path.relative(repoRoot, metaPath),
      lbugPath: path.relative(repoRoot, lbugPath),
      lastCommit: meta.lastCommit,
      indexedAt: meta.indexedAt,
      stats: meta.stats,
    },
    graph: {
      nodes: nodeCount,
      edges: edgeCount,
      nodeLabelCounts: sortedNodeLabels,
      edgeTypeCounts: sortedEdgeTypes,
    },
    overview: {
      components: topComponents,
      crossComponentEdges,
    },
    communities: topCommunities,
    processes: topProcesses,
    artifacts: {
      graphml: path.relative(repoRoot, graphPath),
      mermaid: path.relative(repoRoot, mermaidPath),
      readme: path.relative(repoRoot, summaryReadmePath),
    },
  };

  await fs.writeFile(summaryJsonPath, `${JSON.stringify(summary, null, 2)}\n`, 'utf8');
  await fs.writeFile(mermaidPath, buildOverviewMermaid(topComponents, crossComponentEdges), 'utf8');
  await fs.writeFile(
    summaryReadmePath,
    buildReadme({
      generatedAt: summary.generatedAt,
      nodeCount,
      edgeCount,
      nodeLabelCounts: sortedNodeLabels,
      edgeTypeCounts: sortedEdgeTypes,
      topComponents,
      crossComponentEdges,
      topCommunities,
      topProcesses,
      meta,
    }),
    'utf8',
  );

  process.stdout.write(
    [
      `Wrote ${path.relative(repoRoot, graphPath)}`,
      `Wrote ${path.relative(repoRoot, mermaidPath)}`,
      `Wrote ${path.relative(repoRoot, summaryJsonPath)}`,
      `Wrote ${path.relative(repoRoot, summaryReadmePath)}`,
    ].join('\n') + '\n',
  );
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});
