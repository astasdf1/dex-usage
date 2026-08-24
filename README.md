# DEX Usage — Claude Code 플러그인

Claude Code와 Codex의 로컬 로그인 정보로 남은 사용량을 수집하고, Antigravity `agy`의 `/usage` TUI에서 5시간·주간 쿼터를 실험적으로 수집합니다. Google 계열 provider는 Antigravity 하나만 제공합니다. Node.js, npm, FlowDesk, MCP가 필요 없으며 Python 3 표준 라이브러리와 선택적 `tmux`만 사용합니다. 상태줄은 네트워크나 TUI를 호출하지 않고 캐시만 읽습니다.

## 개발/로컬 실행

저장소 루트에서 다음 명령으로 플러그인을 현재 세션에 로드합니다.

```bash
claude --plugin-dir "$PWD/plugins/dex-usage"
```

사용 가능한 명령은 `/dex-usage:usage-all`, `/dex-usage:refresh`, `/dex-usage:doctor`, `/dex-usage:setup`입니다. `setup`은 먼저 dry-run을 표시한 뒤 사용자 확인을 받아야 합니다. 기존 `statusLine`이 command 형식이면 출력 앞부분을 보존해 합성하고 설정 원본을 타임스탬프 백업한 뒤 원자적으로 기록합니다. 상태줄 명령은 marketplace의 버전별 캐시 경로를 저장하지 않고 `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/dex-usage/statusline.py`에 원자적으로 설치되는 사용자 소유의 캐시 전용 사본을 실행하므로 플러그인 업데이트나 캐시 삭제 후에도 동작합니다. 그 외 형식이나 심볼릭 링크 설정 경로이면 충돌을 보고하며 아무것도 쓰지 않습니다.

CLI 직접 실행:

```bash
plugins/dex-usage/bin/dex-usage refresh
plugins/dex-usage/bin/dex-usage doctor
plugins/dex-usage/bin/dex-usage uninstall --dry-run
plugins/dex-usage/bin/dex-usage uninstall
```

## 팀 배포

폴더를 안전하게 복사합니다(명시된 릴리스 파일만 복사하며 소스의 심볼릭 링크/특수 파일 또는 기존 대상이 있으면 중단하고 설정은 수정하지 않음).

```bash
python3 plugins/dex-usage/scripts/install-folder.py "$HOME/.local/share/dex-usage"
claude --plugin-dir "$HOME/.local/share/dex-usage"
```

단일 파일 패키지를 만들 수도 있습니다. 패키지는 같은 19개 릴리스 허용 목록만 포함하며 테스트, 설치/패키징 도구, 개발 파일, dot/editor/민감 파일은 포함하지 않습니다. tar 멤버와 gzip 헤더의 시간·소유자·이름·권한 메타데이터를 정규화하므로 동일한 내용은 빌드 시간, 소스 경로, checkout 권한과 무관하게 byte-for-byte 동일한 archive를 생성합니다.

```bash
python3 plugins/dex-usage/scripts/package.py --out dist/dex-usage-1.4.1.tar.gz
tar -xzf dist/dex-usage-1.4.1.tar.gz -C /safe/team/path
claude --plugin-dir /safe/team/path/dex-usage
```

로컬 marketplace는 `.claude-plugin/marketplace.json`에 포함되어 있습니다. 사용자가 명시적으로 추가할 때만 다음을 실행합니다.

```bash
claude plugin marketplace add /absolute/path/to/plugins/dex-usage
claude plugin install dex-usage@dex-usage-marketplace --scope user
```

GitHub marketplace로 등록한 설치본은 Claude Code의 marketplace 자동 업데이트가 켜져 있으면 `main`의 새 manifest 버전을 백그라운드에서 받습니다. 자동 업데이트는 Claude Code `/plugin`의 marketplace 설정에서 `dex-usage-marketplace`에 대해 켭니다. 즉시 반영하려면 다음 명령을 사용할 수 있습니다.

```bash
claude plugin marketplace update dex-usage-marketplace
claude plugin update dex-usage@dex-usage-marketplace --scope user
```

업데이트된 플러그인의 `SessionStart` 훅은 사용자가 `/dex-usage:setup`으로 한 번 연결한 안정 경로의 status-line 실행 파일만 원자적으로 갱신합니다. 기존 `settings.json`, 기존 status-line 합성 정보, 인증정보는 덮어쓰지 않습니다. 새 버전 적용에는 Claude Code 재시작이 필요할 수 있습니다.

Claude Code 세션 안에서는 같은 작업을 `/plugin marketplace add /absolute/path/to/plugins/dex-usage`, `/plugin install dex-usage@dex-usage-marketplace`로 실행할 수 있습니다. 팀 저장소에만 고정하려면 `--scope project`, 현재 체크아웃에만 두려면 `--scope local`을 사용합니다. 마켓플레이스 이름은 `dex-workers@dex-team`과 독립적으로 공존하도록 `dex-usage-marketplace`로 고정됩니다.

플러그인은 사용자 전역 설정을 자동 변경하지 않습니다. `SessionStart` 훅은 상태줄이 처음 렌더링되기 전에 공급자 사용량을 병렬 갱신합니다. 시작 지연은 8초의 하드 타임아웃과 내부 7초 제한으로 제한됩니다. `/dex-usage:setup`은 `agy`가 설치되어 있고 비대화형 `--help`/`models` 로그인·준비 상태 검사를 통과할 때만 Antigravity TUI 수집을 활성화합니다. 실행 파일 부재, 로그아웃 또는 검사 실패는 setup을 실패시키지 않고 비활성 상태를 기록합니다. setup은 `agy`를 설치하거나 로그인하지 않으며, 검사 출력이나 인증정보를 저장하지 않습니다. 자동 판정으로 비활성화된 설치는 재실행 시 다시 검사하지만 기존 사용자의 명시적 비활성화는 유지합니다. `DEX_USAGE_ANTIGRAVITY_TUI=0`으로도 끌 수 있습니다. 수집기는 고유 tmux 소켓과 빈 임시 작업 디렉터리에서 로컬 설치·로그인된 `agy`를 실행하고 `/usage`, 이어서 필요할 때 `/quota` 화면을 메모리에서만 파싱합니다. 원본 화면·이메일·계정 식별자·토큰·인증정보는 저장하지 않으며 파싱된 5시간/7일 퍼센트와 리셋 시각만 권한 `0600`으로 30분 캐시합니다. `tmux` 부재, 로그인 실패, 레이아웃 변경 또는 시간 초과 시 Claude를 막지 않고 `A ready quota:?`를 표시하며, 이전 정상 캐시가 있으면 `A~`로 유지합니다. `UserPromptSubmit`은 비동기로 실행되며 일반 캐시 TTL이 지난 경우에만 갱신합니다.

## 소유권과 출처

`lib/dex_usage/`는 DEX-2가 소유·업데이트하는 독립 payload입니다. 최초 어댑터는 저장소의 검증된 `scripts/flowdesk_usage_snapshot/`에서 복사했으며 이후 플러그인 사본은 DEX-2가 독립 유지합니다. 공식 구조와 훅 동작은 Anthropic Claude Code 플러그인/훅/status line 문서를 기준으로 합니다. 자세한 고지는 `NOTICE.md`를 참조하십시오.
