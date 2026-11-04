"""추출 앱(msds.api.extract_app) 라우터. 경로는 모두 /api 아래다.

health       GET  /api/health                서버 상태와 모델 태그
jobs         /api/documents[/{id}[/retry]]   문서 올리기·목록·진행 상태·다시 돌리기
pages        /api/documents/{id}/pdf, /pages/{n}/image|lines   원문 보기 (원본 PDF, 쪽 이미지, 줄 번호 붙은 쪽 글)
results      /api/documents/{id}/result, /sections/{m}/{s}      추출 결과 보기
storage      /api/documents/{id}/results/persist|stored, /handoffs, /to-judgment   PostgreSQL 결과 보관과 판정용 전달
regenerated  /api/documents/{id}/regenerated  재생성 MSDS
review       /api/documents/{id}/review[/fields|/sections] 추출값 확인(검수)

함께 쓰는 문서 찾기·산출물 위치는 deps에 있다. store·worker·pages_root는 create_app이 app.state에 넣는다.
"""

from msds.api.routers.extract import (
    health,
    jobs,
    pages,
    regenerated,
    results,
    review,
    storage,
)

ROUTERS = (
    health.router,
    jobs.router,
    pages.router,
    results.router,
    storage.router,
    regenerated.router,
    review.router,
)
