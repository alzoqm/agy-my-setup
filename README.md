# agy-my-setup

다른 데스크탑에서도 동일한 Antigravity 응답 스타일(에디토리얼 이미지 + 인터랙티브 UI + 장문형 답변)과 외부 하네스 서브에이전트(`ext-claude`, `ext-codex`, `ext-dsh`)를 설치하고, **PC별 환경에 맞게 주력 하네스/모델을 전환**할 수 있는 통합 플러그인입니다.

## 새 데스크탑에서 설치 및 프로파일 설정

### 1. 한 줄 설치
```bash
agy plugin install https://github.com/alzoqm/agy-my-setup
```

### 2. 데스크탑 환경에 맞게 프로파일 적용 (`configure.ps1`)
설치된 플러그인 폴더 안의 `configure.ps1`을 실행하면, 해당 PC에서 쓸 하네스만 남기고 규칙(`rules/AGENTS.md`), 스킬(`SKILL.md`), `mcp_config.json`을 자동으로 재구성합니다.

- **대화형 메뉴로 선택하기:**
  ```powershell
  powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.gemini\config\plugins\agy-my-setup\configure.ps1"
  ```

- **Claude Team Premium 데스크탑 (DeepSeek Harness 미사용, `sonnet medium` 기본 + `opus high` 고난도):**
  ```powershell
  powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.gemini\config\plugins\agy-my-setup\configure.ps1" -Profile claude-primary
  ```
  *(Codex도 안 쓰는 경우 `-DisableCodex` 추가)*

- **DeepSeek Harness 주력 데스크탑 (`ext-dsh` 10x : `ext-claude` 2x : `ext-codex` 1x):**
  ```powershell
  powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.gemini\config\plugins\agy-my-setup\configure.ps1" -Profile dsh-primary
  ```

- **커스텀 모델/effort 지정 예시:**
  ```powershell
  powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.gemini\config\plugins\agy-my-setup\configure.ps1" -Profile claude-primary -ClaudeModel opus -ClaudeEffort high -DisableCodex
  ```

### 3. 활성화
- Antigravity App의 **Customizations > Installed** (또는 CLI `/plugin`)에서 `agy-my-setup`을 켜면 설정된 프로파일이 즉시 적용됩니다.
- `dsh-primary` 프로파일을 선택한 경우에만 **DeepSeek Harness MCP Token** 입력창이 표시됩니다.
