# agy-my-setup

다른 데스크탑에서도 동일한 Antigravity 응답 스타일(에디토리얼 이미지 + 인터랙티브 UI + 장문형 답변)과 외부 하네스 서브에이전트(`ext-claude`, `ext-codex`, `ext-dsh`)를 설치하고, **PC마다 원하는 조합·가중치·모델·effort를 자유롭게 커스텀**할 수 있는 통합 플러그인입니다.

## 새 데스크탑에서 설치 및 커스텀 세팅

### 1. 플러그인 설치
```bash
agy plugin install https://github.com/alzoqm/agy-my-setup
```

### 2. 원하는 대로 커스텀 구성 (`configure.ps1`)

#### A. 대화형 마법사로 하나씩 고르기
```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.gemini\config\plugins\agy-my-setup\configure.ps1"
```
- 에디토리얼 스타일 ON/OFF
- 사용할 하네스 선택 (`dsh`, `claude`, `codex` 각각 ON/OFF)
- 주력 하네스 및 할당 가중치 지정 (예: `claude=8,codex=2`)
- 각 하네스별 **일반 작업 모델:effort** / **고난도 작업 모델:effort** 지정
- 설정은 `setup.json`에 저장되어, 다음에 다시 실행하면 기존 값을 기본값으로 불러와 일부만 수정할 수 있습니다.

#### B. CLI 플래그로 한 번에 커스텀 적용 (예시)
- **예시 1) Claude Team Premium 데스크탑 (`sonnet:medium` 기본, `opus:high` 고난도, Codex 보조, DSH 미사용):**
  ```powershell
  powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.gemini\config\plugins\agy-my-setup\configure.ps1" `
    -Harnesses claude,codex `
    -Primary claude `
    -Weights "claude=8,codex=2" `
    -ClaudeNormal "sonnet:medium" `
    -ClaudeHard "opus:high"
  ```

- **예시 2) Claude 단독 + 최고 성능 위주 (`opus:high` 기본, `opus:max` 고난도, Codex/DSH 미사용):**
  ```powershell
  powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.gemini\config\plugins\agy-my-setup\configure.ps1" `
    -Harnesses claude `
    -Primary claude `
    -ClaudeNormal "opus:high" `
    -ClaudeHard "opus:max"
  ```

- **예시 3) 답변 스타일 없이 하네스만 쓰기 (`-Editorial $false`):**
  ```powershell
  powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.gemini\config\plugins\agy-my-setup\configure.ps1" `
    -Editorial $false -Harnesses claude -Primary claude
  ```

- **예시 4) JSON 파일(`-ConfigFile`)로 팀/머신 설정 불러오기:**
  ```powershell
  powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.gemini\config\plugins\agy-my-setup\configure.ps1" -ConfigFile .\my-desktop.json
  ```

### 3. 활성화
- Antigravity App의 **Customizations > Installed** (또는 CLI `/plugin`)에서 `agy-my-setup`을 켜면 방금 구성한 `mcp_config.json`, `rules/AGENTS.md`, `skills/external-subagents/SKILL.md`가 적용됩니다.
- `dsh`를 활성화한 경우에만 **DeepSeek Harness MCP Token** 입력창이 표시됩니다.
