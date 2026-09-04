"""`.claude/hooks/protect_never_touch.py`의 Bash 경로 커버리지 테스트.

이번 세션 코드 리뷰가 발견한 구멍: 이 훅은 원래 Edit|Write|MultiEdit만
매칭해서, `sed -i`/`tee`/리다이렉션/`python3 -c "open(...).write(...)"`
같은 Bash 경유 쓰기는 전혀 안 걸렸다(CLAUDE.md의 "Mechanically enforced
(no bypass)" 문구가 그래서 부정확했음). `bash_write_target()`은 그
구멍을 메우는 함수 - Edit/Write 경로와 달리 파일 단위(함수 단위 아님)
커버리지라는 점은 모듈 docstring에 명시돼 있다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".claude", "hooks"))
import protect_never_touch as hook  # noqa: E402


class TestBashWriteTarget(unittest.TestCase):
    def test_sed_inplace_on_brand_file_caught(self):
        self.assertEqual(
            hook.bash_write_target("sed -i 's/x/y/' brands/hasselblad.py"),
            "brands/hasselblad.py")

    def test_redirect_into_brand_file_caught(self):
        self.assertEqual(
            hook.bash_write_target("echo bad >> brands/hasselblad.py"),
            "brands/hasselblad.py")

    def test_cp_with_brand_file_as_destination_caught(self):
        self.assertEqual(
            hook.bash_write_target("cp /tmp/x.py brands/hasselblad.py"),
            "brands/hasselblad.py")

    def test_python_open_write_mode_on_brand_file_caught(self):
        cmd = "python3 -c \"open('brands/hasselblad.py', 'w').write(x)\""
        self.assertEqual(hook.bash_write_target(cmd), "brands/hasselblad.py")

    def test_redirect_into_profile_dcp_caught(self):
        cmd = "printf x > hybrid_engine/assets/profiles/hasselblad_x2dii_chart.dcp"
        self.assertEqual(
            hook.bash_write_target(cmd),
            "hybrid_engine/assets/profiles/hasselblad_x2dii_chart.dcp")

    def test_cp_with_brand_file_as_source_only_not_flagged(self):
        """protected 파일을 참고용으로 읽어서 다른 곳에 복사하는 건 그
        파일 자체를 수정하는 게 아니다 - source 위치는 걸면 안 됨."""
        self.assertIsNone(
            hook.bash_write_target("cp brands/hasselblad.py /tmp/ref.py"))

    def test_cat_brand_file_not_flagged(self):
        self.assertIsNone(hook.bash_write_target("cat brands/hasselblad.py"))

    def test_git_diff_brand_file_not_flagged(self):
        self.assertIsNone(hook.bash_write_target("git diff brands/hasselblad.py"))

    def test_pytest_with_unrelated_redirect_target_not_flagged(self):
        cmd = "pytest brands/hasselblad.py -v > /tmp/log.txt"
        self.assertIsNone(hook.bash_write_target(cmd))

    def test_sed_on_unrelated_file_not_flagged(self):
        self.assertIsNone(hook.bash_write_target("sed -i 's/x/y/' tools/foo.py"))

    def test_heredoc_prose_mentioning_redirect_not_flagged(self):
        """이 훅 자체를 처음 만들 때 실제로 겪은 자기참조적 false
        positive: 이 시나리오를 설명하는 커밋 메시지 heredoc이 훅을
        스스로 걸리게 만들었었다."""
        cmd = ('git commit -m "$(cat <<XEOF\n'
               'explains that echo x >> brands/hasselblad.py would be bad\n'
               'XEOF\n)"')
        self.assertIsNone(hook.bash_write_target(cmd))

    def test_no_protected_path_mentioned_not_flagged(self):
        self.assertIsNone(hook.bash_write_target("echo hi >> /tmp/scratch.txt"))

    def test_python_heredoc_write_still_caught(self):
        """2026-08-20 정정 (README 2차 라운드 #1, 실증): heredoc 본문을
        무조건 지우던 게, python3 - <<'PY' ... PY로 넘겨져서 실제
        실행되는 open(...).write(...) 코드까지 놓쳤다 - 실제로 파일에
        쓰기가 일어남에도 이 훅의 Bash 커버리지를 완전히 우회했었다."""
        cmd = 'python3 - <<\'PY\'\nopen("brands/hasselblad.py","w").write("x")\nPY'
        self.assertEqual(hook.bash_write_target(cmd), "brands/hasselblad.py")

    def test_adjacent_literal_concat_still_caught(self):
        """2026-08-20 정정 (README 2차 라운드 #2, 실증): Python이 런타임에
        이어붙이는 인접 문자열 리터럴(open('brand''s/x.py','w'))이 단일
        따옴표쌍 가정 정규식을 피해갔다."""
        cmd = "python3 -c \"open('brand''s/hasselblad.py','w').write('x')\""
        self.assertIsNotNone(hook.bash_write_target(cmd))

    def test_variable_indirection_still_caught(self):
        """2026-08-20 정정 (README 2차 라운드 #2, 실증): open() 호출부에
        리터럴이 아예 없는 변수 간접 참조가 놓쳤다."""
        cmd = "python3 -c \"p='brands/hasselblad.py'; open(p,'w').write('x')\""
        self.assertIsNotNone(hook.bash_write_target(cmd))

    def test_variable_indirection_to_unrelated_file_not_flagged(self):
        cmd = "python3 -c \"p='tools/scratch.py'; open(p,'w').write('x')\""
        self.assertIsNone(hook.bash_write_target(cmd))

    def test_multihop_variable_indirection_still_caught(self):
        """2026-08-20 정정 (사용자 지시): 단일 홉만 따라가던 걸 다단계로
        확장 - p='brands/x.py'; q=p; open(q,'w') 같은 체인."""
        cmd = "python3 -c \"p='brands/hasselblad.py'; q=p; open(q,'w').write('x')\""
        self.assertIsNotNone(hook.bash_write_target(cmd))

    def test_multihop_variable_indirection_to_unrelated_file_not_flagged(self):
        cmd = "python3 -c \"p='tools/scratch.py'; q=p; open(q,'w').write('x')\""
        self.assertIsNone(hook.bash_write_target(cmd))

    def test_hop_limit_exceeded_gives_up_safely(self):
        """6홉 체인(_MAX_VAR_HOPS=5 초과)은 이 국소 패치의 문서화된
        한계 - 무한 재귀는 아니지만(hops 카운터로 종료) 값도 못 찾음."""
        chain = "; ".join(f"v{i}=v{i-1}" for i in range(1, 7))
        cmd = f"python3 -c \"v0='brands/hasselblad.py'; {chain}; open(v6,'w').write('x')\""
        self.assertIsNone(hook.bash_write_target(cmd))


class TestMainEndToEnd(unittest.TestCase):
    """main()의 tool_name 라우팅(Bash 분기 vs 기존 Edit/Write/MultiEdit
    분기)이 실제로 올바르게 연결됐는지 subprocess로 확인."""

    def setUp(self):
        # Redirect violations logging to a throwaway file - otherwise every
        # test run appends synthetic denials to the real, git-tracked
        # .claude/hooks/violations_log.jsonl.
        self._log_dir = tempfile.mkdtemp()
        self._env = dict(os.environ, HNCS_HOOK_VIOLATIONS_LOG=os.path.join(
            self._log_dir, "test_violations_log.jsonl"))

    def tearDown(self):
        shutil.rmtree(self._log_dir, ignore_errors=True)

    def _run_hook(self, tool_name, tool_input, agent_id=None):
        payload = {"tool_name": tool_name, "tool_input": tool_input}
        if agent_id:
            payload["agent_id"] = agent_id
            payload["agent_type"] = "general-purpose"
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=json.dumps(payload), env=self._env,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_bash_write_to_brand_file_denied(self):
        decision = self._run_hook(
            "Bash", {"command": "sed -i 's/x/y/' brands/hasselblad.py"})
        self.assertEqual(decision, "deny")

    def test_bash_unrelated_command_allowed(self):
        decision = self._run_hook("Bash", {"command": "git status"})
        self.assertEqual(decision, "allow")

    def test_non_matching_tool_allowed(self):
        decision = self._run_hook("Read", {"file_path": "brands/hasselblad.py"})
        self.assertEqual(decision, "allow")

    def test_subagent_bash_write_denied_even_with_valid_override(self):
        """CRITICAL 등급: 서브에이전트발 호출은 override조차 안 받는다
        (2026-08-15) - bash 주석은 서브에이전트 스스로도 쓸 수 있어서."""
        cmd = ("sed -i 's/x/y/' brands/hasselblad.py"
               "  # HNCS-OVERRIDE: protect_never_touch: 사유")
        decision = self._run_hook(
            "Bash", {"command": cmd}, agent_id="agt_1")
        self.assertEqual(decision, "deny")


if __name__ == "__main__":
    unittest.main()
