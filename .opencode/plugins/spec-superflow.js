import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const PLUGIN_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const SKILLS_DIR = join(PLUGIN_ROOT, 'skills');
const LAUNCHER = join(PLUGIN_ROOT, 'servers', 'spec-superflow-mcp-launcher.cmd');
const MCP_SERVER = join(PLUGIN_ROOT, 'servers', 'spec-superflow-mcp.mjs');

function markdownBody(relativePath) {
  const source = readFileSync(join(PLUGIN_ROOT, relativePath), 'utf8');
  const frontmatter = source.match(/^---\r?\n[\s\S]*?\r?\n---\r?\n/);
  if (!frontmatter) {
    throw new Error(`Missing frontmatter in ${relativePath}`);
  }
  return source.slice(frontmatter[0].length).trim();
}

function markdownBodies(...relativePaths) {
  return relativePaths.map(markdownBody).join('\n\n');
}

function addUnique(list, value) {
  if (!list.includes(value)) list.push(value);
}

function normalizeReviewerTask(args) {
  if (args?.subagent_type !== 'spec-superflow-reviewer') return;
  const prompt = typeof args.prompt === 'string' ? args.prompt : '';
  const change = /\bchange\s+`?(changes\/[a-z0-9][a-z0-9-]*)`?/i.exec(prompt)?.[1];
  const stage = /\bstage\s+`?(proposal-specs|design-tasks|final)`?/i.exec(prompt)?.[1];
  if (!change || !stage) {
    throw new Error('Reviewer task requires exactly one change directory and review stage');
  }
  args.description = `Review ${stage}`;
  args.prompt = `Review change \`${change}\` at stage \`${stage}\`.`;
}

export const SpecSuperflowPlugin = async () => {
  return {
    config: async config => {
      config.skills ??= {};
      config.skills.paths ??= [];
      addUnique(config.skills.paths, SKILLS_DIR);

      config.agent ??= {};
      config.agent['spec-superflow'] = {
        description: 'Manage development through the Spec Superflow SDD workflow.',
        mode: 'primary',
        color: 'accent',
        prompt: markdownBody('.opencode/agents/spec-superflow.md'),
        permission: {
          skill: 'allow',
          question: 'allow',
          task: {
            '*': 'deny',
            'spec-superflow-reviewer': 'allow',
          },
          'spec-superflow_*': 'deny',
        },
      };
      config.agent['spec-superflow-setup'] = {
        description: 'Initialize or update the Spec Superflow runtime.',
        mode: 'subagent',
        hidden: true,
        prompt: markdownBody('.opencode/agents/spec-superflow-setup.md'),
        permission: {
          '*': 'deny',
          question: 'allow',
          'spec-superflow_*': 'allow',
        },
      };
      config.agent['spec-superflow-reviewer'] = {
        description: 'Perform one independent read-only semantic review.',
        mode: 'subagent',
        hidden: true,
        prompt: markdownBodies(
          '.opencode/agents/spec-superflow-reviewer.md',
          'agents/spec-superflow-reviewer.agent.md',
        ),
      };

      config.command ??= {};
      config.command['workflow-init'] = {
        description: 'Initialize or update the Spec Superflow workflow runtime.',
        agent: 'spec-superflow-setup',
        subtask: false,
        template: markdownBody('.opencode/commands/workflow-init.md'),
      };

      config.mcp ??= {};
      config.mcp['spec-superflow'] ??= {
        type: 'local',
        command: [LAUNCHER, MCP_SERVER],
        cwd: PLUGIN_ROOT,
        enabled: true,
        environment: {
          SPEC_SUPERFLOW_PLUGIN_HOST: 'opencode',
        },
      };
    },

    'tool.execute.before': async (input, output) => {
      if (input.tool === 'task') normalizeReviewerTask(output.args);
    },

  };
};

export default {
  id: 'spec-superflow',
  server: SpecSuperflowPlugin,
};
