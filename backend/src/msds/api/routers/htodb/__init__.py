"""지식DB 조회 앱(msds.api.htodb_app) 라우터. 모두 읽기 전용이다.

health    GET  /health                       접속 확인과 적재 버전
chemicals GET  /chemicals, /chemicals/{id}[/{part}]   물질 찾기와 물질별 원본 행
codes     GET  /codes/{종류}/{code}          코드 기준정보
mapping   GET  /mapping/hazard, /mapping/{kind}/{code}   추출 코드 → HTODB 코드 번역
lookup    POST /lookup                       추출 JSON 한 건의 코드를 한 번에 번역·조회

접속 풀·버전·매핑 시트는 deps.state에 있다 (htodb_app lifespan이 채운다).
"""

from msds.api.routers.htodb import chemicals, codes, health, lookup, mapping

ROUTERS = (health.router, chemicals.router, codes.router, mapping.router, lookup.router)
