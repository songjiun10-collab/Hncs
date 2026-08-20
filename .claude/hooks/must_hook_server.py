#!/usr/bin/env python3
"""must훅 (2026-08-16): decision record 작성을 Write 툴로 자유 텍스트 JSON을
쓰는 방식이 아니라, 스키마가 강제되는 MCP 툴 호출로 대체한다.

배경: `_hook_common.require_decision_or_deny()`가 MEDIUM/HIGH/CRITICAL
전체에 decision record 필수 게이트를 걸었지만(2026-08-16, 앞선 정정),
그 게이트를 통과하는 경로 자체는 여전히 "Write 툴로
`.pending_decision_record.json`에 알아서 맞는 JSON을 쓰라"였다 - 필드
누락/타입 오류/범위 밖 confidence를 막을 방법이 그 파일을 나중에 읽는
`decision_record()`쪽 검증뿐이었다. 이 서버는 그 대신 `write_decision_record`
MCP 툴 하나를 노출하고, 파라미터 스키마(타입 힌트 + pydantic Field 제약)
자체가 잘못된 호출을 MCP 프로토콜 단에서 막는다 - 스키마를 어긴 호출은
서버 코드에 도달하지도 못한다.

Write 툴로 이 sentinel 파일을 직접 쓰는 경로는
`protect_decision_record_bypass.py`가 별도로 막는다 - 이 MCP 툴이
유일한 통로가 되도록. 파일 포맷/읽기 쪽(`decision_record()`)은 전혀
바뀌지 않는다 - 이 서버도 결국 `_hook_common.write_decision_record()`를
그대로 호출해서 쓴다(포맷 단일 소스 유지, 검증 로직 중복 없음).

`.mcp.json`에 stdio 서버로 등록. 실행: `python3 must_hook_server.py`."""
from typing import Annotated, Optional

from pydantic import Field

from _hook_common import write_decision_record

from mcp.server.mcpserver import MCPServer

app = MCPServer("must_hook")


@app.tool(name="write_decision_record")
def _write_decision_record_tool(
    rule: Annotated[str, Field(min_length=1, description=(
        "가드 훅 이름, 예: protect_never_touch (require_decision_or_deny의 "
        "hook_name과 정확히 일치해야 매칭됨)"))],
    severity: Annotated[str, Field(
        pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$",
        description="자기평가 심각도 - 가드의 고정 SEVERITY와 다를 수 있음(그 차이가 eval 대상)")],
    confidence: Annotated[float, Field(ge=0.0, le=1.0, description="이 판단에 대한 확신도")],
    reason: Annotated[str, Field(min_length=1, description="판단 근거")],
    expected_risk: Annotated[str, Field(min_length=1, description="예상되는 위험")],
    target: Annotated[Optional[str], Field(
        default=None, description="가드 훅과 동일한 target 문자열(파일/브랜치/명령어). "
        "decision_id가 없으면 필수")] = None,
    decision_id: Annotated[Optional[str], Field(
        default=None, description="target이 자연스럽지 않은 가드용 슬러그. "
        "target이 없으면 필수")] = None,
) -> str:
    """가드된 액션 직전에, 그 액션이 걸릴 것으로 예상되는 규칙에 대해
    decision record를 기록한다. 다음 매칭되는 가드 호출이 이 기록을
    소비한다(10분 이내, rule+target 또는 rule+decision_id 일치)."""
    write_decision_record(
        rule, severity, confidence, reason, expected_risk,
        target=target, decision_id=decision_id,
    )
    return f"decision record written: rule={rule} target={target or decision_id}"


if __name__ == "__main__":
    app.run(transport="stdio")
