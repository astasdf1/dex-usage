# DEX Usage — Claude Code 플러그인

Claude Code, Codex, Gemini의 로컬 로그인 정보를 이용해 남은 사용량을 수집하고 캐시에 저장합니다. Node.js, npm, FlowDesk, MCP가 필요 없으며 Python 3 표준 라이브러리만 사용합니다. 상태줄은 네트워크를 호출하지 않고 캐시만 읽습니다.

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
python3 plugins/dex-usage/scripts/package.py --out dist/dex-usage-1.1.0.tar.gz
tar -xzf dist/dex-usage-1.1.0.tar.gz -C /safe/team/path
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

플러그인은 사용자 전역 설정을 자동 변경하지 않습니다. `SessionStart` 훅은 상태줄이 처음 렌더링되기 전에 공급자 사용량을 갱신합니다. 시작 지연은 8초의 하드 타임아웃과 공급자별 2초 타임아웃으로 제한됩니다. 하드 타임아웃이나 일시적인 rate-limit/API 실패가 발생하면 마지막 정상값을 유지하며 공급자 글자 뒤의 `~`로 stale 상태를 표시합니다. `UserPromptSubmit`은 기존처럼 비동기로 실행되고 5분 TTL이 지난 경우에만 갱신합니다. Claude/Codex/Gemini가 없거나 로그아웃 상태이고 이전 정상값도 없으면 해당 공급자를 `unknown`으로 표시하며 전체 명령은 성공합니다.

## 소유권과 출처

`lib/dex_usage/`는 DEX-2가 소유·업데이트하는 독립 payload입니다. 최초 어댑터는 저장소의 검증된 `scripts/flowdesk_usage_snapshot/`에서 복사했으며 이후 플러그인 사본은 DEX-2가 독립 유지합니다. 공식 구조와 훅 동작은 Anthropic Claude Code 플러그인/훅/status line 문서를 기준으로 합니다. 자세한 고지는 `NOTICE.md`를 참조하십시오.
