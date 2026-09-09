"""`.codex/hooks.json`이 특정 머신에만 통하는 절대경로를 안 들고 있는지
회귀 검증.

2026-09-07까지 이 파일의 모든 `command`가 `/Users/songjiun/Hncs/...`로
하드코딩돼 있었다 - 다른 경로에 클론하거나 다른 컴퓨터에서 열면 CRITICAL
안전 훅(`protect_never_touch` 등) 전부가 조용히 실행 실패한다(파일 없음
에러가 나긴 하지만, hook 자체가 안 걸리는 건 "덜 위험해 보이지만 실은 더
위험한" 실패 모드다). `.claude/settings.json`이 이미 쓰는 저장소-상대경로
패턴으로 맞췄다 - `.codex/hooks/*.py`는 그 파일들의 심링크라
`os.getcwd()` 기준 경로 해석이 Claude 쪽과 동일하게 작동한다(레포
합치기 커밋 "AGENTS.md/훅 미러를 심링크로 통일"의 전제이기도 하다)."""
import json
import os
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HOOKS_JSON = os.path.join(_REPO_ROOT, ".codex", "hooks.json")


def _all_commands(config):
    for event_entries in config["hooks"].values():
        for entry in event_entries:
            for hook in entry["hooks"]:
                yield hook["command"]


class TestCodexHooksJsonPortability(unittest.TestCase):
    def setUp(self):
        if not os.path.exists(_HOOKS_JSON):
            self.skipTest(".codex/hooks.json 없음")
        with open(_HOOKS_JSON, encoding="utf-8") as f:
            self.config = json.load(f)

    def test_no_command_hardcodes_an_absolute_repo_path(self):
        commands = list(_all_commands(self.config))
        self.assertGreater(len(commands), 0, "hooks.json에 command가 하나도 없음")
        for cmd in commands:
            with self.subTest(command=cmd):
                self.assertNotIn(_REPO_ROOT, cmd,
                                 f"저장소 절대경로가 하드코딩돼 있음: {cmd}")
                # 다른 절대경로(/Users/..., /home/... 등)도 전부 막는다 -
                # "이 저장소 경로만 아니면 됨"이 아니라 애초에 특정 머신
                # 경로에 묶이면 안 된다.
                self.assertFalse(os.path.isabs(cmd.strip("'\"").split(" ", 1)[-1]
                                               if cmd.startswith("python3 ")
                                               else cmd.strip("'\"")),
                                 f"절대경로로 보이는 command: {cmd}")

    def test_referenced_hook_scripts_exist_relative_to_repo_root(self):
        """command가 참조하는 .codex/hooks/*.py·*.sh가 저장소 루트 기준
        상대경로로 실제 존재하는지 - 경로 형식만 맞고 대상이 없는 것도
        같은 종류의 실패다."""
        for cmd in _all_commands(self.config):
            rel = cmd.strip("'\"")
            if rel.startswith("python3 "):
                rel = rel[len("python3 "):].strip("'\"")
            with self.subTest(command=cmd):
                self.assertTrue(
                    os.path.exists(os.path.join(_REPO_ROOT, rel)),
                    f"저장소 루트 기준 경로에 파일이 없음: {rel}")


if __name__ == "__main__":
    unittest.main()
