# Multi-Model Coding Orchestrator Gateway v0.6.0

Kimi K3를 메인 오케스트레이터로 사용하고, DeepSeek V4와 GLM-5.2를 독립 서브에이전트로 병렬 호출하는 로컬 개발 게이트웨이입니다. 거대한 모델 가중치를 내려받지 않으며, 모든 API 모델도 **공식 Kimi Code의 ACP 코드 에이전트 하네스** 안에서 파일 탐색·MCP·테스트·승인 흐름을 공유합니다.

## 최종 권장 구조

```text
Minis / Codex / OpenAI client / MCP client
                    │
                    ▼
Multi-Model Orchestrator Gateway
  ├─ 역할 기반 라우팅·병렬 합의
  ├─ 공급자 한도 감지·서킷 브레이커
  ├─ 작업공간 제한·승인·감사 로그
  └─ 선택적 개인 웹 자문 대체
                    │ ACP/stdio
                    ▼
Official Kimi Code coding-agent runtime
  ├─ Kimi K3 OAuth       : 메인 오케스트레이터·실제 수정
  ├─ K3 DS2API 호환명    : `kimi-k3` MCP/OpenAI 요청명으로 같은 OAuth 세션 호출
  ├─ NVIDIA DeepSeek V4  : 빠른 코딩·테스트·검토
  ├─ DS2API DeepSeek V4  : NVIDIA 장애 시 선택적 로컬 fallback
  ├─ NVIDIA GLM-5.2      : 아키텍처·긴 문맥·검토
  ├─ DeepSeek official   : NVIDIA 한도/장애 시 저가 대체
  └─ Z.AI official API   : GLM 대체
```

### 왜 세 모델에 동일한 Kimi Code 하네스를 쓰는가

Kimi Code는 OpenAI·Anthropic 호환 공급자와 임시 `KIMI_MODEL_*` 모델 정의를 지원합니다. 따라서 Kimi OAuth뿐 아니라 NVIDIA NIM, DeepSeek 공식 API, Z.AI API도 같은 ACP 세션·도구·승인 계층으로 실행할 수 있습니다. 각 모델용 별도 코딩 에이전트를 유지하는 것보다 업데이트와 보안 정책을 한 곳에서 관리하기 쉽습니다.

## 모델 역할과 기본 대체 순서

- **오케스트레이터:** `k3-256k → k3 → NVIDIA GLM-5.2 → NVIDIA DeepSeek V4 Pro`
- **코더/테스트:** `K3-256K → Kimi K3 API/self-hosted → NVIDIA DeepSeek V4 Flash → DS2API DeepSeek V4 Flash → DeepSeek 공식 → NVIDIA GLM-5.2`
- **아키텍트/긴 문맥:** `NVIDIA GLM-5.2 → K3 → NVIDIA DeepSeek V4 Pro → Z.AI 공식 API`
- **최종 검토/보안:** `NVIDIA DeepSeek V4 Pro → NVIDIA GLM-5.2 → K3 → DeepSeek 공식`
- **웹 자문:** API 경로가 모두 실패한 경우 `plan/review/research`에만 사용

NVIDIA 엔드포인트는 프로토타입·무료 우선 경로이므로 영구 가용성을 가정하지 않습니다. 429·503·용량 오류가 발생하면 공급자 서킷을 잠시 열고 다음 경로로 자동 전환합니다. DS2API의 DeepSeek fallback은 기본 비활성화이며 DeepSeek 전용입니다. K3는 별도의 `ds2api-kimi-k3` 호환 프로필을 통해 `kimi-k3`라는 OpenAI/DS2API 형식의 요청명을 제공하지만, 실제 실행은 공식 Kimi Code OAuth 세션에서 이루어집니다. K3를 DeepSeek 모델에 잘못 매핑하지 않습니다.

## 1. 전체 설치

### Linux/macOS

```bash
./scripts/bootstrap-all.sh
```

개인 웹 자문 브리지까지 설치하려면:

```bash
INSTALL_BROWSER_FALLBACK=1 ./scripts/bootstrap-all.sh
```

### Windows PowerShell

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap-all.ps1
```

브라우저 대체까지 설치:

```powershell
.\scripts\bootstrap-all.ps1 -InstallBrowserFallback
```

이미 Kimi Code가 설치되어 있다면 `scripts/setup.*`만 실행해도 됩니다.

## 2. 계정과 키 설정

`.env`를 열어 사용하는 공급자만 입력합니다.

```env
NVIDIA_API_KEY=nvapi-...
DEEPSEEK_API_KEY=
ZAI_API_KEY=
DS2API_ENABLED=false
DS2API_BASE_URL=http://127.0.0.1:5001/v1
DS2API_API_KEY=
DS2API_API_KEY_FILE=
```

Kimi OAuth는 키나 비밀번호를 `.env`에 넣지 않습니다. 공식 K3 API를
사용하는 경우에만 `KIMI_API_KEY` 또는 root-only `KIMI_API_KEY_FILE`을
설정하고 `kimi-k3-api`를 runtime refresh로 검증합니다. 자체 호스팅 K3는
`K3_SELF_HOSTED_ENABLED=true`와 `K3_SELF_HOSTED_BASE_URL`을 설정한 뒤
`moonshotai/Kimi-K3` exact model discovery가 통과해야 활성화됩니다.

DS2API의 DeepSeek 계정 비밀번호·세션은 DS2API 내부에서만 관리합니다. 게이트웨이는 `healthz`, `readyz`, `v1/models`, `v1/chat/completions` 계약만 사용합니다.

VPS 배포 템플릿은 `docker-compose.providers.yml`입니다. DS2API fork 이미지와 root-only Secret 파일을 지정한 뒤 gateway·DS2API·QA·watchdog을 private Compose network로 실행합니다.

```bash
./scripts/login.sh
```

브라우저에서 본인이 직접 Kimi OAuth 승인을 완료합니다. 아이디·비밀번호·OAuth 토큰을 다른 사람에게 전달하지 마세요.

### Kimi K3 DS2API 호환 MCP 경로

공식 Kimi 계정 로그인을 완료하면 `kimi-k3`를 Kimi Code OAuth의 `k3` 모델로
해석하는 호환 alias가 활성화됩니다. 이 alias는 외부 DS2API의 DeepSeek 계정
pool을 K3로 위장하지 않으며, K3 gateway의 OpenAI-compatible
`/v1/chat/completions`와 MCP `dispatch_subagent(model="kimi-k3")` 양쪽에서
사용할 수 있습니다.

```bash
./scripts/login-k3-ds2api.sh
./scripts/doctor.sh
```

Minis MCP 호출 예시는 다음과 같습니다.

```text
dispatch_subagent(
  task="프로젝트를 분석하고 변경 계획을 작성해줘",
  cwd="/path/to/workspace",
  role="coder",
  model="kimi-k3",
  thinking="high"
)
```

`ds2api-kimi-k3`는 요청/모델 명명 호환 계층이고, CJackHwang DS2API의
`ds2api-deepseek-v4-flash` 계정 로그인 경로와는 분리됩니다. Kimi 계정 비밀번호는
환경변수·GitHub·MCP payload에 넣지 않고 공식 OAuth 로그인 화면에서만 입력합니다.

> **K3 이용 조건:** `k3-256k`와 `k3`는 Kimi Code Moderato 이상에서 사용할 수 있습니다. `k3`의 최대 1M 컨텍스트는 Allegretto 이상에서 열립니다. 권한이 없거나 할당량이 소진되어 401이 반환되면, 게이트웨이는 새 요청에서 NVIDIA/공식 API 대체 경로로 전환합니다. 모델이나 reasoning effort를 바꿀 때는 캐시 손실을 피하도록 새 세션을 사용하세요.

## 3. 진단과 시작

```bash
./scripts/doctor.sh
./scripts/start.sh
```

Windows:

```powershell
.\scripts\doctor.ps1
.\scripts\start.ps1
```

기본 주소는 `http://127.0.0.1:8790`입니다.

```bash
curl http://127.0.0.1:8790/health \
  -H "Authorization: Bearer YOUR_LOCAL_GATEWAY_KEY"
```

현재 라우팅과 공급자 상태:

```bash
curl http://127.0.0.1:8790/api/providers -H "Authorization: Bearer YOUR_LOCAL_GATEWAY_KEY"
curl http://127.0.0.1:8790/api/routes -H "Authorization: Bearer YOUR_LOCAL_GATEWAY_KEY"
```

## 4. 메인 Kimi 오케스트레이션

```bash
curl http://127.0.0.1:8790/api/orchestrations \
  -H "Authorization: Bearer YOUR_LOCAL_GATEWAY_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "요구사항을 분석하고 서브에이전트를 활용해 구현·테스트·검토해줘",
    "cwd": "/absolute/path/to/project",
    "mode": "execute",
    "role": "orchestrator",
    "model": "k3-256k"
  }'
```

모든 Kimi 내장 서브에이전트와 멀티모델 MCP 서브에이전트를 사용할 수 있습니다. 충돌을 막기 위해 기본 정책은 **메인 Kimi 세션만 실제 파일을 수정**하고, 외부 DeepSeek·GLM 서브에이전트는 독립 분석·패치 제안·검토를 반환합니다.

## 5. 독립 서브에이전트 호출

```bash
curl http://127.0.0.1:8790/api/subagents/dispatch \
  -H "Authorization: Bearer YOUR_LOCAL_GATEWAY_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "동시성 버그와 누락된 테스트를 찾아줘",
    "cwd": "/absolute/path/to/project",
    "role": "reviewer",
    "mode": "review",
    "model": "nvidia-deepseek-v4-pro"
  }'
```

모델을 생략하면 역할별 경로가 자동 적용됩니다.

## 6. 병렬 멀티모델 합의

```bash
curl http://127.0.0.1:8790/api/subagents/consensus \
  -H "Authorization: Bearer YOUR_LOCAL_GATEWAY_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "이 변경의 설계·보안·회귀 위험을 독립적으로 검토해줘",
    "cwd": "/absolute/path/to/project",
    "roles": ["architect", "reviewer", "security"],
    "models": ["nvidia-glm-5.2", "nvidia-deepseek-v4-pro", "k3-256k"],
    "mode": "review",
    "max_parallel": 3,
    "synthesize": true
  }'
```

## 7. OpenAI 호환 연결

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8790/v1",
    api_key="YOUR_LOCAL_GATEWAY_KEY",
)

response = client.chat.completions.create(
    model="multi-agent-orchestrator",
    messages=[{"role": "user", "content": "저장소를 분석하고 개선안을 제시해줘"}],
    extra_body={
        "metadata": {
            "cwd": "/absolute/path/to/project",
            "mode": "plan",
            "role": "orchestrator",
            "preferred_models": ["k3-256k", "nvidia-glm-5.2"]
        }
    },
)
print(response.choices[0].message.content)
```

사용 가능한 모델 별칭은 `GET /v1/models`에서 확인합니다.

## 8. Minis와 MCP

- `config/minis/provider.example.json`: Minis 공급자 템플릿
- `config/mcp/client-config.example.json`: 게이트웨이를 MCP 서버로 연결하는 템플릿
- `config/provider-profiles.example.json`: 공급자 정의 전체 예제
- `config/routes.example.json`: 역할별 대체 순서

MCP 도구:

- `dispatch_subagent`
- `multi_model_consensus`
- `provider_status`
- `provider_catalog`
- `provider_health`
- `provider_refresh`
- `provider_route`

메인 Kimi 오케스트레이터에는 이 MCP 서버가 자동 전달되어, 작업 중 DeepSeek·GLM·Kimi 독립 검토자를 호출할 수 있습니다.

## 9. 승인 정책

| 모드 | 용도 | 파일 변경·명령 |
|---|---|---|
| `plan` | 조사·계획 | 차단 |
| `review` | 검토·테스트 설계 | 변경 차단, 일부 테스트 승인 |
| `execute` | 실제 개발 | 메인 세션에서 승인 필요 |
| `yolo` | 완전 자율 | 기본 비활성, 격리 환경에서만 |

승인 조회·처리:

```bash
curl http://127.0.0.1:8790/api/approvals -H "Authorization: Bearer YOUR_LOCAL_GATEWAY_KEY"

curl -X POST http://127.0.0.1:8790/api/approvals/APPROVAL_ID \
  -H "Authorization: Bearer YOUR_LOCAL_GATEWAY_KEY" \
  -H "Content-Type: application/json" \
  -d '{"approve": true, "always": false}'
```

## 10. API 한도 시 웹 대화 병행

웹 자동화는 **최후 자문 대체**입니다. 모델 API처럼 안정적인 계약이 아니며, 로컬 파일·셸·MCP를 직접 실행하지 않습니다.

```bash
./scripts/setup-browser.sh
./scripts/browser-login.sh deepseek
./scripts/browser-login.sh glm
./scripts/browser-start.sh
```

각 로그인 창에서 사용자가 직접 로그인합니다. 비밀번호·쿠키를 코드로 추출하지 않습니다. 이후 `.env`에서 다음을 켭니다.

```env
ENABLE_WEB_ADVISORY_FALLBACK=true
```

제한:

- `plan`, `review`, `researcher` 역할만 허용
- CAPTCHA·사용량 제한·계정 제한 우회 없음
- 다계정 회전 없음
- 사이트 DOM 변경 시 `config/browser-profiles.json` 선택자 수정 필요
- 공개 서버나 상업적 프록시로 운영하지 않음

## 11. 운영 원칙

- 게이트웨이와 브라우저 브리지는 `127.0.0.1`에만 바인딩합니다.
- 원격 Minis에는 SSH 터널로 전달합니다.
- `.env`, `data/`, Kimi Code 홈, 브라우저 프로필, 감사 로그를 Git에 올리지 않습니다.
- 장시간 자율 작업과 `yolo`는 프로젝트 전용 Docker/VM에서만 사용합니다.
- 한 세션의 작업공간·공급자·추론 강도는 고정되며 변경 시 새 세션을 생성합니다.

자세한 내용:

- `docs/ARCHITECTURE.md`
- `docs/PROVIDER_STRATEGY.md`
- `docs/OPERATIONS.md`
- `docs/VALIDATION.md`
- `SECURITY.md`


## Orchestrator agent profiles

Project-scoped Kimi Code agents live under `.agents/agents/`. Start the command agent with:

```bash
kimi --agent k3-orchestrator
```

The command agent uses built-in Kimi subagents and the local MCP gateway to run DeepSeek/GLM architecture, security, testing and adversarial reviews concurrently. Gateway policy remains the final enforcement layer.

## Dependency baseline

The production baseline uses stable `agent-client-protocol` 0.11.x and MCP Python SDK 1.x. MCP 2.x remains a pre-release line and is not required.
