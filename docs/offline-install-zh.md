# Spec Superflow 离线安装与更新

适用于公司内网不能访问公网 npm 或 GitHub 的环境。离线目录中的同一个
`spec-superflow-<version>.tgz` 同时提供 CLI 和 Plugin 文件，因此两者不会来自
不同版本。

## 前置条件

- Node.js 22 或更高版本已通过公司软件渠道安装。
- VS Code 已启用 Agent Plugins。
- 将整个离线目录复制到公司电脑，并先校验 `SHA256SUMS`。

macOS / Linux：

```bash
shasum -a 256 -c SHA256SUMS
```

## 安装 CLI

安装并启用 Plugin 后，选择 **Spec Superflow** Agent，在 Chat 中执行：

```text
/workflow-init package=/absolute/path/spec-superflow-<version>.tgz
```

命令会检查 Node、安装本地 tgz、验证精确版本并返回 `READY`。它不会访问或修改
npm registry。也可以在离线目录直接执行等价的终端命令：

在离线目录执行：

```bash
npm install -g ./spec-superflow-<version>.tgz
ssf --version
ssf doctor
```

命令只读取本地 tgz，不需要修改 npm registry。升级时执行相同命令覆盖旧版本。

## 安装 Plugin

将 tgz 解压到一个长期稳定、所有业务仓库都能读取的位置：

```bash
mkdir -p ~/company-tools/spec-superflow-<version>
tar -xzf spec-superflow-<version>.tgz \
  -C ~/company-tools/spec-superflow-<version>
```

在 VS Code 用户设置中注册解压后的 `package` 目录：

```json
{
  "chat.pluginLocations": {
    "/absolute/path/company-tools/spec-superflow-<version>/package": true
  }
}
```

重新加载 VS Code，选择 **Spec Superflow** Agent。输入 `/workflow-init`，
从建议中选择 Plugin 提供的 `workflow-init`。CLI 尚未安装时附带上面的
`package=<absolute-tgz-path>`；版本已经匹配时不会重复安装。

## 更新

1. 校验新离线目录的 `SHA256SUMS`。
2. 用新 tgz 执行 `npm install -g`。
3. 解压到新的版本目录。
4. 将 `chat.pluginLocations` 改为新目录并重新加载 VS Code。
5. 运行 `/workflow-init package=<absolute-tgz-path>`、`ssf --version` 和 `ssf doctor`。
6. 验证完成后再删除旧版本目录，保留旧 tgz 作为回退包。

## 验收

- Plugin 页面显示目标版本。
- `/workflow-init` 返回 `READY`。
- `ssf --version` 与 Plugin 版本一致。
- `ssf doctor` 全部通过。
- 空白业务仓库中能选择 Spec Superflow Agent、发现 Skills 和 Plugin MCP。
