param(
    [ValidateSet("", "dsh-primary", "claude-primary", "custom")]
    [string]$Profile = "",
    [string]$ClaudeModel = "",
    [string]$ClaudeEffort = "",
    [switch]$DisableCodex,
    [switch]$DisableEditorial,
    [string]$TargetDir = $PSScriptRoot
)

$ErrorActionPreference = "Stop"

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

if (-not $Profile) {
    Write-Host ""
    Write-Host "=== agy-my-setup Profile Configurator ===" -ForegroundColor Cyan
    Write-Host "1) dsh-primary    : DeepSeek Harness 10x primary + Claude + Codex"
    Write-Host "2) claude-primary : Claude Team Premium primary (sonnet/medium default, opus/high hard) - NO DeepSeek Harness"
    Write-Host "3) custom         : Choose each harness & Claude defaults interactively"
    $choice = Read-Host "Select profile [1/2/3] (default: 2)"
    switch ($choice) {
        "1" { $Profile = "dsh-primary" }
        "3" { $Profile = "custom" }
        default { $Profile = "claude-primary" }
    }
}

$useEditorial = -not $DisableEditorial
$useDsh = ($Profile -eq "dsh-primary")
$useClaude = $true
$useCodex = -not $DisableCodex
$ruleProfile = $Profile

if ($Profile -eq "custom") {
    $ansEd = Read-Host "Enable editorial-media (web images & editorial cards)? [Y/n]"
    $useEditorial = ($ansEd -notmatch "^[nN]$")

    $ansDsh = Read-Host "Enable ext-dsh (DeepSeek Harness Desktop)? [y/N]"
    $useDsh = ($ansDsh -match "^[yY]$")

    $ansClaude = Read-Host "Enable ext-claude (Claude Code CLI)? [Y/n]"
    $useClaude = ($ansClaude -notmatch "^[nN]$")

    $ansCodex = Read-Host "Enable ext-codex (OpenAI Codex)? [Y/n]"
    $useCodex = ($ansCodex -match "^[yY]$")

    if ($useClaude) {
        if (-not $ClaudeModel) {
            $m = Read-Host "Default Claude model (sonnet / opus / haiku, blank = CLI default) [sonnet]"
            $ClaudeModel = if ([string]::IsNullOrWhiteSpace($m)) { "sonnet" } else { $m.Trim() }
        }
        if (-not $ClaudeEffort) {
            $e = Read-Host "Default Claude effort (low / medium / high / xhigh / max) [medium]"
            $ClaudeEffort = if ([string]::IsNullOrWhiteSpace($e)) { "medium" } else { $e.Trim() }
        }
    }

    if ($useDsh) {
        $ansPrimary = Read-Host "Primary harness? [1] DeepSeek Harness  [2] Claude Code (default: 2)"
        $ruleProfile = if ($ansPrimary -eq "1") { "dsh-primary" } else { "claude-primary" }
    } else {
        $ruleProfile = "claude-primary"
    }
} elseif ($Profile -eq "claude-primary") {
    if (-not $ClaudeModel) { $ClaudeModel = "sonnet" }
    if (-not $ClaudeEffort) { $ClaudeEffort = "medium" }
    if (-not $PSBoundParameters.ContainsKey("DisableCodex") -and -not $Profile) {
        $ansCodex = Read-Host "Include ext-codex (OpenAI Codex) as optional fallback? [Y/n]"
        $useCodex = ($ansCodex -notmatch "^[nN]$")
    }
}

# Build mcp_config.json
$servers = [ordered]@{}

if ($useEditorial) {
    $servers["editorial-media"] = [ordered]@{
        command = "python"
        args = @("-X", "utf8", "`${PLUGIN_ROOT}/scripts/editorial_media_server.py")
    }
}

if ($useClaude) {
    $claudeCfg = [ordered]@{
        command = "python"
        args = @("-X", "utf8", "`${PLUGIN_ROOT}/scripts/claude_workers_server.py")
    }
    $claudeEnv = [ordered]@{}
    if ($ClaudeModel) { $claudeEnv["CLAUDE_WORKER_MODEL"] = $ClaudeModel }
    if ($ClaudeEffort) { $claudeEnv["CLAUDE_WORKER_EFFORT"] = $ClaudeEffort }
    if ($claudeEnv.Count -gt 0) {
        $claudeCfg["env"] = $claudeEnv
    }
    $servers["ext-claude"] = $claudeCfg
}

if ($useCodex) {
    $servers["ext-codex"] = [ordered]@{
        command = "python"
        args = @("-X", "utf8", "`${PLUGIN_ROOT}/scripts/codex_workers_server.py")
    }
}

if ($useDsh) {
    $servers["ext-dsh"] = [ordered]@{
        command = "python"
        args = @("-X", "utf8", "`${PLUGIN_ROOT}/scripts/dsh_bridge.py")
        env = [ordered]@{
            DSH_MCP_TOKEN = "`${DSH_MCP_TOKEN}"
        }
        variables = @(
            [ordered]@{
                name = "DSH_MCP_TOKEN"
                title = "DeepSeek Harness MCP Token"
                description = "DeepSeek Harness Desktop의 MCP Bearer 토큰을 입력하세요 (로컬 서버 127.0.0.1:5642/mcp 인증용)."
            }
        )
    }
}

$mcpObj = [ordered]@{ mcpServers = $servers }
$mcpJson = $mcpObj | ConvertTo-Json -Depth 10
Write-Utf8NoBom -Path (Join-Path $TargetDir "mcp_config.json") -Content ($mcpJson + "`n")

# Build rules/AGENTS.md
$templatesDir = Join-Path $PSScriptRoot "templates"
$rulesParts = @()
if ($useEditorial) {
    $rulesParts += (Get-Content -Raw -Encoding UTF8 (Join-Path $templatesDir "rules-editorial.md")).Trim()
}
$subagentRuleFile = if ($ruleProfile -eq "dsh-primary") { "rules-dsh-primary.md" } else { "rules-claude-primary.md" }
$rulesParts += (Get-Content -Raw -Encoding UTF8 (Join-Path $templatesDir $subagentRuleFile)).Trim()

$rulesOutDir = Join-Path $TargetDir "rules"
New-Item -ItemType Directory -Force -Path $rulesOutDir | Out-Null
Write-Utf8NoBom -Path (Join-Path $rulesOutDir "AGENTS.md") -Content (($rulesParts -join "`n`n---`n`n") + "`n")

# Update skills/external-subagents/SKILL.md
$skillSrc = if ($ruleProfile -eq "dsh-primary") { "skill-dsh-primary.md" } else { "skill-claude-primary.md" }
$skillOutDir = Join-Path $TargetDir "skills\external-subagents"
New-Item -ItemType Directory -Force -Path $skillOutDir | Out-Null
Copy-Item -Force (Join-Path $templatesDir $skillSrc) (Join-Path $skillOutDir "SKILL.md")

Write-Host ""
Write-Host "Configured agy-my-setup at: $TargetDir" -ForegroundColor Green
Write-Host "  Profile        : $Profile (routing: $ruleProfile)"
Write-Host "  MCP Servers    : $($servers.Keys -join ', ')"
if ($useClaude) {
    $mShow = if ($ClaudeModel) { $ClaudeModel } else { "<CLI default>" }
    $eShow = if ($ClaudeEffort) { $ClaudeEffort } else { "<CLI default>" }
    Write-Host "  Claude Default : model=$mShow, effort=$eShow"
}
Write-Host "Restart or toggle the plugin in Antigravity Customizations to reload MCP servers." -ForegroundColor Yellow
