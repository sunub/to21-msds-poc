"""API 라우터. 붙는 앱(목적지)마다 하위 패키지를 하나씩 두고, 그 안은 의미 단위로 파일을 나눈다.

extract  msds.api.extract_app (추출 서비스, 포트 8020)
htodb    msds.api.htodb_app   (지식DB 조회, 읽기 전용, 포트 8010)

각 하위 패키지의 ROUTERS를 앱이 차례로 붙인다. 앱끼리 서로의 라우터·deps를 가져다 쓰지 않는다.
판정 API(msds.api.judge_app)는 혼자 띄우는 앱이기도 해서 아직 자기 파일에 있다.
"""
