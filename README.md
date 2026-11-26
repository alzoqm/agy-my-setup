# agy-my-setup

다른 데스크탑에서도 동일한 Antigravity 응답 스타일(에디토리얼 이미지 + 인터랙티브 UI + 장문형 답변)과 외부 하네스 서브에이전트(`ext-claude`, `ext-codex`, `ext-dsh`)를 한 줄 명령어로 적용하기 위한 통합 플러그인입니다.

## 새 데스크탑에서 설치하기

### 1. 사전 준비
- Python 3.x (`python` 명령어가 PATH에 등록되어 있어야 함)
- 사용할 외부 하네스 설치 및 로그인:
  - **Claude Code**: `claude` CLI 설치 및 로그인
  - **OpenAI Codex**: Codex Desktop 앱 설치 및 로그인
  - **DeepSeek Harness Desktop**: 앱 설치 및 로그인 (MCP Bearer 토큰 확인)

### 2. 한 줄 설치
```bash
agy plugin install https://github.com/alzoqm/agy-my-setup
```

### 3. 토큰 입력 및 활성화
- `variables`(`DSH_MCP_TOKEN`)가 선언되어 있으므로, 설치 후 Antigravity App의 **Customizations > Installed** 또는 CLI `/plugin`에서 이 플러그인을 켤 때 **DeepSeek Harness MCP Token** 입력창이 나타납니다.
- 해당 PC의 토큰을 입력하면 즉시 모든 규칙, 스킬, MCP 서버가 활성화됩니다.
