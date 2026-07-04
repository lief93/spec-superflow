// ssf install-workbuddy — deploy spec-superflow skills to WorkBuddy
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { fileURLToPath } from 'node:url';

const DEFAULT_MARKETPLACE = 'cb_teams_marketplace';
const __dirname = dirname(fileURLToPath(import.meta.url));
const defaultPluginRoot = resolve(__dirname, '..', '..');

function readJsonIfExists(filePath) {
  if (!existsSync(filePath)) return {};
  return JSON.parse(readFileSync(filePath, 'utf-8'));
}

function listSkillNames(skillsDir) {
  if (!existsSync(skillsDir)) {
    throw new Error(`skills/ directory not found at ${skillsDir}`);
  }
  return readdirSync(skillsDir)
    .filter(name => {
      const dir = join(skillsDir, name);
      return statSync(dir).isDirectory() && existsSync(join(dir, 'SKILL.md'));
    })
    .sort();
}

function planInstall({ pluginRoot = defaultPluginRoot, homeDir = homedir(), marketplaceName = DEFAULT_MARKETPLACE } = {}) {
  const root = resolve(pluginRoot);
  const skillsDir = join(root, 'skills');
  const skillNames = listSkillNames(skillsDir);
  const workbuddyRoot = join(homeDir, '.workbuddy');
  const pluginsDir = join(workbuddyRoot, 'plugins', 'marketplaces', marketplaceName, 'plugins');
  const settingsPath = join(workbuddyRoot, 'settings.json');
  const enabledPluginKeys = skillNames.map(name => `${name}@${marketplaceName}`);

  return {
    pluginRoot: root,
    skillsDir,
    skillNames,
    workbuddyRoot,
    pluginsDir,
    settingsPath,
    marketplaceName,
    enabledPluginKeys,
  };
}

function installWorkBuddy(options = {}) {
  const plan = planInstall(options);
  const { skillsDir, skillNames, pluginsDir, settingsPath, enabledPluginKeys } = plan;

  mkdirSync(pluginsDir, { recursive: true });
  for (const name of skillNames) {
    const target = join(pluginsDir, name);
    rmSync(target, { recursive: true, force: true });
    cpSync(join(skillsDir, name), target, { recursive: true });
  }

  mkdirSync(plan.workbuddyRoot, { recursive: true });
  const settings = readJsonIfExists(settingsPath);
  settings.enabledPlugins = settings.enabledPlugins && typeof settings.enabledPlugins === 'object'
    ? settings.enabledPlugins
    : {};
  for (const key of enabledPluginKeys) {
    settings.enabledPlugins[key] = true;
  }
  writeFileSync(settingsPath, JSON.stringify(settings, null, 2) + '\n');

  return plan;
}

export async function run(args) {
  const { values } = parseArgs({
    args,
    options: {
      local: { type: 'string' },
      home: { type: 'string' },
      marketplace: { type: 'string' },
      'dry-run': { type: 'boolean' },
    },
  });

  const plan = planInstall({
    pluginRoot: values.local || defaultPluginRoot,
    homeDir: values.home || homedir(),
    marketplaceName: values.marketplace || DEFAULT_MARKETPLACE,
  });

  if (values['dry-run']) {
    console.log('WorkBuddy install plan:');
    console.log(`  Skills:      ${plan.skillNames.length}`);
    console.log(`  Marketplace: ${plan.marketplaceName}`);
    console.log(`  Target:      ${plan.pluginsDir}`);
    console.log(`  Settings:    ${plan.settingsPath}`);
    return;
  }

  installWorkBuddy({
    pluginRoot: plan.pluginRoot,
    homeDir: values.home || homedir(),
    marketplaceName: plan.marketplaceName,
  });

  console.log('✅ WorkBuddy install complete:');
  console.log(`   Skills:      ${plan.skillNames.length}`);
  console.log(`   Marketplace: ${plan.marketplaceName}`);
  console.log(`   Target:      ${plan.pluginsDir}`);
  console.log(`\nNext: restart WorkBuddy and try "用 workflow-start 开始".`);
}

export { planInstall, installWorkBuddy };
