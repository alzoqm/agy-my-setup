param(
    [string]$ConfigFile = "",
    [string]$Editorial = "",             # true | false (or 1 | 0)
    [string[]]$Harnesses = @(),          # e.g. @("claude","codex") or "claude,codex"
    [string]$Primary = "",               # dsh | claude | codex | none
    [string]$Weights = "",               # e.g. "claude=8,codex=2" or "dsh=10,claude=2,codex=1"
    [string]$ClaudeNormal = "",          # model:effort, e.g. "sonnet:medium"
    [string]$ClaudeHard = "",            # model:effort, e.g. "opus:high"
    [string]$CodexNormal = "",           # model:effort, e.g. "gpt-6.2-sol:medium"
    [string]$CodexHard = "",             # model:effort, e.g. "gpt-6.2-sol:high"
    [string]$CodexAsset = "",            # model:effort, e.g. "gpt-6-luna:medium"
    [string]$DshNormal = "",             # model:effort, e.g. "muse-spark-1.3-contributor:medium"
    [string]$DshHard = "",               # model:effort, e.g. "deepseek-v4.1-flash:high"
    [switch]$Interactive,
    [string]$TargetDir = $PSScriptRoot
)

$ErrorActionPreference = "Stop"

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Split-Pair {
    param([string]$Spec, [string]$DefaultModel, [string]$DefaultEffort)
    if ([string]::IsNullOrWhiteSpace($Spec)) {
        return @{ model = $DefaultModel; effort = $DefaultEffort }
    }
    $parts = $Spec.Split(":", 2)
    $m = if ($parts[0].Trim()) { $parts[0].Trim() } else { $DefaultModel }
    $e = if ($parts.Count -gt 1 -and $parts[1].Trim()) { $parts[1].Trim() } else { $DefaultEffort }
    return @{ model = $m; effort = $e }
}

function Read-Default {
    param([string]$Prompt, [string]$Default)
    $ans = Read-Host "$Prompt [$Default]"
    if ([string]::IsNullOrWhiteSpace($ans)) { return $Default }
    return $ans.Trim()
}

function Read-Bool {
    param([string]$Prompt, [bool]$Default)
    $hint = if ($Default) { "Y/n" } else { "y/N" }
    $ans = Read-Host "$Prompt [$hint]"
    if ([string]::IsNullOrWhiteSpace($ans)) { return $Default }
    return ($ans -match "^[yY]")
}

# 1. Base defaults (or load from setup.json / -ConfigFile)
$cfg = [ordered]@{
    editorial = $true
    harnesses = [ordered]@{
        dsh    = $true
        claude = $true
        codex  = $true
    }
    primary = "dsh"
    weights = [ordered]@{
        dsh    = 10
        claude = 2
        codex  = 1
    }
    models = [ordered]@{
        dsh    = [ordered]@{ normal = "muse-spark-1.3-contributor:medium"; hard = "deepseek-v4.1-flash:high" }
        claude = [ordered]@{ normal = "sonnet:medium"; hard = "opus:high" }
        codex  = [ordered]@{ normal = "gpt-6.2-sol:medium"; hard = "gpt-6.2-sol:high"; asset = "gpt-6-luna:medium" }
    }
}

$existingSetupPath = if ($ConfigFile) { $ConfigFile } else { Join-Path $TargetDir "setup.json" }
if (Test-Path $existingSetupPath) {
    $loaded = Get-Content -Raw -Encoding UTF8 $existingSetupPath | ConvertFrom-Json
    if ($null -ne $loaded.editorial) { $cfg.editorial = [bool]$loaded.editorial }
    if ($loaded.harnesses) {
        foreach ($k in @("dsh", "claude", "codex")) {
            if ($null -ne $loaded.harnesses.$k) { $cfg.harnesses[$k] = [bool]$loaded.harnesses.$k }
        }
    }
    if ($loaded.primary) { $cfg.primary = [string]$loaded.primary }
    if ($loaded.weights) {
        foreach ($k in @("dsh", "claude", "codex")) {
            if ($null -ne $loaded.weights.$k) { $cfg.weights[$k] = [int]$loaded.weights.$k }
        }
    }
    if ($loaded.models) {
        foreach ($h in @("dsh", "claude", "codex")) {
            if ($loaded.models.$h) {
                if ($loaded.models.$h.normal) { $cfg.models[$h].normal = [string]$loaded.models.$h.normal }
                if ($loaded.models.$h.hard)   { $cfg.models[$h].hard   = [string]$loaded.models.$h.hard }
                if ($h -eq "codex" -and $loaded.models.$h.asset) { $cfg.models[$h].asset = [string]$loaded.models.$h.asset }
            }
        }
    }
}

# 2. Check if any CLI customization flags were passed
$hasCliOverrides = (
    $Editorial -ne "" -or
    $Harnesses.Count -gt 0 -or
    $Primary -ne "" -or
    $Weights -ne "" -or
    $ClaudeNormal -ne "" -or
    $ClaudeHard -ne "" -or
    $CodexNormal -ne "" -or
    $CodexHard -ne "" -or
    $CodexAsset -ne "" -or
    $DshNormal -ne "" -or
    $DshHard -ne ""
)

if ($Interactive -or (-not $hasCliOverrides -and -not $ConfigFile)) {
    Write-Host ""
    Write-Host "=== agy-my-setup Custom Configurator ===" -ForegroundColor Cyan
    Write-Host "Press Enter to keep the [current/default] value." -ForegroundColor DarkGray
    Write-Host ""

    $cfg.editorial = Read-Bool "1) Enable Global Editorial Style & editorial-media MCP?" $cfg.editorial

    $cfg.harnesses.dsh    = Read-Bool "2) Enable ext-dsh (DeepSeek Harness Desktop)?" $cfg.harnesses.dsh
    $cfg.harnesses.claude = Read-Bool "3) Enable ext-claude (Claude Code CLI)?" $cfg.harnesses.claude
    $cfg.harnesses.codex  = Read-Bool "4) Enable ext-codex (OpenAI Codex / GPT)?" $cfg.harnesses.codex

    $enabledList = @("dsh", "claude", "codex") | Where-Object { $cfg.harnesses[$_] }
    if ($enabledList.Count -gt 0) {
        $defaultPrim = if ($enabledList -contains $cfg.primary) { $cfg.primary } else { $enabledList[0] }
        $pInput = Read-Default "5) Primary harness ($($enabledList -join ' / '))" $defaultPrim
        if ($enabledList -contains $pInput) { $cfg.primary = $pInput } else { $cfg.primary = $defaultPrim }

        if ($enabledList.Count -gt 1) {
            $wDefault = ($enabledList | ForEach-Object { "$_=$($cfg.weights[$_])" }) -join ","
            $wInput = Read-Default "6) Quota weights (e.g. claude=8,codex=2)" $wDefault
            foreach ($pair in $wInput.Split(",")) {
                $kv = $pair.Split("=", 2)
                if ($kv.Count -eq 2) {
                    $k = $kv[0].Trim().ToLower()
                    if ($cfg.weights.Contains($k)) {
                        $v = 0
                        if ([int]::TryParse($kv[1].Trim(), [ref]$v) -and $v -ge 0) {
                            $cfg.weights[$k] = $v
                        }
                    }
                }
            }
        }

        if ($cfg.harnesses.claude) {
            $cfg.models.claude.normal = Read-Default "   - Claude normal tier (model:effort)" $cfg.models.claude.normal
            $cfg.models.claude.hard   = Read-Default "   - Claude hard/architect tier (model:effort)" $cfg.models.claude.hard
        }
        if ($cfg.harnesses.codex) {
            $cfg.models.codex.normal = Read-Default "   - Codex normal tier (model:effort)" $cfg.models.codex.normal
            $cfg.models.codex.hard   = Read-Default "   - Codex hard tier (model:effort)" $cfg.models.codex.hard
            $cfg.models.codex.asset  = Read-Default "   - Codex asset tier (model:effort)" $cfg.models.codex.asset
        }
        if ($cfg.harnesses.dsh) {
            $cfg.models.dsh.normal = Read-Default "   - DSH normal tier (model:effort)" $cfg.models.dsh.normal
            $cfg.models.dsh.hard   = Read-Default "   - DSH hard tier (model:effort)" $cfg.models.dsh.hard
        }
    } else {
        $cfg.primary = "none"
    }
}

# 3. Apply explicit CLI flag overrides
if ($Editorial -ne "") {
    $edVal = $Editorial.Trim().ToLower()
    if ($edVal -in @("true", "1", "yes", "y", "on")) { $cfg.editorial = $true }
    elseif ($edVal -in @("false", "0", "no", "n", "off")) { $cfg.editorial = $false }
    else { throw "Invalid -Editorial '$Editorial'. Use true or false." }
}

if ($Harnesses.Count -gt 0) {
    $flat = ($Harnesses -join ",").Split(",") | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ }
    foreach ($k in @("dsh", "claude", "codex")) {
        $cfg.harnesses[$k] = ($flat -contains $k)
    }
}

$enabled = @("dsh", "claude", "codex") | Where-Object { $cfg.harnesses[$_] }

if ($Primary) {
    $p = $Primary.Trim().ToLower()
    if ($p -eq "none" -or ($enabled -contains $p)) {
        $cfg.primary = $p
    } else {
        throw "Invalid -Primary '$Primary'. Enabled harnesses: $($enabled -join ', ')"
    }
} elseif ($enabled.Count -eq 0) {
    $cfg.primary = "none"
} elseif (-not ($enabled -contains $cfg.primary)) {
    $cfg.primary = $enabled[0]
}

if ($Weights) {
    foreach ($pair in $Weights.Split(",")) {
        $kv = $pair.Split("=", 2)
        if ($kv.Count -eq 2) {
            $k = $kv[0].Trim().ToLower()
            if ($cfg.weights.Contains($k)) {
                $v = 0
                if ([int]::TryParse($kv[1].Trim(), [ref]$v) -and $v -ge 0) {
                    $cfg.weights[$k] = $v
                }
            }
        }
    }
}

if ($ClaudeNormal) { $cfg.models.claude.normal = $ClaudeNormal }
if ($ClaudeHard)   { $cfg.models.claude.hard   = $ClaudeHard }
if ($CodexNormal)  { $cfg.models.codex.normal  = $CodexNormal }
if ($CodexHard)    { $cfg.models.codex.hard    = $CodexHard }
if ($CodexAsset)   { $cfg.models.codex.asset   = $CodexAsset }
if ($DshNormal)    { $cfg.models.dsh.normal    = $DshNormal }
if ($DshHard)      { $cfg.models.dsh.hard      = $DshHard }

$pClaudeNorm = Split-Pair $cfg.models.claude.normal "sonnet" "medium"
$pClaudeHard = Split-Pair $cfg.models.claude.hard   "opus"   "high"
$pCodexNorm  = Split-Pair $cfg.models.codex.normal  "gpt-6.2-sol" "medium"
$pCodexHard  = Split-Pair $cfg.models.codex.hard    "gpt-6.2-sol" "high"
$pCodexAsset = Split-Pair $cfg.models.codex.asset   "gpt-6-luna"  "medium"
$pDshNorm    = Split-Pair $cfg.models.dsh.normal    "muse-spark-1.3-contributor" "medium"
$pDshHard    = Split-Pair $cfg.models.dsh.hard      "deepseek-v4.1-flash" "high"

# 4. Generate mcp_config.json
$servers = [ordered]@{}

if ($cfg.editorial) {
    $servers["editorial-media"] = [ordered]@{
        command = "python"
        args = @("-X", "utf8", "`${PLUGIN_ROOT}/scripts/editorial_media_server.py")
    }
}

if ($cfg.harnesses.claude) {
    $servers["ext-claude"] = [ordered]@{
        command = "python"
        args = @("-X", "utf8", "`${PLUGIN_ROOT}/scripts/claude_workers_server.py")
        env = [ordered]@{
            CLAUDE_WORKER_MODEL  = $pClaudeNorm.model
            CLAUDE_WORKER_EFFORT = $pClaudeNorm.effort
        }
    }
}

if ($cfg.harnesses.codex) {
    $servers["ext-codex"] = [ordered]@{
        command = "python"
        args = @("-X", "utf8", "`${PLUGIN_ROOT}/scripts/codex_workers_server.py")
        env = [ordered]@{
            CODEX_WORKER_MODEL  = $pCodexNorm.model
            CODEX_WORKER_EFFORT = $pCodexNorm.effort
        }
    }
}

if ($cfg.harnesses.dsh) {
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

$mcpJson = ([ordered]@{ mcpServers = $servers }) | ConvertTo-Json -Depth 10
Write-Utf8NoBom -Path (Join-Path $TargetDir "mcp_config.json") -Content ($mcpJson + "`n")

# 5. Generate dynamic External Subagents rule & skill sections
$subagentRule = ""
$subagentSkill = ""

if ($enabled.Count -gt 0) {
    $totalWeight = ($enabled | ForEach-Object { [Math]::Max(0, [int]$cfg.weights[$_]) } | Measure-Object -Sum).Sum
    if ($totalWeight -le 0) { $totalWeight = $enabled.Count }

    $orderedHarnesses = @($cfg.primary) + ($enabled | Where-Object { $_ -ne $cfg.primary }) | Where-Object { $enabled -contains $_ }

    $serverLines = @()
    $allocLines = @()
    $fallbackLines = @()
    $skillSections = @()

    foreach ($h in $orderedHarnesses) {
        $w = [int]$cfg.weights[$h]
        $pct = [Math]::Round(($w / $totalWeight) * 100)
        $roleTag = if ($h -eq $cfg.primary) { "**Primary Worker (~$pct%)**" } else { "Secondary/Specialist (~$pct%)" }

        if ($h -eq "dsh") {
            $serverLines += "- ``ext-dsh``: DeepSeek Harness Desktop (``session_create``, ``session_send``, ``session_poll``, ``session_result``, ``model_list``)"
            $allocLines += "- **``ext-dsh`` [$roleTag, weight=$w]**:"
            $allocLines += "  - Normal tasks (implementation, refactoring, tests, docs, 1st-pass review — no secrets): ``opencode-go/$($pDshNorm.model)`` (effort ``$($pDshNorm.effort)``)."
            $allocLines += "  - Hard/confidential tasks (algorithms, critical verification, large outputs): ``opencode-go/$($pDshHard.model)`` (effort ``$($pDshHard.effort)``)."
            $skillSections += @"
### ``ext-dsh`` ($roleTag)
- Allowed models ONLY: ``opencode-go/$($pDshNorm.model)`` (normal, no secrets) and ``opencode-go/$($pDshHard.model)`` (hard/confidential).
- Default tiers: normal=``$($pDshNorm.model)`` (``$($pDshNorm.effort)``), hard=``$($pDshHard.model)`` (``$($pDshHard.effort)``).
- Flow: ``session_create(workspacePath, provider="opencode-go", model=...)`` -> ``session_send(sessionId, prompt, wait="turn")`` -> ``session_result(sessionId)``.
"@
        }
        elseif ($h -eq "claude") {
            $serverLines += "- ``ext-claude``: Claude Code CLI (``claude_start``, ``claude_send``, ``claude_poll``, ``claude_result``, ``claude_info``) — default ``$($pClaudeNorm.model)`` (``$($pClaudeNorm.effort)``)"
            $allocLines += "- **``ext-claude`` [$roleTag, weight=$w]**:"
            $allocLines += "  - Normal/default tier: ``$($pClaudeNorm.model)`` (effort ``$($pClaudeNorm.effort)``) for feature implementation, refactoring, tests, docs, and 1st-pass review."
            $allocLines += "  - Hard/architect tier: ``$($pClaudeHard.model)`` (effort ``$($pClaudeHard.effort)``) for architecture design, multi-module root-cause debugging, and precision reviews."
            $skillSections += @"
### ``ext-claude`` ($roleTag)
- Tools: ``claude_start``, ``claude_send``, ``claude_poll``, ``claude_result``, ``claude_cancel``, ``claude_list``, ``claude_info``.
- Default tier (used when ``model``/``effort`` omitted): ``$($pClaudeNorm.model)`` (``$($pClaudeNorm.effort)``).
- Hard/architect tier (pass explicitly): ``model="$($pClaudeHard.model)", effort="$($pClaudeHard.effort)"``.
- Flow: ``claude_start(workspacePath, task, wait=true/false)`` -> ``claude_send(sessionId, task)``.
"@
        }
        elseif ($h -eq "codex") {
            $serverLines += "- ``ext-codex``: OpenAI Codex / GPT (``codex_start``, ``codex_send``, ``codex_poll``, ``codex_result``, ``codex_info``) — default ``$($pCodexNorm.model)`` (``$($pCodexNorm.effort)``)"
            $allocLines += "- **``ext-codex`` [$roleTag, weight=$w]**:"
            $allocLines += "  - Normal/default tier: ``$($pCodexNorm.model)`` (effort ``$($pCodexNorm.effort)``)."
            $allocLines += "  - Hard/sandboxed test loops: ``$($pCodexHard.model)`` (effort ``$($pCodexHard.effort)``); asset generation: ``$($pCodexAsset.model)`` (effort ``$($pCodexAsset.effort)``)."
            $skillSections += @"
### ``ext-codex`` ($roleTag)
- Tools: ``codex_start``, ``codex_send``, ``codex_poll``, ``codex_result``, ``codex_cancel``, ``codex_list``, ``codex_info``.
- Default tier: ``$($pCodexNorm.model)`` (``$($pCodexNorm.effort)``); hard tier: ``$($pCodexHard.model)`` (``$($pCodexHard.effort)``); asset tier: ``$($pCodexAsset.model)`` (``$($pCodexAsset.effort)``).
- Flow: ``codex_start(workspacePath, task, model=..., reasoningEffort=..., wait=true/false)`` -> ``codex_send(threadId, task)``.
"@
        }
    }

    $dshRestrictionBlock = ""
    if ($cfg.harnesses.dsh) {
        $dshRestrictionBlock = @"

## DeepSeek Harness (``ext-dsh``) Model Restriction
For ``ext-dsh``, ONLY use these two OpenCode models:
1. ``opencode-go`` / ``deepseek-v4.1-flash``
2. ``opencode-go`` / ``muse-spark-1.3-contributor``
"@
    }

    $fallbackChain = ($orderedHarnesses | ForEach-Object { "``ext-$_``" }) -join " -> "

    $subagentRule = @"
# External Subagents (Custom Machine Config)

Enabled external subagent MCP servers on this machine (primary: ``ext-$($cfg.primary)``):
$($serverLines -join "`n")
$dshRestrictionBlock

## Task Allocation & Model Tiers
$($allocLines -join "`n")
- **Main agent (Antigravity)**: Handle simple file reads, small localized edits, and direct shell checks yourself rather than spawning a subagent.

## Quota Exhaustion / Fallback Order
- Escalate within the active harness first (normal tier -> hard tier).
- If a harness is rate-limited or unavailable, fall back along: $fallbackChain -> Antigravity direct execution.
"@

    $subagentSkill = @"
---
name: external-subagents
description: Delegate tasks to the enabled external subagent MCP servers ($($orderedHarnesses -join ', ')) using this machine's custom model, effort, and quota routing config.
---

# External Subagents (Active Machine Config)

Primary harness: **``ext-$($cfg.primary)``** | Fallback order: $fallbackChain

$($skillSections -join "`n")
## Fallback & Escalation
1. Start normal tasks on the harness's normal tier; escalate to its hard tier on complex architecture, RCA, or failure.
2. If the primary harness is rate-limited, fall back in order: $fallbackChain -> direct Antigravity execution.
"@
}

# 6. Write rules/AGENTS.md
$templatesDir = Join-Path $PSScriptRoot "templates"
$rulesParts = @()
if ($cfg.editorial) {
    $rulesParts += (Get-Content -Raw -Encoding UTF8 (Join-Path $templatesDir "rules-editorial.md")).Trim()
}
if ($subagentRule) {
    $rulesParts += $subagentRule.Trim()
}

$rulesOutDir = Join-Path $TargetDir "rules"
New-Item -ItemType Directory -Force -Path $rulesOutDir | Out-Null
Write-Utf8NoBom -Path (Join-Path $rulesOutDir "AGENTS.md") -Content (($rulesParts -join "`n`n---`n`n") + "`n")

# 7. Write or remove skills/external-subagents/SKILL.md
$skillOutDir = Join-Path $TargetDir "skills\external-subagents"
if ($subagentSkill) {
    New-Item -ItemType Directory -Force -Path $skillOutDir | Out-Null
    Write-Utf8NoBom -Path (Join-Path $skillOutDir "SKILL.md") -Content ($subagentSkill.Trim() + "`n")
} elseif (Test-Path $skillOutDir) {
    Remove-Item -Recurse -Force $skillOutDir
}

# 8. Save setup.json for future incremental tweaks
$setupJson = $cfg | ConvertTo-Json -Depth 10
Write-Utf8NoBom -Path (Join-Path $TargetDir "setup.json") -Content ($setupJson + "`n")

Write-Host ""
Write-Host "Configured agy-my-setup at: $TargetDir" -ForegroundColor Green
Write-Host "  Editorial Style : $($cfg.editorial)"
Write-Host "  MCP Servers     : $($servers.Keys -join ', ')"
if ($enabled.Count -gt 0) {
    Write-Host "  Primary Harness : ext-$($cfg.primary)"
    if ($cfg.harnesses.claude) { Write-Host "  Claude Tiers    : normal=$($pClaudeNorm.model):$($pClaudeNorm.effort), hard=$($pClaudeHard.model):$($pClaudeHard.effort)" }
    if ($cfg.harnesses.codex)  { Write-Host "  Codex Tiers     : normal=$($pCodexNorm.model):$($pCodexNorm.effort), hard=$($pCodexHard.model):$($pCodexHard.effort), asset=$($pCodexAsset.model):$($pCodexAsset.effort)" }
    if ($cfg.harnesses.dsh)    { Write-Host "  DSH Tiers       : normal=$($pDshNorm.model):$($pDshNorm.effort), hard=$($pDshHard.model):$($pDshHard.effort)" }
}
Write-Host "  Saved Config    : $(Join-Path $TargetDir 'setup.json')"
Write-Host "Restart or toggle the plugin in Antigravity Customizations to reload." -ForegroundColor Yellow
