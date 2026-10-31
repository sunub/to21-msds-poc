"""작업 화면의 표시 이름 (역할 B, 개발 전용, ADR-027).

파일이나 서버를 읽지 않는 순수 함수다. 실행 정보가 이름보다 우선하며,
모르는 조건은 그대로 남겨 표시 이름에서 실행 조건을 잃지 않는다.
"""
import re
from datetime import datetime
from math import isfinite
from pathlib import PurePosixPath

from msds.evaluate.score import WEIGHTS    # src 경로는 b_app이 먼저 부르는 _common이 등록한다


# 첫 HTML에 넣는다. 이후 API를 못 받아도 오류의 사실과 복구 방법은 읽을 수 있다.
_LEGACY_POLISH_TEXT: dict = {
    "load_error": {"message": "자료를 불러오지 못했습니다.",
                   "fix": "앱을 켠 터미널의 오류를 보고 화면을 다시 여세요."},
    "request_error": {"message": "요청을 완료하지 못했습니다.",
                      "fix": "원문 보기의 안내에 따라 입력과 연결 상태를 확인한 뒤 다시 시도하세요."},
    "cell_labels": {"c-none": "기록 없음", "c-ok": "성공", "c-re": "재추출 성공",
                    "c-limit": "한도 후 성공", "c-fail": "실패"},
    "silver_labels": {"same": "실버와 같음", "diff": "실버와 다름",
                      "only": "실버에만 있음", "missing": "실버에 없음"},
    "row_change": {"up": "정답에 가까워짐", "down": "정답에서 멀어짐", "same": "차이 유지"},
    "changed": "조건 다름",
    "no_pages": "쪽 자료가 없습니다. 다른 문서를 고르거나 입력 폴더를 확인하세요.",
    "no_lines": "이 쪽에는 줄 글자가 없습니다.",
    "no_models": "등록된 모델이 없습니다.",
    "time_over": "목표 초과",
    "loading": "불러오는 중…",
}


# 승인 COPY.md의 공통 화면 글. 계산과 기존 문구 함수는 유지한다.
UI_TEXT: dict = {'nav': {'app_name': '화학 안전문서 AI 결과 검토',
         'purpose': 'AI가 안전 문서에서 뽑은 값을 정답과 비교합니다.',
         'open_guide': '처음 사용 안내 열기',
         'open_jobs': '진행 중 작업 보기',
         'recent': '최근 결과',
         'source': '원문과 맞춰 보기',
         'retest': '다시 시험',
         'compare': '두 결과 비교',
         'jobs': '작업 기록',
         'servers': 'AI 켜기와 비용',
         'help': '도움말',
         'current': '보고 있음',
         'a11y': '작업 메뉴'},
 'context': {'model': {'option': '{model} — {state}',
                       'state_ready': '연결됨',
                       'state_unknown': '연결 상태 확인 안 됨',
                       'state_off': 'AI 꺼짐',
                       'default_name': 'AI 모델',
                       'checking': '{model}의 연결을 확인하고 있습니다.',
                       'failed': '{model}의 연결 상태를 확인하지 못했습니다.',
                       'ready': '{model}이 응답했습니다.',
                       'off': '{model}이 연결되지 않았습니다. AI가 꺼져 있을 때는 정상 상태입니다.',
                       'reading': '저장된 점수와 원문은 AI 없이 볼 수 있습니다.',
                       'action': '할 일: 다시 시험하려면 AI 켜기와 비용에서 모델을 준비하세요.',
                       'current_label': '{model}의 지금 상태',
                       'off_normal': 'AI가 꺼져 있을 때는 정상 상태입니다.',
                       'saved_readable': '저장된 결과는 AI 없이 읽을 수 있습니다. 다시 시험할 때만 AI가 필요합니다.',
                       'company_ready': '연결됨 · 회사 서버',
                       'expected_reply': '기대한 {model}의 응답을 확인했습니다.',
                       'rented_ready': '연결됨 · 빌린 서버',
                       'rented_cost': '시간당 약 ${cost_per_hour} (예시). 가동 {hours}시간.',
                       'rented_loading': '켜는 중 · 빌린 서버',
                       'rented_elapsed': '{minutes}분 경과. 준비 중에도 요금이 나갑니다.',
                       'deleting': '서버 삭제 확인 중',
                       'deleting_cost': '완료 전까지 요금이 나갈 수 있습니다.',
                       'query_failed': '상태 확인 실패',
                       'readiness_unknown': '준비 여부를 확인하지 못했습니다.',
                       'query_pending': '응답 확인 중',
                       'wait_before_send': '확인 전에는 시험을 보내지 않습니다.',
                       'wrong_reply': '다른 모델 응답',
                       'mismatch': '기대한 {expected_model}와 응답 {actual_model}가 다릅니다.',
                       'company_loading': '켜는 중 · 회사 서버',
                       'company_elapsed': '{minutes}분 경과. 보통 15~25분이 걸립니다.',
                       'tunnel_closed': '연결 통로 닫힘',
                       'still_running': '회사 서버의 모델은 실행 중입니다.',
                       'connected_count': '연결된 모델 {count}개: {names}',
                       'checked_at': '마지막 확인: {time}'},
             'set': {'label_new': '새 문서 폴더 · data/pages 바로 아래',
                     'previous_version': '이전 개발 자료 {version}판',
                     'selected': '선택한 묶음 · {set_id}',
                     'no_text': '원문 글자 없음 · {set_id}'},
             'key': {'claude': 'AI 정답 초안 · Claude',
                     'silver': 'AI 정답 초안 · {name}',
                     'gold': '사람이 확인한 정답 · {name}'},
             'models': {'qwen36_35b_runpod': 'Qwen3.6 35B · 빌린 서버',
                        'qwen3_30b_a3b_rngd': 'Qwen3 30B · 회사 서버',
                        'gpt_oss_20b_rngd': 'gpt-oss 20B · 회사 서버',
                        'nuextract2_8b_runpod': 'NuExtract 2.0 8B · 빌린 서버',
                        'qwen3vl4b_rngd': 'Qwen3-VL 4B · 회사 서버',
                        'qwen38': 'Qwen3.8 27B (vLLM)',
                        'claude': 'Claude · AI 정답 초안',
                        'gpt': 'GPT'},
             'set_reason': {'eval_locked': '평가용 문서라 개발 중에는 열 수 없습니다.',
                            'unknown_doc': '문서 목록과 문서 정보 파일에서 용도를 확인하지 못했습니다.',
                            'empty': '이 폴더에 문서 폴더가 없습니다.',
                            'eval_only': '평가용 문서만 있는 묶음은 고를 수 없습니다.',
                            'no_line_numbers': '원문 줄 번호가 없어 새 시험에는 쓸 수 없습니다. 지난 결과는 읽을 수 있습니다.',
                            'nothing_open': '열 수 있는 문서가 없습니다.',
                            'run_moved': '실행에 쓴 {recorded} 폴더가 옮겨졌습니다. 지금은 {id}에서 읽습니다.',
                            'run_missing': '실행에 쓴 {recorded} 폴더를 찾지 못했습니다. 지금은 {name}에서 읽습니다. 원문 줄 번호가 다를 수 '
                                           '있습니다.',
                            'no_line_numbers_doc': '이 문서에 원문 줄 번호가 없습니다. 할 일: 줄 번호가 있는 묶음을 고르세요.',
                            'outside_try': '현재 실행기는 목록 밖 문서의 한 부분 시험을 지원하지 않습니다. 할 일: 시험 가능한 개발 문서를 고르세요.',
                            'outside_wait': '현재 실행기는 이 문서를 시험할 수 없습니다. 할 일: 시험 가능한 개발 문서를 고르세요.',
                            'dev_only': '개발용 문서만 시험할 수 있습니다.'},
             'key_reason': {'key_empty': '정답 폴더에 파일이 없습니다.',
                            'key_no_doc_files': '문서별 정답 파일이 없습니다. 파일 이름은 T21-S003.json 같은 문서 번호여야 합니다.',
                            'key_not_to21': '정해진 결과 형식(TO21 JSON)의 정답 파일이 없습니다.',
                            'key_eval_only': '평가용 문서의 정답만 있어 고를 수 없습니다.',
                            'unknown_key': '정답지 {id}를 찾지 못했습니다. 할 일: 정답지 목록에서 다시 고르세요.',
                            'unusable_key': '이 정답지를 쓸 수 없습니다. 이유: {reason}'},
             'documents': {'label': '점수를 매긴 문서', 'count': '개발용 문서 {count}건'},
             'change_documents': '필요할 때 문서 바꾸기',
             'answer': {'label': '비교한 정답',
                        'gold_count': '사람이 확인한 정답 · {count}건',
                        'gold_scope': '사람 확인 정답은 일부 개발 문서에만 있습니다. 정답이 있는 문서만 점수를 매깁니다.',
                        'doc_missing': '선택 문서의 정답 없음'},
             'answer_draft': 'AI 정답 초안 · 사람 확인 전',
             'change_answer': '필요할 때 정답 바꾸기',
             'answer_trust': '점수는 개선 방향을 보는 참고용입니다. 값은 원문과 맞춘 뒤 믿으세요. 사람 확인 정답은 일부 개발 문서에만 있습니다.',
             'prepare_model': '시험할 때 AI 준비하기',
             'picker': {'title': '문서와 정답을 함께 검토한 뒤 적용하세요.',
                        'set_count': '이전 개발 자료 {version}판 · {count}건',
                        'draft_count': 'AI가 먼저 만든 정답 · {count}건',
                        'draft_origin': 'AI가 먼저 작성',
                        'select_draft': '정답 초안 {count}건 고르기',
                        'select_gold': '사람 확인 정답 {count}건 고르기',
                        'apply': '선택한 기준 적용하기',
                        'cancel': '변경하지 않고 돌아가기',
                        'alternatives': '다른 후보와 사용할 수 없는 이유',
                        'usable': '사용 가능',
                        'dev_count': '개발 {count}건',
                        'draft_short': '초안 {count}건',
                        'open_empty': '결과 없음 상태 보기',
                        'gold_name': '사람이 확인한 정답',
                        'dev_scope': '개발 {count}건 중',
                        'review_gold': '{count}건의 정답으로 검토하기',
                        'empty_folder': '빈 자료 폴더',
                        'no_text': '원문 글자 없음',
                        'no_lines': '줄 번호 없는 묶음',
                        'no_lines_reason': '원문 근거를 확인할 줄 번호 없음',
                        'eval_set': '평가용 묶음',
                        'restricted': '열람 제한',
                        'dev_forbidden': '개발 중 사용 금지',
                        'unreadable_key': '읽을 수 없는 정답',
                        'key_format': '문서별 결과 형식 확인 필요',
                        'doc_keys': '문서별 정답과 출처',
                        'gold_short': '사람 확인 정답',
                        'remaining_docs': '나머지 개발 문서 {count}건',
                        'modified': '현재 파일 수정 시각: {time}.',
                        'fingerprint': '이 지문은 현재 파일 내용의 구분값입니다. 과거 점수를 복원하지는 않습니다.',
                        'effects': '적용하면 바뀌는 정보',
                        'effect_set': '문서 묶음을 바꾸면 해당 묶음의 실행 후보를 찾습니다.',
                        'effect_key': '정답을 바꾸면 저장 결과를 새 정답으로 점수를 다시 계산합니다.',
                        'no_model_call': 'AI를 다시 호출하지 않습니다.',
                        'hide_stale_score': '새 기준을 읽는 동안 이전 점수는 숨깁니다.',
                        'running_context': '이미 보낸 작업은 시작 당시 기준을 사용합니다.',
                        'absent_selection': '문서가 새 묶음에 없으면 빈 선택으로 남깁니다.',
                        'keep_valid': '유효한 문서와 부분과 편집한 설명은 유지합니다.',
                        'gold_origin': '사람이 검토'},
             'applied': {'title': '사람이 확인한 정답으로 기준을 바꿨습니다.',
                         'scope': '개발용 {total}건 중 정답이 있는 {count}건만 점수를 매깁니다.',
                         'missing_count': '나머지 {count}건은 정답 없음으로 표시합니다.',
                         'hide_stale': '점수를 읽기 전에는 이전 {count}건의 점수를 표시하지 않습니다.',
                         'open_result': '새 기준으로 결과 읽기'},
             'absent': {'title': '새 문서 묶음에는 보던 문서가 없습니다.',
                        'selection_cleared': '문서 선택을 비웠습니다. 다른 문서를 자동으로 고르지 않았습니다.',
                        'select_doc': '개발용 문서 고르기'},
             'a11y': '현재 문서와 정답과 모델',
             'unavailable': '확인 못 함'},
 'common': {'run': {'date': '{month}/{day}',
                    'prompt': 'AI에게 시킨 일 {version}',
                    'input': '원문 자료 {version}',
                    'manual': '앱에서 시작 · {title}',
                    'document': '문서 {doc} 한 건',
                    'probe': '일부 문서 시험 {round}회',
                    'diagnostic': '문제 확인 {run_id}',
                    'repeat': '{round}회차',
                    'eval': '평가용 문서 한 건 · 열람 제한',
                    'title': '{date} {model} · {conditions}'},
            'legacy': {'load_error': {'message': '자료를 읽지 못했습니다.', 'fix': '할 일: 앱을 켠 터미널의 오류를 보고 화면을 다시 여세요.'},
                       'request_error': {'message': '요청을 완료하지 못했습니다.',
                                         'fix': '할 일: 현재 화면의 입력과 연결 상태를 확인한 뒤 다시 시도하세요.'},
                       'cell_labels': {'c_none': '기록 없음',
                                       'c_ok': '성공',
                                       'c_re': '다시 뽑아 성공',
                                       'c_limit': '길이 제한 뒤 성공',
                                       'c_fail': '실패'},
                       'silver_labels': {'diff': '정답과 다름', 'only': '정답에만 있음', 'missing': '정답에 없음'},
                       'row_change': {'up': '정답에 가까워짐', 'down': '정답에서 멀어짐', 'same': '차이 유지'},
                       'changed': '조건 다름',
                       'no_pages': '원문 쪽 자료가 없습니다. 할 일: 원문이 있는 문서 묶음을 고르세요.',
                       'no_lines': '이 쪽에는 줄 글자가 없습니다.',
                       'no_models': '등록된 모델이 없습니다.',
                       'time_over': '목표 초과',
                       'loading': '자료를 읽고 있습니다.'},
            'conditions': {'dev10': '개발 10건',
                           'eval': '평가 10건',
                           'probe': '일부 시험',
                           'cls': '분류 검사',
                           'optonly': '선택 항목만',
                           'wsonly': '빈칸 줄이기만',
                           'diag': '문제 확인',
                           'none': 'AI에게 시킬 일 없음',
                           'ex': '예시 포함',
                           'w1': '동시 1개',
                           'p3': 'AI에게 시킬 일 p3'},
            'document_definition': '화학제품 안전 설명서(MSDS)입니다. 성분과 응급조치 등 16개 주제로 나뉩니다.',
            'local_only': '내 컴퓨터에서 쓰는',
            'tool_kind': '문서 검토 도구',
            'item': '항목',
            'score': '점수',
            'target': '목표',
            'priority': '중요도',
            'required': '필수',
            'important': '중요',
            'ordinary': '일반',
            'document': '문서',
            'tier': '등급',
            'count': '수',
            'weight': '무게',
            'record': '기록',
            'done': '완료',
            'display': '표시',
            'close': '닫기',
            'selected': '선택됨',
            'wrong': '틀림',
            'subject': '대상',
            'run_label': '실행',
            'section': '부분',
            'blank': '빈칸',
            'made': '만듦',
            'answer_key': '정답지',
            'input': '입력',
            'content': '내용',
            'format': '형식',
            'image': '이미지',
            'warning': '경고',
            'none': '없음',
            'result': '결과',
            'category': '구분',
            'set': '묶음',
            'basis': '기준',
            'change': '변화',
            'same': '같음',
            'table': '표',
            'answer': '정답',
            'shared': '공통',
            'started': '시작',
            'model': '모델',
            'no': '아님',
            'used': '사용',
            'job': '작업',
            'progress': '진행',
            'stop': '중단',
            'method': '방법',
            'server': '서버',
            'manage': '관리',
            'action': '할 수 있는 일',
            'scope': '범위',
            'selection': '선택',
            'current': '현재',
            'candidate': '후보',
            'available': '가능',
            'present': '있음',
            'ai': 'AI',
            'expand': '펼치기',
            'collapse': '접기',
            'raw_error': '원문 보기',
            'todo': '할 일: {action}'},
 'errors': {'empty': {'fact': '아직 저장된 실행이 없습니다.', 'todo': '시험 결과가 생기면 점수와 문제를 볼 수 있습니다. 할 일: 시험할 문서를 고르세요.'},
            'loading': {'fact': '고른 정답지로 실행 결과를 읽고 있습니다.',
                        'available': '새 기준 아래 이전 점수는 숨겼습니다. 메뉴와 모델 관리는 계속 사용할 수 있습니다.',
                        'open_result': '읽은 결과 보기'},
            'pages_missing': {'title': '고른 묶음에서 이 문서의 쪽 글자를 찾지 못했습니다.',
                              'fact': '{where}에서 원문 쪽 자료를 찾지 못했습니다.',
                              'todo': '할 일: 이 문서의 원문이 있는 묶음을 고르세요.',
                              'keep_target': '{doc}의 {section}번 부분을 유지했습니다. 할 일: 원문이 있는 묶음을 고르세요.',
                              'details': '오류 원문과 읽은 자료',
                              'set': '조회한 묶음: 빈 자료 폴더 ·',
                              'no_lines': '줄 번호 없는 묶음은 자료 없음과 사유를 구분합니다.',
                              'status_not_lock': '직접 요청의 {status_code}만으로 평가 잠금이라고 판단하지 않습니다.'},
            'eval_locked': {'fact': '평가용 {count}건은 개발 과정에서 열 수 없습니다.',
                            'todo': '최종 성능을 공정하게 재려고 잠가 두었습니다. 할 일: 개발용 문서를 고르세요.',
                            'no_read': '원문과 그림을 요청하지 않습니다.',
                            'no_run': '시험과 점수 계산도 제한합니다.'},
            'key_missing': {'fact': '이 문서에 대응하는 정답지가 없습니다.',
                            'todo': '정답이 없어 점수를 계산하지 않았습니다. 할 일: 정답지를 고르거나 점수 없이 원문을 읽으세요.',
                            'select': '정답지 고르기',
                            'read_source': '점수 없이 원문 읽기',
                            'can_extract': '추출 실행 자체는 정답 유무와 별개입니다.'},
            'model_none': {'fact': '회사 서버에 켜진 모델이 없습니다.',
                           'todo': '회사 서버까지 연결은 됐습니다. 할 일: 시험할 AI 모델을 고르세요.',
                           'select': '모델 고르기'},
            'tunnel_closed': {'fact': '회사 서버로 가는 연결 통로가 닫혀 있습니다.',
                              'todo': '회사 서버의 {model}는 켜져 있습니다. 할 일: 이 컴퓨터의 연결 통로를 여세요.',
                              'open': '연결 통로 열기'},
            'model_loading': {'fact': '회사 서버에서 {model}를 켜고 있습니다.',
                              'elapsed': '{minutes}분이 지났습니다. 준비에는 보통 15~25분이 걸립니다.',
                              'late': '{minutes}분이 지나면 서버 기록을 확인하세요. 시간이 지났다고 실패한 것은 아닙니다.',
                              'no_resend': '모델 준비 중 · 중복 요청 불가',
                              'open_ready': '준비가 끝난 상태 보기',
                              'ready_condition': '기대한 모델의 응답이 확인되면 다음 행동이 바뀝니다.'},
            'job_pages': {'fact': '시험할 문서의 쪽 글자를 읽지 못했습니다.',
                          'todo': '할 일: 원문 폴더를 확인한 뒤 같은 문서로 다시 시험하세요.',
                          'retry': '입력 확인 후 다시 시험하기',
                          'record': '실패한 작업의 기록',
                          'target': '작업: {doc}의 {section}번 부분 시험.',
                          'log_path': '로그 위치:'},
            'env': {'line': '설정 파일(.env)의 {line}번째 줄을 읽지 못했습니다.',
                    'line_todo': '할 일: 해당 줄의 따옴표와 = 표시를 고친 뒤 설정 다시 읽기를 누르세요.',
                    'missing': '설정 파일(.env)에 {variable} 설정이 없습니다.',
                    'runpod_url': '할 일: RUNPOD_VLLM_BASE_URL에 빌린 서버의 중계 주소를 넣으세요.',
                    'company_url': '할 일: RNGD_BASE_URL에 보안 연결을 거친 내 컴퓨터 쪽 주소를 넣으세요.',
                    'unknown_url': '할 일: 모델 설정에서 {variable}에 필요한 주소 형식을 확인하세요.'},
            'connection': {'ssh_prefix': {'fact': 'RNGD_SSH 설정에 ssh 명령어까지 들어 있습니다.',
                                          'todo': '할 일: 앞의 ssh를 빼고 접속 옵션만 적으세요.'},
                           'ssh_missing': {'fact': '회사 서버 접속 설정(RNGD_SSH)이 없습니다.',
                                           'todo': '할 일: .env.example의 RNGD_SSH 항목을 설정 파일에 채우세요.'},
                           'certificate': {'fact': '빌린 서버 주소의 인증서를 확인하지 못했습니다.',
                                           'todo': '할 일: Python 3.11을 쓴다면 인증서 설치 파일을 실행한 뒤 앱을 다시 켜세요.'},
                           'model_key': {'fact': '모델 서버가 접속 키를 거절했습니다.',
                                         'todo': '할 일: 설정 파일의 모델 접속 키와 서버를 켤 때 쓴 키를 맞추세요.'},
                           'account_key': {'fact': '빌린 서버 관리 키가 거절됐습니다.',
                                           'todo': '할 일: RunPod에서 관리 키를 다시 만든 뒤 설정 파일에 넣으세요.'},
                           'no_response': {'fact': '모델 서버가 응답하지 않습니다.',
                                           'todo': '할 일: AI 켜기와 비용에서 연결 통로와 모델 준비 상태를 확인하세요.'},
                           'other': {'fact': '서버 상태를 읽지 못했습니다.', 'todo': '할 일: 오류 기록을 열어 설정과 연결 상태를 확인하세요.'},
                           'model_key_changed': '서버를 만든 뒤 접속 키를 바꿨다면 서버를 다시 만들어야 합니다. 비용을 확인한 뒤 진행하세요.'},
            'job': {'pages': {'message': '원문 쪽 글자가 있는 폴더나 파일을 찾지 못했습니다.',
                              'fix': '할 일: 해당 문서의 원문이 있는 묶음을 다시 고르세요.'},
                    'outside': {'message': '현재 실행기는 이 문서를 시험할 수 없습니다.', 'fix': '할 일: 시험 가능한 개발 문서를 고르세요.'},
                    'connect': {'message': '모델 서버에 연결하지 못했습니다.', 'fix': '할 일: AI 켜기와 비용에서 모델 상태를 확인하세요.'},
                    'key': {'message': '모델 서버가 키를 거절했습니다.',
                            'fix': '할 일: 모델 접속 키가 서버를 켤 때 쓴 키와 같은지 설정 파일에서 확인하세요.'},
                    'eval': {'message': '평가용 문서는 시험할 수 없습니다.', 'fix': '할 일: 개발용 문서를 고르세요.'},
                    'other': {'message': '작업이 오류로 끝났습니다.', 'fix': '할 일: 마지막 오류 기록을 확인하세요.'},
                    'no_line': {'fix': '할 일: 작업 기록을 열어 마지막 오류를 확인하세요.'}},
            'request': {'unknown_set': {'message': '없는 문서 묶음입니다: {id}.', 'fix': '할 일: 문서 묶음 목록에서 다시 고르세요.'},
                        'unusable_set': {'message': '고를 수 없는 묶음입니다: {reason}',
                                         'fix': '할 일: 문서 묶음 목록에서 다른 묶음을 고르세요.'},
                        'unknown_key': {'message': '없는 정답지입니다: {id}.', 'fix': '할 일: 정답지 목록에서 다시 고르세요.'},
                        'unusable_key': {'message': '고를 수 없는 정답지입니다: {reason}',
                                         'fix': '할 일: 정답지 목록에서 다른 정답지를 고르세요.'},
                        'missing_pages': {'message': '{where}의 쪽 자료가 없습니다.',
                                          'fix': '할 일: 이 문서가 있는 문서 묶음을 다시 고르세요.'},
                        'missing_run': {'message': '없는 실행입니다: {name}.', 'fix': '할 일: 실행 목록에서 다시 고르세요.'},
                        'doc_not_in_run': {'message': '이 실행에서 열 수 없는 문서입니다: {doc}.',
                                           'fix': '할 일: 이 실행의 문서 목록에서 다시 고르세요.'},
                        'doc_not_in_set': {'message': '이 묶음에서 열 수 없는 문서입니다: {doc}.',
                                           'fix': '할 일: 이 묶음의 문서 목록에서 다시 고르세요.'},
                        'bad_query': {'fix': '할 일: 입력을 고친 뒤 다시 보내세요.'}},
            'confirm_expired': {'fact': '이 확인 화면에서 실행할 수 있는 시간이 지났습니다.',
                                'todo': '할 일: 상태를 다시 읽은 뒤 확인 화면을 다시 여세요.'},
            'state': '현재 상태',
            'gold_loading': {'title': '사람이 확인한 정답으로 점수를 읽고 있습니다.',
                             'scope': '개발용 {total}건 중 {count}건을 점수를 매길 수 있습니다.',
                             'hide_stale': '이전 정답의 점수는 표시하지 않습니다.',
                             'open_failed': '새 기준 조회 실패 상태 보기'},
            'tunnel_and_model': {'title': '연결 통로가 닫혀 있습니다.', 'no_model': '회사 서버에 켜진 모델도 없습니다.'}},
 'compare': {'table': {'open': '비교표 만들기'}},
 'jobs': {'trial': {'open_batch': '여러 문서 시험하기'}}}

# S01 승인 글. COPY의 가짜 예시는 데이터로 사용하지 않는다.
UI_TEXT["score"] = {'criteria': {'hint': '23가지 기준의 점수와 목표를 확인하세요.',
              'expand': '점수가 깎인 곳 모두 보기 · 23가지 기준',
              'title': '점수를 매기는 기준 23개',
              'below_count': '목표 아래인 항목은 {count}개입니다.',
              'filter_below': '목표 아래 {count}개 먼저 보기',
              'show_all': '모든 항목 23개 보기 · 숨긴 항목 없음',
              'loss': '깎인 점수',
              'method': '측정 방법',
              'met': '목표 이상',
              'method_msds': '자료를 몇 건으로 나눴는지 비교',
              'below': '목표 아래',
              'method_management': '번호와 날짜와 개정 횟수 비교',
              'method_product': '이름과 긴급 전화 비교',
              'method_signal': '위험·경고 같은 말 비교',
              'method_pictogram': '선택한 위험 그림 종류 비교',
              'method_hazard': '위험 문구 번호의 목록 비교',
              'method_precaution': '예방 문구 번호의 목록 비교',
              'method_classification': '위험 종류와 단계의 짝 비교',
              'method_components': '성분 식별 번호로 목록 비교',
              'method_component_fields': '성분별 이름과 국내 번호 비교',
              'method_content': '부등호와 수치와 단위 비교',
              'method_exposure': '성분과 기준 종류와 수치 비교',
              'method_physchem_required': '끓는점 등 주요 성질 비교',
              'method_physchem_other': '색과 냄새 등 나머지 성질 비교',
              'method_acute': '먹음·피부·흡입 독성 비교',
              'method_toxicity_other': '자극과 과민 반응 비교',
              'method_cmr': '세 종류 독성의 분류 비교',
              'method_ecology': '생물 독성과 분해성 비교',
              'method_domestic': '규제 항목과 해당 여부 비교',
              'method_regulation_concentration': '규제가 적용되는 농도 비교',
              'method_foreign': '해외 규제 항목과 해당 여부 비교',
              'method_transport': '운송 번호와 위험 등급 비교',
              'method_narrative': '응급조치 등 문장의 글자 유사도 비교',
              'msds': '문서 안 안전자료 수',
              'msds_original': '(MSDS 건수)',
              'management': '작성일과 개정 정보',
              'management_original': '(관리정보)',
              'product': '제품과 회사 정보',
              'product_original': '(제품명)',
              'signal': '위험을 알리는 말',
              'signal_original': '(신호어)',
              'pictogram': '위험 표시 그림',
              'pictogram_original': '(그림문자)',
              'hazard': '위험 문구 번호',
              'hazard_original': '(H 코드)',
              'precaution': '예방 문구 번호',
              'precaution_original': '(P 코드)',
              'classification': '위험의 종류와 정도',
              'classification_original': '(유해성 분류)',
              'components': '들어 있는 성분 목록',
              'components_original': '(구성성분(CAS))',
              'component_fields': '성분 이름과 번호',
              'component_fields_original': '(구성성분 필드)',
              'content': '성분이 들어 있는 양',
              'content_original': '(함유량)',
              'exposure': '작업장 공기 중 허용 농도',
              'exposure_original': '(8번 부분 · 노출기준)',
              'physchem_required': '주요 물리·화학 성질',
              'physchem_required_original': '(9번 부분 필수 물성)',
              'physchem_other': '그 밖의 물리·화학 성질',
              'physchem_other_original': '(9번 부분 기타 물성)',
              'acute': '짧은 노출의 독성',
              'acute_original': '(11번 부분 급성독성)',
              'toxicity_other': '그 밖의 독성',
              'toxicity_other_original': '(11번 부분 기타 독성)',
              'cmr': '암·유전·생식 관련 독성',
              'cmr_original': '(11번 부분 CMR)',
              'ecology': '환경에 미치는 영향',
              'ecology_original': '(12번 부분 생태)',
              'domestic': '국내 규제 해당 여부',
              'domestic_original': '(15번 부분 국내 규제)',
              'regulation_concentration': '국내 규제의 기준 농도',
              'regulation_concentration_original': '(15번 부분 국내 규제 기준농도)',
              'foreign': '해외 규제 해당 여부',
              'foreign_original': '(15번 부분 해외)',
              'transport': '운송에 필요한 정보',
              'transport_original': '(14번 부분 운송)',
              'narrative': '문장으로 쓰인 설명',
              'narrative_original': '(서술형)',
              'hidden': '목표 아래가 아닌 항목 {count}개를 숨겼습니다.',
              'score': '점수 {score}점 · 목표 {target}점',
              'weight': '{level} · 무게 {weight}'},
 'history': {'hint': '최근 결과와 지난 최고점을 구분해서 보세요.',
             'expand': '실행 이력 · {count}개 결과 중 최고 {best}점',
             'caption': '완료 시각 순 점수 · 목표 점수 {line}점',
             'a11y': '{date} {first_score}점, {middle_day}일 {middle_score}점과 최고 {best}점, {latest_day}일 최근 '
                     '{latest_score}점. 모두 목표 점수 {line}점 아래입니다.',
             'model_date': '{month}/{day} · {model}',
             'best_point': '{score} · 최고',
             'latest_point': '{score} · 최근',
             'title': '지난 결과',
             'latest_meaning': '현재 화면은 최고 점수가 아니라 가장 늦게 끝난 결과를 보여 줍니다.',
             'finished': '끝난 시각',
             'score': '점수 / {maximum}',
             'current': '현재 · 가장 최근',
             'best': '지난 최고점',
             'previous': '이전 결과',
             'comparable': '네 결과는 같은 문서 {count}건과 같은 정답 초안으로 비교했습니다.',
             'target': '목표 점수은 모두 {line}점입니다.',
             'exclude_answer': '정답을 만들기 위한 실행은 최고점과 추세에서 제외합니다.',
             'answer_records': '정답 생성 기록도 아래 목록에서 따로 열 수 있습니다.',
             'select_record': '조회할 기록',
             'run_option': '문서 처리 · {time} · {score}점',
             'answer_option': '정답 생성 · {time} · 비교 대상 아님',
             'select_a': '먼저 비교할 결과 A',
             'option': '{time} · {score}점',
             'select_b': '나중에 비교할 결과 B',
             'selection_order': '표의 선택 순서가 A와 B의 순서입니다.',
             'compare': '선택한 두 결과 비교하기',
             'clear': '선택 해제하기',
             'point': '{run} · {score}점 · {model} · {time}',
             'selected': '{order} 선택됨',
             'plotted': '점수 기록 {count}개를 표시합니다.',
             'current_record': '지금 보는 결과',
             'started': '시작 시각'},
 'documents': {'hint': '문서별 점수와 AI 요청 기록을 확인하세요.',
               'expand': '문서와 호출 · 개발용 {count}건 완료',
               'title': '문서별 점수와 AI 요청 기록',
               'completed': '개발용 {count}건을 완료했습니다.',
               'time_target': '처리 시간의 목표는 문서 한 건당 {seconds}초입니다.',
               'must_below': '목표 아래 필수 항목',
               'duration': '처리 시간',
               'time_state': '시간 상태',
               'recorded': '기록 있음',
               'within_time': '{minutes}분 목표 이내',
               'time_unknown': '시간 비교 불가'},
 'rows': {'hint': '표에 담긴 행 수를 정답과 비교하세요.',
          'expand': '표 행 수 · {count}종을 정답과 비교',
          'title': '표에 담긴 행 수',
          'meaning': '같은 종류의 값이 몇 줄씩 들어 있는지 비교합니다.',
          'kind': '표 종류',
          'prediction': 'AI 결과',
          'answer': '정답 초안',
          'ratio': '정답 대비 비율',
          'physchem': '물리·화학 성질',
          'cmr': '암·유전·생식 독성',
          'intl_class': '국제 위험 분류',
          'not_applicable': '해당 없음',
          'components': '성분',
          'exposure': '노출기준',
          'toxicity': '독성',
          'ecology': '생태',
          'regulations': '규제'},
 'summary': {'headline_below': '목표 점수 {line}점보다 {gap}점 낮습니다.',
             'headline_met': '목표 점수 {line}점에 도달했습니다.',
             'value': '전체 점수는 {score}점입니다.',
             'must_some': '23개 점수 기준 중 꼭 맞아야 하는 {total}개가 필수 기준입니다. {met}개가 각자의 목표를 채웠습니다.',
             'must_all': '필수 기준 {total}개가 모두 각자의 목표에 닿았습니다.',
             'unscored': '이 결과는 점수를 계산하지 않았습니다.',
             'unscored_todo': '할 일: 비교할 AI 결과와 정답이 있는지 확인하세요.',
             'drop': '{item}은 {score}점입니다. 목표는 {goal}점입니다. 가장 많은 문제 유형은 {cause} {count}건입니다.',
             'next_trial': '할 일: {section}번 부분을 다시 시험하세요.',
             'next_source': '할 일: {item}의 문제 값을 원문과 맞춰 보세요.',
             'next_compare': '두 목표에 모두 도달했습니다. 할 일: 두 결과를 비교해 반복할 때의 차이를 보세요.',
             'next_items': '할 일: 모든 기준의 점수와 목표를 확인하세요.',
             'counts_meaning': '{counts}건은 이 기준에서 찾은 문제 값 수입니다. 값 하나가 몇 점인지는 따로 계산하지 않습니다.',
             'loss_meaning': '100점에서 {total_loss}점이 깎여 {score}점입니다. 그중 {item_loss}점이 이 기준에서 깎였습니다. 23개 기준 중 '
                             '가장 많습니다.',
             'history': '저장된 결과 {count}개 중 최고점은 {score}점입니다. 해당 결과는 {run}입니다.',
             'docs': '문서 {count}건입니다. {score_detail} {time_detail}',
             'lowest': '가장 낮은 점수는 {doc}의 {score}점입니다.',
             'slowest': '가장 오래 걸린 문서는 {doc}입니다. {seconds}초 걸렸습니다.',
             'no_scores': '문서별 점수 기록이 없습니다.',
             'no_times': '문서별 시간 기록이 없습니다.',
             'grid': 'AI 요청 {count}개의 상태입니다.',
             'grid_count': '{state} {count}개',
             'rows': '표 {count}개 중 정답보다 행이 적은 표는 {short}개입니다.',
             'rows_shortest': '행이 가장 부족한 표는 {table}입니다. AI 결과는 {pred}행입니다. 정답은 {answer}행입니다.',
             'headline_model': '{model}의 최근 점수는 목표보다 낮습니다.',
             'scope': '{model} · 개발용 문서 {count}건의 점수',
             'denominator': '/ 100점',
             'gap_short': '목표 {line}점보다 {gap}점 낮음',
             'target': '목표 점수 {line}점',
             'below_best': '지난 최고점 {best}점보다 {gap}점 낮습니다.',
             'finished': '{time}에 끝난 가장 최근 결과입니다.',
             'top_problem_exposure': '가장 큰 문제는 공기 속 물질의 허용량(허용 농도)입니다.',
             'exposure_section': '8번 부분 · 작업장 공기 기준(노출기준)',
             'back': '최근 결과로 돌아가기',
             'must_progress': '필수 {total}개 중 목표 달성 {met}개',
             'target_line': '목표선 {line}점',
             'top_problem': '가장 큰 문제는 {item}입니다.',
             'open_source': '문제의 원문 보기',
             'unlinked': '연결할 문서나 부분을 확인하지 못했습니다. 항목별 문제 기록을 확인하세요.'},
 'tables': {'components': '성분 (3번 부분)',
            'exposure_limits': '노출기준 (8번 부분)',
            'physchem': '물리·화학 성질 (9번 부분)',
            'toxicity': '독성 (11번 부분)',
            'cmr': '발암성 등 CMR (11번 부분)',
            'ecotox': '생태 독성 (12번 부분)',
            'regulations': '규제 (15번 부분)',
            'intl_class': '국제 분류 (15번 부분)',
            'extras': '표 밖에 남은 값'},
 'flow': {'a11y': '현재 작업의 흐름', 'result': '1 결과 보기', 'cause': '2 원인 찾기', 'retest': '3 다시 시험'},
 'problem': {'counts': {'missing': '정답에 있는 값을 못 뽑음 {count}건',
                        'made': '정답에 없는 값을 만듦 {count}건',
                        'wrong': '정답과 다른 값을 뽑음 {count}건'},
             'open_wrong': '틀린 값 {count}건의 원문 보기',
             'evidence_hint': 'AI가 적은 원문 줄이 있어 바로 확인할 수 있는 틀린 값부터 봅니다. 못 뽑은 {count}건의 추정 줄은 목록에서 봅니다.',
             'scope': '문제 종류와 기록 범위',
             'missing_meaning': '못 뽑음: 정답에는 있고 AI 결과에는 없는 값',
             'made_meaning': '만듦: 정답에는 없고 AI 결과에는 있는 값',
             'wrong_meaning': '틀림: 같은 칸의 값이 정답과 다름',
             'answer_warning': '정답 자체의 오류 가능성은 원문과 함께 검토합니다.',
             'section_count': '{section}번 부분 문제는 총 {count}건입니다.',
             'linked_count': '연결된 근거의 대표 {count}건을 먼저 보여 줍니다.',
             'other_counts': '나머지 {count}건은 못 뽑음 {missing}건과 없는 값을 만듦 {made}건입니다.',
             'unrecorded': '문제 상세를 수집하지 않은 항목은 ‘기록 없음’입니다.',
             'checked_empty': '확인해서 문제가 없던 항목은 ‘0건’입니다.',
             'answer_gap': '현재 정답 초안에서 확인할 빈 곳: 예시 {component}의 출처 칸 {count}개.',
             'found_at': '발견 시각: {time}.',
             'nonempty_score': '해당 항목의 빈 행 제외 보조 점수는 {score}%입니다.',
             'open_remaining': '나머지 문제 {count}건 모두 보기',
             'kind': '문제 종류',
             'record': '기록된 내용',
             'missing': '못 뽑음',
             'missing_value': '{component}의 기준 값이 결과에 없음',
             'made': '없는 값을 만듦',
             'made_value': '원문에 없는 {concentration} mg/m³를 채움',
             'open_linked': '연결된 문제 값 보기',
             'shown': '문제 {total}건 중 {shown}건을 표시합니다.',
             'show_more': '문제 기록 더 보기',
             'empty': '이 항목에 남긴 문제 상세가 없습니다.',
             'cause': '가장 많은 문제 유형: {cause}'},
 'calculation': {'title': '점수 계산 방법',
                 'weighted': '중요도를 반영한 전체 점수(가중 종합)입니다.',
                 'must': '꼭 맞춰야 함(필수)',
                 'weight_total': '무게 합은 61입니다.',
                 'formula': '손실 = 무게 × (1 − 기준 점수) ÷ 61 × 100',
                 'exposure_example': '허용 농도: 3 × (1 − 0.40) ÷ 61 × 100 = 약 2.95점.',
                 'total_loss': '총손실은 반올림 전 합으로 계산한 {loss}점입니다.',
                 'rounded_sum': '각 행을 따로 반올림한 합은 {loss}점입니다.',
                 'counts_not_points': '문제 값 {missing}/{made}/{wrong}건을 점수로 환산하지 않습니다.',
                 'weight': '{level} 기준 {count}개 · 무게 {weight}',
                 'loss_formula': '손실 = 무게 × (1 − 기준 점수) ÷ 점수가 있는 항목의 무게 합 × 100',
                 'weight_basis': '점수가 있는 항목의 무게 합: {weight}'},
 'calls': {'title': '문서 안 첫 번째 안전자료 · 16개 부분의 AI 요청',
           'section': '{section}번 부분',
           'multiple_msds': '한 파일에 안전자료가 여럿이면 자료 순번으로 나눠 표시합니다.',
           'example_scope': '이 예시는 첫 번째 안전자료의 기록입니다.',
           'legend': '요청 상태의 뜻',
           'parsed': 'AI의 답을 값으로 읽음',
           'reextract': '다시 뽑음',
           'reextract_meaning': '첫 답의 문제를 알려 다시 요청',
           'output_limit': '출력 한도',
           'output_limit_meaning': '답변 길이 제한에 도달',
           'failed': '요청을 완료하지 못함',
           'unknown': '성공 여부를 확인할 기록이 없음',
           'expand_section': '{section}번 부분 요청 자세히',
           'attempts': '시도 {count}회 · {seconds}초 · 표 형식으로 요청했습니다.',
           'not_limited': '출력 길이 제한에 걸리지 않았습니다.',
           'failure_count': '실패한 요청은 {count}개입니다.',
           'slow_threshold': '시간이 {seconds}초를 넘으면 느린 처리로 표시합니다.',
           'no_time_inference': '시간 기록이 없으면 초과라고 추정하지 않습니다.',
           'scope': '{doc} · {number}번째 안전자료',
           'attempt_info': '시도 {count}회 · {seconds}초',
           'mode': '요청 방식: {mode}',
           'limit_reason': '출력 한도 원인: {reason}'},
 'conditions': {'expand': '처리 조건과 보조 점수 보기',
                'value': '저장된 값',
                'run_name': '실행 이름',
                'raw_name': '원래 이름',
                'prompt': 'AI에게 시킨 일(지시문)',
                'prompt_version': '{version}번째 버전 ·',
                'pages': '원문 글자 묶음',
                'previous': '이전 개발 자료 ·',
                'score_scope': '점수를 매긴 범위',
                'score_counts': '{total}건 중 {scored}건. 정답 없음 {missing}건. 제외 {excluded}건.',
                'kind': '실행 분류',
                'comparable': '문서 여러 건 처리. 비교 가능.',
                'nonempty_score': '값 없는 행을 뺀 보조 점수는 {score}점입니다.',
                'nonempty_gain': '원래 점수보다 {gap}점 높습니다.',
                'keep_components': '성분 목록은 다른 표에서 참조하므로 제외하지 않습니다.',
                'exclude_answer': '정답을 만드는 실행은 최고점과 추세에서 제외합니다.',
                'progress': '문서 {total}건 중 {done}건 완료',
                'running': '처리 중',
                'nonempty_difference': '원래 점수와의 차이: {gap}점',
                'nonempty_meaning': '정답과 결과 양쪽에서 자료없음·해당없음·비해당·미기재 행을 빼고 같은 채점기로 다시 잰 보조 점수입니다.'},
 'first': {'hint': '처음이라면 결과 읽기부터 시작하세요.', 'open_guide': '처음 사용 안내 열기'},
 'missing_only': {'fact': '이 변형에는 못 뽑은 값만 있습니다.',
                  'open_first': '못 뽑은 첫 값의 원문 보기',
                  'estimated': '못 뽑은 값은 내용이 맞는 줄을 추정으로 찾아 보여 줍니다.',
                  'section_count': '{section}번 부분 문제는 못 뽑은 값 {count}건입니다.',
                  'first': '첫 누락 값의 추정 줄을 먼저 보여 줍니다.',
                  'all_available': '못 뽑은 {count}건은 모두 목록에서 열 수 있습니다.',
                  'open_all': '못 뽑은 문제 {count}건 모두 보기'},
 'empty': {'title': '이 문서 묶음으로 만든 결과가 없습니다.',
           'state': '결과 없음',
           'fact': '현재 선택한 개발 자료에는 저장된 실행이 없습니다.',
           'prepare': '시험 준비하기',
           'filters': '결과 필터 확인하기',
           'set': '입력 묶음은 이전 개발 자료 {version}판입니다.',
           'no_mixing': '다른 묶음의 점수는 여기에 섞지 않습니다.',
           'change_set': '문서 묶음 바꾸기'},
 'partial': {'title': '실행 기록 {total}개 중 {failed}개를 읽지 못했습니다.',
             'state': '일부 읽기 실패',
             'todo': '읽은 결과만 표시했습니다. 할 일: 기록을 다시 읽으세요.',
             'reload': '다시 읽기'},
 'key_failed': {'title': '새 정답지로 점수를 읽지 못했습니다.',
                'state': '점수 확인 실패',
                'todo': '이전 점수는 숨겼습니다. 할 일: 선택한 사람 확인 정답을 다시 읽으세요.',
                'reload': '정답지 다시 확인하기'},
 'no_problem': {'title': '총점에서 깎인 점수가 없습니다.',
                'state': '열어 볼 문제 없음',
                'journey': '문제의 근거를 확인하는 갈래 1은 여기서 끝낼 수 없습니다.',
                'open_items': '항목별 점수 보기',
                'no_fallback': '가장 큰 문제는 없음으로 표시합니다. 다른 값을 대신 열지 않습니다.'},
 'waiting': {'company': 'AI를 켜는 동안 저장된 결과를 읽을 수 있습니다.',
             'back_company': '준비 중인 모델 상태로 돌아가기',
             'target': '시험 대상: {doc} · {section}번 부분.',
             'rented': '빌린 서버가 준비되는 동안 저장된 결과를 읽습니다.',
             'back_rented': '서버 상태와 비용으로 돌아가기',
             'cost': '시간당 약 ${cost_per_hour}의 요금이 나갑니다(예시).'},
 'basis': {'label': '{key} 기준 · 채점 문서 {count}건', 'fallback': '정답 초안(실버) 기준'},
 'loading': {'scoring': '실행 {count}개를 채점 중입니다. 처음에는 수십 초 걸릴 수 있습니다.'},
 'load_failed': {'fact': '실행 결과를 읽지 못했습니다.', 'todo': '할 일: 기록을 다시 읽으세요. 계속 실패하면 앱을 켠 터미널의 오류를 확인하세요.'},
 'selection': {'not_comparable': '전체 실행 비교 대상 아님', 'unknown': '분류 확인 안 됨', 'other_set': '다른 문서 묶음'},
 'gaps': {'title': '정답지에서 확인할 빈 곳',
          'none': '이 정답지에 기록된 빈 곳이 없습니다.',
          'source': '출처: {source}',
          'count': '기록 {count}건'},
 'item_names': {'MSDS 건수': '문서 안 안전자료 수',
                '관리정보': '작성일과 개정 정보',
                '제품명': '제품과 회사 정보',
                '신호어': '위험을 알리는 말',
                '그림문자': '위험 표시 그림',
                'H 코드': '위험 문구 번호',
                'P 코드': '예방 문구 번호',
                '유해성 분류': '위험의 종류와 정도',
                '구성성분(CAS)': '들어 있는 성분 목록',
                '구성성분 필드': '성분 이름과 번호',
                '함유량': '성분이 들어 있는 양',
                '8항 노출기준': '작업장 공기 중 허용 농도',
                '9항 필수 물성': '주요 물리·화학 성질',
                '9항 기타 물성': '그 밖의 물리·화학 성질',
                '11항 급성독성': '짧은 노출의 독성',
                '11항 기타 독성': '그 밖의 독성',
                '11항 CMR': '암·유전·생식 관련 독성',
                '12항 생태': '환경에 미치는 영향',
                '15항 국내 규제': '국내 규제 해당 여부',
                '15항 국내 규제 기준농도': '국내 규제의 기준 농도',
                '15항 해외': '해외 규제 해당 여부',
                '14항 운송': '운송에 필요한 정보',
                '서술형': '문장으로 쓰인 설명'},
 'item_methods': {'MSDS 건수': '자료를 몇 건으로 나눴는지 비교',
                  '관리정보': '번호와 날짜와 개정 횟수 비교',
                  '제품명': '이름과 긴급 전화 비교',
                  '신호어': '위험·경고 같은 말 비교',
                  '그림문자': '선택한 위험 그림 종류 비교',
                  'H 코드': '위험 문구 번호의 목록 비교',
                  'P 코드': '예방 문구 번호의 목록 비교',
                  '유해성 분류': '위험 종류와 단계의 짝 비교',
                  '구성성분(CAS)': '성분 식별 번호로 목록 비교',
                  '구성성분 필드': '성분별 이름과 국내 번호 비교',
                  '함유량': '부등호와 수치와 단위 비교',
                  '8항 노출기준': '성분과 기준 종류와 수치 비교',
                  '9항 필수 물성': '끓는점 등 주요 성질 비교',
                  '9항 기타 물성': '색과 냄새 등 나머지 성질 비교',
                  '11항 급성독성': '먹음·피부·흡입 독성 비교',
                  '11항 기타 독성': '자극과 과민 반응 비교',
                  '11항 CMR': '세 종류 독성의 분류 비교',
                  '12항 생태': '생물 독성과 분해성 비교',
                  '15항 국내 규제': '규제 항목과 해당 여부 비교',
                  '15항 국내 규제 기준농도': '규제가 적용되는 농도 비교',
                  '15항 해외': '해외 규제 항목과 해당 여부 비교',
                  '14항 운송': '운송 번호와 위험 등급 비교',
                  '서술형': '응급조치 등 문장의 글자 유사도 비교'},
 'cause_keys': {'missing': '빠뜨림', 'wrong': '틀림', 'made': '지어냄'},
 'cause_names': {'missing': '못 뽑음', 'wrong': '틀림', 'made': '없는 값을 만듦'}}
UI_TEXT["jobs"]["kinds"] = {'dev10': '개발용 10건 시험',
 'single': '문서 한 건 시험',
 'probe': '일부 문서 시험',
 'silver': 'AI 정답 초안 만들기',
 'eval': '평가용 기록 · 열람 제한',
 'outside': '새 문서 시험 · 점수 없음',
 'models': '비교표'}

COPY_EXCEPTIONS: dict[str, str] = {'common.expand': '공용 카드의 접힘 조작 이름이 COPY 공통 표에 없어 옛 동작 이름을 유지합니다.',
 'common.collapse': '공용 카드의 펼침 조작 이름이 COPY 공통 표에 없어 옛 동작 이름을 유지합니다.',
 'common.raw_error': '공통 오류 상세의 기존 이름을 유지합니다.',
 'common.todo': 'API 복구 문장을 한 번만 접두어와 함께 표시합니다.',
 'context.model.connected_count': '공통 연결 상태의 필수 모델 수와 이름에 대응하는 COPY 자리표시가 없습니다.',
 'context.model.checked_at': 'STRUCTURE가 요구한 최근 확인 시각의 공통 문구가 없습니다.',
 'context.unavailable': 'API가 값이나 시각을 주지 않을 때 알 수 없음을 표시합니다.'}

COPY_EXCEPTIONS.update({'score.basis.label': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.basis.fallback': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.loading.scoring': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.load_failed.fact': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.load_failed.todo': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.summary.must_progress': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.summary.target_line': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.summary.top_problem': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.summary.open_source': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.summary.unlinked': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.criteria.hidden': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.criteria.score': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.criteria.weight': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.problem.shown': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.problem.show_more': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.problem.empty': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.problem.cause': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.selection.not_comparable': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.selection.unknown': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.selection.other_set': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.history.point': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.history.selected': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.history.plotted': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.history.current_record': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.history.started': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.conditions.progress': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.conditions.running': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.conditions.nonempty_difference': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.conditions.nonempty_meaning': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.calls.scope': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.calls.attempt_info': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.calls.mode': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.calls.limit_reason': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.calculation.weight': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.calculation.loss_formula': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.calculation.weight_basis': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.gaps.title': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.gaps.none': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.gaps.source': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
 'score.gaps.count': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.'})

UI_TEXT["score"]["documents"]["seconds"] = "{seconds}초"
COPY_EXCEPTIONS["score.documents.seconds"] = "문서별 처리 시간의 동적 단위를 표시합니다."

UI_TEXT["score"]["actions"] = {"retest": "이 부분 다시 시험하기"}
UI_TEXT["score"]["problem"]["evidence_unrecorded"] = "AI가 적은 원문 줄이 있는 틀린 값부터 봅니다. 문제 수는 기록이 없습니다."
UI_TEXT["score"]["value_points"] = "{score}점"
COPY_EXCEPTIONS["score.problem.evidence_unrecorded"] = "문제 건수가 없을 때 0이나 추정 건수를 만들지 않는 안내입니다."
COPY_EXCEPTIONS["score.value_points"] = "동적 손실 점수에 단위를 붙입니다."

UI_TEXT["score"]["history"]["scope"] = "모든 문서 묶음의 저장된 실행 이력입니다. 문서 수와 정답 기준을 함께 확인하세요."
COPY_EXCEPTIONS["score.history.scope"] = "API의 이력 요약은 전체 묶음 기준이므로 현재 묶음의 점수와 범위를 구분합니다."

UI_TEXT["source"] = {'value': {'field': '{label}: {value}',
           'true': '예',
           'false': '아니요',
           'wrong': '틀림 · {concentration} mg/m³',
           'missing': '못 뽑음 · {concentration} mg/m³',
           'made': '만듦 · {concentration} mg/m³',
           'context': '{doc} · {component} · {section}번 부분 · 허용 농도',
           'model_label': '{model}가 쓴 값',
           'concentration_label': '공기 속 물질의 허용량(허용 농도)',
           'draft': '정답 초안: {concentration} mg/m³.',
           'draft_warning': '정답 초안도 틀릴 수 있습니다. 값을 믿기 전에 원문과 맞춰 보세요.'},
 'legend': {'same': '정답과 같음',
            'different': '정답과 다르거나 정답에 없음',
            'missing': '정답에만 있음 · AI가 못 뽑음',
            'selected': '선택한 값과 원문 줄'},
 'doc': {'howto': '목록에서 값을 고르면 해당 원문 줄이 선택됩니다. 줄을 고르면 그 줄을 근거로 쓴 값이 선택됩니다.',
         'guess': '정답의 근거 글과 글자가 같은 줄을 찾았습니다. AI가 남긴 근거가 아닌 추정 위치입니다.',
         'no_guess': '정답의 근거 글을 이 묶음에서 찾지 못했습니다. 할 일: 해당 부분의 원문을 직접 읽으세요.',
         'counts': 'AI가 채운 값은 {total}개입니다. 정답과 다른 값은 {different}개입니다. 정답에만 있는 값은 {missing}개입니다.'},
 'fields': {'value': '값',
            'text': '원문 글',
            'refs': '근거 줄',
            'cond': '조건',
            'std_code': '표준 코드',
            'match_score': '맞춤 점수',
            'seq': '순서',
            'key': '이름',
            'raw': '원래 표기',
            'unit': '단위',
            'status': '상태',
            'code': '코드',
            'source_text': '근거 원문',
            'page': '쪽',
            'source': '출처',
            'note': '비고',
            'type': '종류',
            'lower': '최솟값',
            'upper': '최댓값',
            'lower_op': '최솟값 비교 기호',
            'upper_op': '최댓값 비교 기호',
            'approx': '근삿값 여부',
            'dp': '소수 자릿수',
            'cas_no': '물질 식별 번호(CAS)',
            'ke_no': '국내 물질 번호(KE)',
            'comp_ref': '성분 참조'},
 'title': '원문과 AI의 값을 비교하세요.',
 'problem_count': '문서 {count}건에서 찾은 문제 값',
 'unit_first_use': '값을 누르면 원문이 바뀝니다. mg/m³는 공기 1세제곱미터에 든 물질의 양(밀리그램)입니다.',
 'filter': {'all': '전체 {count}건', 'missing': '못 뽑음 {count}', 'made': '만듦 {count}', 'wrong': '틀림 {count}'},
 'wrong': {'title': 'AI가 원문의 {expected}를 {actual}로 잘못 옮겼습니다.',
           'risk': '허용 농도를 높게 적으면 더 많이 노출되어도 안전하다고 오해할 수 있습니다.',
           'count_origin': '앞 화면의 ‘틀림 {count}건’에 속한 값입니다.'},
 'evidence': {'title': '원문에 적힌 줄',
              'location': '{page}쪽 {line_no}번째 줄',
              'recorded': 'AI 결과에 기록된 근거 위치입니다.',
              'range': '원문은 {page}쪽 {first_line}번째 줄부터 {last_line}번째 줄까지입니다.'},
 'retest': {'open': '이 부분 다시 시험하기',
            'target': '다시 시험 화면에 {doc}의 {section}번 부분과 ‘AI에게 시킬 일’ 입력란을 채웁니다.',
            'duration': '시험은 약 {seconds}초~{minutes}분입니다(예시). AI 준비 시간은 별도입니다.',
            'cost': '회사 서버는 추가 임대료가 없습니다. 빌린 서버는 켜 둔 시간만큼 요금이 나갑니다.'},
 'selection': {'expand': '문서와 쪽과 부분 바꾸기',
               'current': '현재 값',
               'dev_doc': '개발용 문서',
               'section': '{section}번 부분 · 노출 방지와 보호구',
               'source_set': '원문 묶음',
               'recorded_set': '실행 당시 묶음 ·',
               'next_set': '다음 시험 묶음',
               'selected_set': '선택 묶음 ·',
               'raw': '실행 없이 원문만 보기',
               'eval_reason': '평가 문서 잠금 이유 보기',
               'restore': '선택한 값과 쪽과 읽던 위치는 돌아올 때 복원합니다.',
               'set_mismatch': '원문과 다음 시험 묶음이 다른 경우 보기',
               'open_gone': '새 결과에서 값이 사라진 경우 보기'},
 'page': {'expand': '원문 그림과 줄 글자 보기',
          'caption': '{doc} · {page}쪽의 글자',
          'no_image': '그림이 없는 경우에도 줄 글자는 남습니다.',
          'no_coordinates': '좌표가 없는 줄은 글자만 확인할 수 있습니다.',
          'section_unknown': '부분의 시작 줄을 못 찾은 경우 보기'},
 'structure': {'expand': '값의 구조와 비교 범위 보기',
               'path': '{section}번 부분 → 노출기준 표 → 행 → 기준 값',
               'raw_path': '원래 경로:',
               'line_ref': '줄 표기:',
               'unit': 'mg/m³는 공기 1세제곱미터에 든 물질의 양(밀리그램)입니다.',
               'doc_comparison': '문서 전체의 비교',
               'filled': 'AI가 채운 값',
               'count_scope': '앞 화면의 {count}건은 문서 {documents}건의 허용 농도 기준에 속합니다.',
               'extras': '표 밖에 남은 값은 {count}개입니다.',
               'unknown_section': '어느 부분인지 모르는 값은 ‘문서 부분 확인 필요’에 남깁니다.'},
 'estimation': {'expand': '정답 값의 추정 줄과 근거 없는 상태',
                'coverage': '이 문서의 정답 값 {total}개 중 {matched}개에서 후보 줄을 찾았습니다.',
                'method': '추정 방식은 글자 맞춤입니다.',
                'count_meaning': '이 수는 정답 전체의 줄 찾기 범위입니다. 못 뽑은 값의 건수와는 다릅니다.',
                'verify': '원문이 맞는지는 직접 확인해야 합니다.',
                'open_unlinked': '근거 줄 없음 보기'},
 'missing': {'title': 'AI가 원문에 있는 값을 옮기지 않았습니다.',
             'evidence_title': '원문 줄(추정)',
             'location': '{page}쪽 {line_no}번째 줄 · 추정 위치',
             'estimated': '정답 내용과 글자가 맞는 줄을 찾았습니다. AI가 남긴 근거는 아닙니다.',
             'risk': '값이 빠지면 작업장 공기 기준을 확인할 수 없습니다.',
             'count_origin': '앞 화면의 ‘못 뽑음 {count}건’에 속한 값입니다.'},
 'made': {'title': 'AI가 원문에 없는 숫자를 넣었습니다.',
          'no_data': '자료 없음',
          'draft': '정답 초안: 자료 없음.',
          'risk': '없는 숫자를 넣으면 확인되지 않은 농도를 안전 기준으로 오해할 수 있습니다.',
          'count_origin': '앞 화면의 ‘만듦 {count}건’에 속한 값입니다.'},
 'unlinked': {'title': '원문 줄을 찾지 못했습니다.',
              'line_absent': 'AI가 적은 줄 번호가 현재 원문에 없습니다.',
              'no_fallback': '다른 줄을 근거로 대신 선택하지 않았습니다.',
              'read_section': '이 부분 원문 읽기',
              'todo': '할 일: {section}번 부분의 원문을 직접 읽으세요. 연결된 근거를 찾기 전에는 안내 완료로 세지 않습니다.'},
 'raw': {'title': '저장된 결과 없이 원문만 보고 있습니다.', 'read_page': '{page}쪽 글자 읽기'},
 'sections': {'product': '제품과 회사',
              'fire': '화재 대처',
              'release': '누출 대처',
              'handling': '취급과 저장',
              'exposure': '노출 방지와 보호구',
              'stability': '안정성과 반응',
              'environment': '환경 영향',
              'other': '그 밖의 정보',
              'hazards': '위험성',
              'first_aid': '응급조치',
              'disposal': '폐기',
              'transport': '운송'},
 'section_unknown': {'title': '{section}번 부분의 시작 줄을 찾지 못했습니다.',
                     'state': '부분 구간 확인 필요',
                     'available': '근거 줄과 값은 볼 수 있습니다. 부분 구간 띠는 표시하지 않습니다.',
                     'open_value': '선택 값과 줄 보기'},
 'value_gone': {'title': '이 값은 새 결과에 없습니다.',
                'returned': '{section}번 부분으로 돌아왔습니다.',
                'path_absent': '{doc}의 새 결과에는 선택했던 값 경로가 없습니다.'},
 'origin': {'run': '실행 당시 묶음',
            'moved': '실행 당시 묶음의 옮겨진 위치',
            'param': '직접 고른 묶음',
            'startup': '앱을 켤 때 지정한 묶음',
            'default': '기본 문서 묶음'},
 'empty': {'pages': '원문 쪽 자료가 없습니다. 할 일: 원문이 있는 문서 묶음을 고르세요.',
           'document': '이 실행이나 묶음에서 문서를 찾지 못했습니다. 할 일: 문서와 묶음을 다시 고르세요.',
           'answer': '이 문서의 정답이 없어 같음과 다름을 비교할 수 없습니다.',
           'problems': '이 채점 기준에 연결된 문제 값이 없습니다. 해당 부분의 원문을 직접 읽으세요.',
           'values': '결과 값이 없습니다.',
           'runs': '저장된 실행이 없습니다. 원문만 보기를 이용하세요.',
           'lines': '이 쪽에는 줄 글자가 없습니다.'},
 'locked': {'title': '보호 때문에 이 문서를 열 수 없습니다.',
            'counts': '개발용 {dev}건, 평가용 잠김 {locked}건, 목록 밖 {outside}건입니다.',
            'unknown': '문서의 용도를 확인할 정보가 없습니다. 문서 목록을 다시 불러오세요.'},
 'load_failed': {'fact': '원문 자료를 불러오지 못했습니다.', 'todo': '할 일: 문서와 묶음을 확인한 뒤 다시 불러오세요.'},
 'loading': '원문 자료를 불러오는 중입니다.',
 'reload': '다시 불러오기',
 'labels': {'run': '실행',
            'doc': '문서',
            'section': '부분',
            'page': '쪽',
            'field': '칸',
            'result': 'AI 결과 값',
            'answer': '정답 값',
            'whole_row': '행 전체',
            'section_name': '{section}번 부분 · {name}',
            'unknown_section': '문서 부분 확인 필요',
            'row': '{row}번째 행',
            'only_row': '정답의 {row}번째 행에만 있는 칸',
            'cells': '{count}칸',
            'page_name': '{page}쪽',
            'image_alt': '{page}쪽 그림',
            'selected': '선택됨',
            'line_values': '연결 값 {count}개',
            'range': '구간 {start} ~ {end}',
            'choose': '값이나 줄을 눌러 보세요.',
            'only_field': '정답에만 있는 칸',
            'matched_count': '정답과 같음 {count}개',
            'criterion': '채점 기준: {item}',
            'problem_scope': '현재 문서의 문제 값 {count}개',
            'return_set': '실행 당시 묶음으로 열기'},
 'kinds': {'wrong': '틀림', 'made': '만듦', 'missing': '못 뽑음', 'same': '정답과 같음', 'uncompared': '정답 없음'},
 'comparison': {'wrong': '이 값은 정답과 다릅니다. 원문과 함께 판단하세요.',
                'made': '정답에 없는 값입니다. 원문에 있는지 확인하세요.',
                'missing': '정답에만 있는 값입니다. 원문과 함께 판단하세요.',
                'same': '이 값은 정답과 같습니다.',
                'uncompared': '이 문서의 정답이 없어 비교하지 않았습니다.'},
 'section_names': {'1': '제품과 회사',
                   '2': '위험성',
                   '3': '구성성분',
                   '4': '응급조치',
                   '5': '화재 대처',
                   '6': '누출 대처',
                   '7': '취급과 저장',
                   '8': '노출 방지와 보호구',
                   '9': '물리화학적 특성',
                   '10': '안정성과 반응',
                   '11': '독성',
                   '12': '환경 영향',
                   '13': '폐기',
                   '14': '운송',
                   '15': '법적 규제',
                   '16': '그 밖의 정보'},
 'table_names': {'meta': '관리정보',
                 'product': '제품',
                 'companies': '회사',
                 'hazard': '유해성',
                 'hazard.classes': '유해성 분류',
                 'hazard.pictograms': '그림문자',
                 'hazard.h_statements': 'H 코드',
                 'hazard.p_statements': 'P 코드',
                 'hazard.other_hazards': '기타 유해성',
                 'composition': '조성',
                 'components': '성분',
                 'narratives': '서술 문장',
                 'exposure_limits': '노출기준',
                 'physchem': '물리·화학 성질',
                 'toxicity': '독성',
                 'cmr': '발암성 등 CMR',
                 'ecotox': '생태 독성',
                 'transport': '운송',
                 'regulations': '규제',
                 'dangerous_goods': '위험물',
                 'waste': '폐기물',
                 'intl_class': '국제 분류',
                 'extras': '표 밖에 남은 값'}}

COPY_EXCEPTIONS.update({'source.origin.run': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.origin.moved': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.origin.param': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.origin.startup': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.origin.default': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.empty.pages': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.empty.document': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.empty.answer': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.empty.problems': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.empty.values': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.empty.runs': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.empty.lines': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.locked.title': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.locked.counts': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.locked.unknown': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.load_failed.fact': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.load_failed.todo': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.loading': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.reload': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.run': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.doc': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.section': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.page': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.field': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.result': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.answer': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.whole_row': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.section_name': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.unknown_section': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.row': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.only_row': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.cells': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.page_name': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.image_alt': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.selected': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.line_values': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.range': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.choose': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.only_field': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.matched_count': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.criterion': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.problem_scope': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.labels.return_set': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.kinds.wrong': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.kinds.made': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.kinds.missing': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.kinds.same': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.kinds.uncompared': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.comparison.wrong': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.comparison.made': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.comparison.missing': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.comparison.same': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.comparison.uncompared': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.1': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.2': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.3': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.4': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.5': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.6': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.7': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.8': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.9': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.10': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.11': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.12': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.13': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.14': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.15': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.section_names.16': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.meta': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.product': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.companies': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.hazard': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.hazard.classes': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.hazard.pictograms': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.hazard.h_statements': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.hazard.p_statements': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.hazard.other_hazards': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 '
                                            '보충했습니다.',
 'source.table_names.composition': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.components': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.narratives': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.exposure_limits': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.physchem': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.toxicity': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.cmr': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.ecotox': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.transport': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.regulations': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.dangerous_goods': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.waste': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.intl_class': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.',
 'source.table_names.extras': '원문 전체를 위한 동적 조작과 상태 또는 옛 항·표 이름을 보존합니다. COPY에 일반형 문구가 없어 보충했습니다.'})

UI_TEXT["compare"] = {'headline': {'none': '비교할 기준별 점수가 없습니다.',
              'unscored': 'B({b})와 A({a})의 전체 점수를 비교할 수 없습니다.',
              'equal': 'B({b})와 A({a})의 전체 점수가 같습니다.',
              'lower': 'B({b})가 A({a})보다 {gap}점 낮습니다.',
              'higher': 'B({b})가 A({a})보다 {gap}점 높습니다.',
              'biggest': '가장 크게 달라진 기준은 {item}입니다. 점수 차이는 {delta}점입니다.',
              'below_best': '최근 결과는 지난 최고점보다 {gap}점 낮습니다.',
              'decreased': '이전 결과보다 점수가 {gap}점 낮아졌습니다.'},
 'conditions': {'same': '비교 조건이 모두 같습니다.',
                'changed': '달라진 조건: {condition}',
                'variation': '같은 조건을 반복할 때 생긴 차이일 수 있습니다.',
                'prompt_text': 'AI에게 시킨 글',
                'title': '비교 조건',
                'unknown': '비교 조건의 일치 여부를 확인할 수 없습니다.',
                'key_unknown': '기록 당시 기준 미확인',
                'prompt_sections': 'AI에게 시킨 글이 다른 부분: {sections}',
                'metadata_missing': '일부 조건이 기록되지 않았습니다. 빈 기록이 같은 조건임을 입증하지는 않습니다.',
                'labels': {'모델': 'AI 모델',
                           '안내문 버전': 'AI에게 시킨 일의 버전',
                           '입력 판': '원문 글자 묶음',
                           '동시 호출': '동시에 보내는 요청 수',
                           '코드 커밋': '프로그램 코드 확인값'}},
 'items': {'hidden': '점수가 내려가지 않았거나 없는 기준 {count}개를 숨겼습니다.',
           'empty': '점수가 내려간 기준이 없습니다. 할 일: 모두 보기에서 다른 기준을 확인하세요.',
           'candidate': '원인은 아직 추정입니다. 할 일: 원문과 값을 맞춰 확인하세요.',
           'show_drops': '내려간 것만 보기',
           'show_all': '모두 보기',
           'show_causes': '원인 후보 보기',
           'no_cause': '원인 후보 없음',
           'sort': '항목 정렬',
           'sort_down': '내려간 차이가 큰 순',
           'sort_up': '올라간 차이가 큰 순',
           'sort_name': '이름순',
           'sections': '관련 부분: {sections}',
           'section': '{section}번',
           'name': '채점 기준',
           'delta': '점수 차이 (B − A)'},
 'result_a': '결과 A',
 'result_b': '결과 B',
 'total_score': '전체 점수',
 'score_value': '{score} / 100점',
 'target': '목표 점수',
 'below_target': '{line}점보다 {gap}점 낮음',
 'must': '필수 기준',
 'must_met': '{met}/{total}가지 목표 달성',
 'common_docs': '공통 문서',
 'dev_count': '개발용 {count}건',
 'recalculated': '두 결과의 점수는 현재 선택한 정답으로 다시 계산했습니다.',
 'open_wrong': '새로 틀린 값의 원문 보기',
 'selection': {'expand': '실행 선택과 순서 바꾸기',
               'swap': 'A와 B 순서 바꾸기',
               'open_different': '문서 구성이 다른 비교 보기',
               'choose_two': '비교할 실행 A와 B를 고르세요.',
               'choose': '실행 고르기',
               'reasons': {'single': '문서 한 건 시험이므로 전체 실행 비교 대상이 아닙니다.',
                           'probe': '일부 문서 시험이므로 전체 실행 비교 대상이 아닙니다.',
                           'outside': '새 문서 시험에는 채점할 정답이 없습니다.',
                           'silver': '정답 생성 실행은 비교 대상이 아닙니다.',
                           'eval': '평가용 기록은 개발 과정에서 열 수 없습니다.',
                           'models': '비교표 파일에는 개별 추출 결과가 없습니다.',
                           'unknown': '전체 실행 비교 대상이 아닙니다. 실행 종류와 채점 범위를 확인하세요.'},
               'partial': '실행 기록 {count}개를 읽지 못했습니다.'},
 'detail': {'expand': '비교 조건과 항목별 차이와 AI에게 시킬 일',
            'result_a': '결과 A · 먼저 비교',
            'run': '{time} · {model} · {score}점',
            'result_b': '결과 B · 나중에 비교',
            'common_count': '같은 문서 {count}건으로 비교했습니다.',
            'only_a': 'A에만 있는 문서는 {count}건입니다.',
            'only_b': 'B에만 있는 문서도 {count}건입니다.',
            'both_below': '두 결과 모두 전체 목표 점수 {line}점 아래입니다.',
            'basis': '비교 기준',
            'must_met': '필수 17개 중 목표 이상',
            'nonempty_score': '빈 행 제외 보조 점수',
            'pages': '문서 자료',
            'concurrency': '동시에 보내는 요청',
            'code': '코드 기록',
            'example_answer': '예시 답안'},
 'interpretation': {'title': '조건과 점수의 해석',
                    'loading': '비교 결과를 읽는 중에는 ‘두 결과를 비교하고 있습니다’를 표시합니다.',
                    'keep_selection': '비교를 읽지 못하면 고른 A와 B를 유지합니다.',
                    'retry': '‘비교 결과를 다시 불러오기’로 재시도합니다.',
                    'changed_prompt': '바뀐 조건은 AI에게 준 AI에게 시킨 일입니다.',
                    'causality': 'AI에게 시킬 일 변경만으로 점수 차이가 생겼다고 확정하지 않습니다.',
                    'same': '조건이 모두 같으면 ‘같은 조건의 반복’으로 표시합니다.',
                    'common_first': '문서 구성이 다르면 공통 문서부터 확인합니다.',
                    'key_unknown': '정답 기준을 확인할 수 없으면 ‘기록 당시 기준 미확인’으로 표시합니다.'},
 'criteria': {'title': '항목별 차이 · 23개',
              'direction': 'A → B',
              'increased': '높아짐 · 원인은 미확정',
              'decreased': '낮아짐 · 원인은 미확정',
              'exposure': '작업장 공기 중 허용 농도 (8번 부분 · 노출기준(작업장 공기 기준))',
              'hidden_count': '하락한 항목만 보는 경우 숨긴 수를 함께 표시합니다.',
              'cause_threshold': '{gap}점 이상 내려간 항목에는 원인 후보를 제시합니다.',
              'no_cause': '확인할 근거가 없으면 ‘원인 후보 없음’입니다.',
              'same': '같음',
              'unknown': '점수 확인 안 됨',
              'delta': '차이 {delta}점',
              'title_count': '항목별 차이 · {count}개'},
 'prompt': {'title': 'AI에게 시킨 일의 차이',
            'lines_a': '{section}번 부분 설명: A는 {count}줄입니다.',
            'lines_b': 'B는 {count}줄입니다.',
            'changed_line': '바뀐 줄: “{prompt_line}”',
            'format': '답변 형식은 두 결과 모두 표입니다.',
            'hash_warning': '이 설명을 다시 만든 확인값(해시)이 기록과 다르면 경고합니다.',
            'full_text': '설명 전문은 화면에서만 읽습니다.',
            'open': '{section}번 부분의 지시문 차이 보기',
            'loading': '{section}번 부분의 지시문을 다시 만드는 중입니다. 몇 초 걸릴 수 있습니다.',
            'failed': '지시문 차이를 읽지 못했습니다.',
            'todo': '할 일: 다시 불러오세요. 계속 실패하면 실행 당시 코드 기록이 있는지 확인하세요.',
            'retry': '지시문 차이 다시 불러오기',
            'rows': '표 행 형식',
            'json': '항목 형식(JSON)',
            'form': '{side} 답변 형식: {format}',
            'same': '두 지시문이 같습니다.',
            'hashes': '{side} 기록 확인값: {recorded} → 복원 확인값: {restored}',
            'legend': '−는 A에만 있는 줄입니다. +는 B에만 있는 줄입니다.',
            'note': '부분을 펼칠 때만 당시 지시문을 다시 읽습니다.'},
 'values': {'title': '바뀐 값과 표 행 수',
            'correct_count': '새로 맞춘 값 {total}개 중 {shown}개를 표시합니다.',
            'product': '{doc} · 제품 이름: {before} → {after}.',
            'company': '{doc} · 회사 이름: {before} → {after}.',
            'wrong_count': '새로 틀린 값 {total}개 중 {shown}개를 표시합니다.',
            'scope': '공통 문서의 필수 항목 상세에서 찾은 값입니다.',
            'exposure': '{doc}의 허용 농도: {before} mg/m³ → {after} mg/m³.',
            'open_source': '이 값의 원문 보기',
            'expand': '바뀐 값 펼치기',
            'same': '두 실행의 틀린 값 목록이 같습니다.',
            'fixed': '새로 맞춘 값 {count}개',
            'broken': '새로 틀린 값 {count}개',
            'more': '값 {count}개 더 보기',
            'kind': '문제 종류',
            'content': '기록된 내용',
            'path_missing': '정확한 값 위치가 기록되지 않았습니다. 해당 부분에서 값을 골라 확인하세요.',
            'unlinked': '관련 부분이 기록되지 않아 원문으로 바로 이동할 수 없습니다.',
            'definitions': '새로 맞춘 값은 A의 오류 목록에서 사라진 값입니다. 새로 틀린 값은 B의 오류 목록에 생긴 값입니다.'},
 'table': {'title': '여러 결과를 한 비교표로 만들기',
           'column_order': '선택한 순서대로 표의 열이 만들어집니다.',
           'caption': '표 제목',
           'name_a': '결과 A의 표시 이름',
           'before': '수정 전',
           'name_b': '결과 B의 표시 이름',
           'after': '수정 후',
           'selection_summary': '선택 {count}개 · 각 결과의 점수를 매긴 문서 {documents}건 · 비교 가능',
           'reload': '결과 목록 새로 불러오기',
           'create_ordered': '선택한 순서로 비교표 만들기',
           'open_job': '만든 비교표의 작업 기록 보기',
           'default_name': '기본 표시 이름은 실행 이름입니다.',
           'result_path': '결과 파일:',
           'open_title': '여러 실행을 한 표로 모으기',
           'open': '비교표 만들기'},
 'swapped': {'title': 'B는 A보다 {gap}점 높습니다.', 'order': '선택 순서', 'swap_again': 'A와 B 순서 다시 바꾸기'},
 'different': {'title': '두 실행의 점수를 매긴 문서 구성이 다릅니다.',
               'common_first': '공통 문서부터 확인하세요.',
               'counts': 'A에만 {only_a}건이 있습니다. B에만 {only_b}건이 있습니다. 공통은 {common}건입니다.',
               'open_common': '공통 문서 확인하기',
               'no_inference': '각 실행의 전체 평균 차이만으로 개선을 단정하지 않습니다.',
               'conditions': '조건 차이 보기',
               'set': '자료 묶음',
               'prompt': '설명 버전',
               'concurrency': '동시 호출 수',
               'code': '코드 확인값'},
 'common': {'title': '공통 개발 문서 {count}건을 비교합니다.',
            'scope': '비교 범위',
            'values_scope': '두 결과에 모두 있는 문서만 바뀐 값 비교에 사용합니다.',
            'back': '두 결과 비교로 돌아가기'},
 'same': {'title': '같은 조건을 반복한 두 결과입니다.',
          'variation': '실행마다 생기는 차이일 가능성이 있습니다.',
          'no_inference': '점수 변화만으로 설명 수정의 효과라고 판단하지 않습니다.',
          'open_items': '항목별 차이 보기'},
 'hash_mismatch': {'title': '지금 복원한 설명이 실행 기록과 다릅니다.',
                   'state': '설명 확인 필요',
                   'todo': '기록의 확인값과 다릅니다. 할 일: 당시 보낸 글인지 작업 기록에서 확인하세요.',
                   'back': '비교 조건으로 돌아가기'},
 'builder': {'title': '고른 순서대로 결과를 한 표에 모으세요.',
             'display_name': '표시 이름',
             'conditions': '조건과 점수를 매긴 범위',
             'first_name': '첫째 이름',
             'scope': '이전 개발 자료. 같은 정답. 개발용 {count}건. 비교 가능.',
             'second_name': '둘째 이름',
             'disabled': '선택 불가',
             'answer_run': '정답 생성 기록',
             'answer_excluded': '정답 생성 실행은 비교 대상 아님.',
             'selected_count': '선택한 결과는 {count}개입니다.',
             'selection_output': '선택과 출력 위치',
             'swap': '두 실행의 순서 바꾸기',
             'reload': '실행 목록 다시 읽기',
             'empty_name': '이름을 비워 두면 실행 이름을 씁니다.',
             'path': '파일 위치:'},
 'builder_swapped': {'title': '최근 결과를 첫 번째 열로 옮겼습니다.',
                     'order': '열 순서',
                     'latest': '최근 결과 · {score}점',
                     'best': '지난 최고점 · {score}점',
                     'create': '이 순서로 비교표 만들기'},
 'builder_running': {'title': '두 실행으로 비교표를 만들고 있습니다.',
                     'state': '표 생성 중',
                     'no_model': '모델을 새로 부르지 않습니다.',
                     'open_output': '완성된 비교표 위치 보기'},
 'builder_done': {'title': '두 실행의 비교표를 만들었습니다.', 'columns': '표의 열'},
 'side_a': 'A',
 'side_b': 'B',
 'loading': '두 결과를 비교하고 있습니다.',
 'reload': '비교 결과를 다시 불러오기',
 'load_failed': {'fact': '두 결과의 비교를 읽지 못했습니다.', 'todo': '할 일: 비교 결과를 다시 불러오세요. 계속 실패하면 앱을 켠 터미널의 오류를 확인하세요.'},
 'rows': {'title': '표 행 수 차이',
          'unit': '{count}행',
          'closer': '정답 행 수에 가까워짐',
          'farther': '정답 행 수에서 멀어짐',
          'same': '정답 행 수와의 차이 유지',
          'unknown': '정답과의 거리 확인 안 됨',
          'table': '표',
          'answer': '현재 정답',
          'distance': '정답 행 수와의 거리',
          'hint': 'A와 B와 현재 정답의 표 행 수입니다. 행 수가 같아도 값은 다를 수 있습니다.'},
 'target_line': '목표선 {line}점',
 'basis': '점수 기준: {key}',
 'unknown': '확인 안 됨'}

COPY_EXCEPTIONS.update({'compare.selection.choose_two': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.selection.choose': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.selection.reasons.single': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.selection.reasons.probe': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.selection.reasons.outside': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.selection.reasons.silver': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.selection.reasons.eval': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.selection.reasons.models': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.selection.reasons.unknown': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.selection.partial': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.loading': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.reload': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.load_failed.fact': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.load_failed.todo': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.conditions.title': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.conditions.unknown': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.conditions.key_unknown': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.conditions.prompt_sections': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.conditions.metadata_missing': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.conditions.labels.모델': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.conditions.labels.안내문 버전': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.conditions.labels.입력 판': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.conditions.labels.동시 호출': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.conditions.labels.코드 커밋': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.criteria.same': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.criteria.unknown': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.criteria.delta': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.criteria.title_count': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.items.show_drops': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.items.show_all': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.items.show_causes': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.items.no_cause': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.items.sort': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.items.sort_down': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.items.sort_up': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.items.sort_name': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.items.sections': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.items.section': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.items.name': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.items.delta': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.values.expand': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.values.same': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.values.fixed': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.values.broken': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.values.more': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.values.kind': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.values.content': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.values.path_missing': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.values.unlinked': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.values.definitions': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.rows.title': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.rows.unit': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.rows.closer': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.rows.farther': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.rows.same': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.rows.unknown': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.rows.table': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.rows.answer': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.rows.distance': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.rows.hint': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.prompt.open': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.prompt.loading': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.prompt.failed': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.prompt.todo': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.prompt.retry': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.prompt.rows': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.prompt.json': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.prompt.form': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.prompt.same': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.prompt.hashes': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.prompt.legend': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.prompt.note': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.target_line': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.basis': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.',
 'compare.unknown': '비교의 동적 조작·단위·API 누락 상태와 기존 정보 보존을 위한 일반 문구를 보충합니다.'})


# app-redo step 5: 승인된 모델 연결 문구. 설계 파일은 실행 시 읽지 않습니다.
UI_TEXT["servers"] = {'confirm': {'load': {'title': '회사 서버에서 {model}를 켤까요?',
                      'target': '{model}. 계산 부품 {count}장. 한 번에 모델 하나.',
                      'cost': '추가 임대료 없음. 준비 15~25분.',
                      'action': '확인하고 모델 켜기'},
             'create': {'title': '요금을 내고 새 서버를 만들까요?',
                        'target': '{model}. 기존 서버가 있으면 비용이 추가됩니다.',
                        'cost': '켜진 동안 시간당 약 ${cost_per_hour}가 듭니다(예시). 준비 완료 시각은 모릅니다. 사용 뒤 삭제하세요. 앱이 만든 '
                                '서버는 생성 후 4시간에 자동 삭제됩니다. 앱이 켜져 있어야 예약을 확인합니다.',
                        'action': '요금을 확인하고 서버 만들기'},
             'delete': {'title': '서버 {server}을 삭제할까요?',
                        'target': '{pod_id}. 이 앱이 만든 서버입니다. 진행 작업은 없습니다.',
                        'cost': '가동 {hours}시간. 추정 비용 ${cost}. 별도 저장공간 비용은 남을 수 있습니다.',
                        'action': '서버 {server} 삭제하기'},
             'unload': {'title': '회사 서버의 모델을 끌까요?',
                        'target': '{model}. 진행 중인 작업은 없습니다.',
                        'effect': '모델을 끈 뒤 새 모델을 켤 수 있습니다.',
                        'action': '확인하고 모델 끄기',
                        'model_title': '{model}를 끌까요?',
                        'no_jobs': '진행 중인 작업은 없습니다.',
                        'no_trial': '모델을 끄면 새 시험을 보낼 수 없습니다.'},
             'tunnel_open': {'title': '회사 서버로 가는 연결 통로를 열까요?',
                             'effect': '이 컴퓨터에서 회사 모델에 요청을 전달하는 길을 엽니다.',
                             'allowed': '모델을 새로 올리는 작업은 아닙니다. 진행 중에도 열 수 있습니다.',
                             'action': '확인하고 연결 열기',
                             'no_load': '모델을 켜는 작업은 아닙니다.'},
             'tunnel_close': {'title': '회사 서버로 가는 연결 통로를 닫을까요?',
                              'state': '진행 작업은 없습니다. 현재 켜진 모델은 없습니다.',
                              'effect': '닫으면 이 컴퓨터에서 시험을 보낼 수 없습니다.',
                              'action': '확인하고 연결 닫기'},
             'batch': {'title': '여러 문서 시험에 쓸 서버를 확인하세요.',
                       'target': '개발용 {count}건. 반복 {repeats}회. {model}.',
                       'cost': '빌린 서버를 쓰면 시간당 약 ${cost_per_hour}입니다(예시).',
                       'action': '확인하고 시험 시작하기'},
             'summary': '실행할 내용',
             'once': '이 확인 화면에서는 한 번만 실행할 수 있습니다.',
             'expires': '{time}까지 한 번만 실행할 수 있습니다. 시간이 지나면 확인 화면을 다시 여세요.',
             'cancel': '취소하고 돌아가기',
             'conditions': '실행할 수 있는 조건 보기',
             'recheck': '실행 직전에 상태와 권한을 다시 확인합니다.',
             'changed_state': '상태가 바뀌면 이전 확인으로 실행하지 않습니다.',
             'open_expired': '실행 시간이 지난 경우 보기',
             'open_busy': '진행 작업 때문에 잠긴 경우 보기',
             'expired': {'not_executed': '아직 실행하지 않았습니다.',
                         'reload': '상태 다시 읽기',
                         'fact': '확인 유효시간이 지났습니다. 아직 실행하지 않았습니다.',
                         'todo': '할 일: 상태를 다시 읽고 실행 요약을 다시 여세요.'},
             'expires_once': '{time}까지 한 번만 실행할 수 있습니다(예시). 시간이 지나면 확인 화면을 다시 여세요.',
             'warning': '주의할 내용',
             'no_expiry': '확인 유효시간을 알 수 없어 실행할 수 없습니다.'},
 'diagnosis': {'ready': {'fact': '회사 서버의 AI 모델이 응답했습니다.', 'todo': '다시 시험에서 이 모델을 고르세요.'},
               'no_model': {'fact': '회사 서버에 켜진 AI 모델이 없습니다.', 'todo': '할 일: 모델을 켜세요. 준비에는 보통 15~25분 걸립니다.'},
               'tunnel_closed': {'fact': '회사 서버로 가는 연결 통로(SSH 터널)가 닫혀 있습니다.', 'todo': '할 일: 연결 통로를 여세요.'},
               'loading': {'elapsed': 'AI 모델을 켜고 있습니다. {minutes}분 지났습니다.',
                           'unknown': 'AI 모델을 켜고 있습니다. 시작 시각은 확인하지 못했습니다.',
                           'todo': '보통 15~25분 걸립니다. 기다리는 동안 저장된 결과를 읽을 수 있습니다.',
                           'late': '{minutes}분을 넘겼습니다. 할 일: 서버 기록을 확인하세요.',
                           'log': '회사 서버 기록 위치: /root/to21-bc/{tag}.log'}},
 'controls': {'busy': '시험 중에는 서버를 바꿀 수 없습니다. 할 일: 작업이 끝난 뒤 다시 확인하세요.',
              'create': '빌린 서버 목록을 확인하지 못해 새 서버를 만들 수 없습니다. 할 일: 서버 상태를 다시 확인하세요.',
              'delete': '빌린 서버 목록을 확인하지 못해 삭제할 수 없습니다. 할 일: 서버 상태를 다시 확인하세요.',
              'up': '회사 서버 상태를 확인하지 못해 AI를 켤 수 없습니다. 할 일: 서버 상태를 다시 확인하세요.',
              'down': '회사 서버 상태를 확인하지 못해 AI를 끌 수 없습니다. 할 일: 서버 상태를 다시 확인하세요.',
              'no_ssh': '회사 서버 접속 설정(RNGD_SSH)이 없습니다. 할 일: 설정 파일에서 준비하세요.',
              'no_port': '회사 모델 주소가 내 컴퓨터 쪽 주소가 아닙니다. 할 일: RNGD_BASE_URL 설정을 확인하세요.',
              'open': '연결 통로가 이미 열려 있습니다.',
              'closed': '연결 통로가 이미 닫혀 있습니다.',
              'not_owned': '이 앱이 연 연결이 아닙니다. 할 일: 연결을 연 터미널에서 닫으세요.'},
 'status': {'guide': 'AI 켜기와 비용에서 모델을 준비하세요.',
            'busy': '서버를 바꾸고 있습니다. 끝날 때까지 기다리세요.',
            'unavailable': '서버 상태를 확인하지 못해 변경을 막았습니다. 할 일: 상태를 다시 확인하세요.',
            'failure': {'fact': '서버 변경을 마치지 못했습니다.', 'todo': '할 일: 오류 기록에서 연결 상태와 진행 중인 작업을 확인하세요.'}},
 'messages': {'pod_key_missing': '빌린 모델의 접속 키가 설정되지 않았습니다. 할 일: 설정 파일의 RUNPOD_VLLM_API_KEY를 채운 뒤 설정 다시 읽기를 '
                                 '누르세요.',
              'pod_not_ours': '이 앱이 만든 서버가 아니라 삭제할 수 없습니다. 할 일: 서버 주인에게 확인하세요.',
              'env_file_unknown': '설정 파일의 위치를 찾지 못했습니다. 할 일: 앱을 다시 켜세요.',
              'tunnel_no_port': '회사 모델 주소가 내 컴퓨터 쪽 주소가 아닙니다. 할 일: RNGD_BASE_URL을 확인한 뒤 설정을 다시 읽으세요.',
              'tunnel_already_open': '내 컴퓨터의 {port}번 연결이 이미 열려 있습니다. 할 일: 모델이 응답하는지 확인하세요.',
              'tunnel_closed': '내 컴퓨터의 {port}번 연결이 닫혀 있습니다. 할 일: 서버 상태를 다시 확인하세요.',
              'tunnel_not_ours': '내 컴퓨터의 {port}번 연결은 이 앱이 열지 않았습니다. 할 일: 연결을 연 터미널에서 닫으세요.',
              'tunnel_exited': '보안 연결 프로그램이 통로를 열기 전에 끝났습니다. 종료 코드는 {code}입니다. 할 일: RNGD_SSH 설정과 키 파일을 '
                               '확인하세요.',
              'tunnel_timeout': '연결 통로가 {seconds}초 안에 열리지 않았습니다. 할 일: 터미널에서 회사 서버에 접속되는지 확인하세요.',
              'tunnel_spawn_failed': '보안 연결 프로그램을 시작하지 못했습니다. 할 일: 터미널에서 ssh 명령을 쓸 수 있는지 확인하세요.',
              'tunnel_still_open': '닫기를 요청한 {port}번 연결이 아직 열려 있습니다. 할 일: 잠시 뒤 서버 상태를 다시 확인하세요.'},
 'choice': {'recommendation': '추가 임대료 없는 회사 서버를 권합니다.',
            'company': '추천 · 회사 서버(RNGD)',
            'rented': '다른 방법 · 빌린 서버(RunPod)'},
 'compare': {'cost': '추가 임대료',
             'wait': '준비 시간',
             'limits': '사용 제한과 정리',
             'company': {'wait': '15~25분',
                         'limit': '한 번에 모델 하나',
                         'cost_meaning': '추가 임대료가 없다는 뜻입니다. 회사 장비의 운영비까지 없다는 뜻은 아닙니다.'},
             'rented': {'cost': '시간당 약 ${cost_per_hour} (예시)',
                        'wait': '준비 시간은 매번 다릅니다. 준비 중에는 기다린 시간을 보여 줍니다.',
                        'cleanup': '사용 뒤 삭제하세요. 앱이 만든 서버는 생성 후 4시간에 자동 삭제됩니다.'}},
 'company': {'connected': '회사 서버로 가는 연결 통로는 열려 있습니다.',
             'off': '이 서버의 AI는 꺼져 있습니다. 켜는 데 보통 15~25분 걸립니다.',
             'confirm_load': '{model} 켜기 확인하기',
             'read_while_waiting': '기다리는 동안 저장된 결과를 읽을 수 있습니다.',
             'return_target': '돌아갈 대상: {doc} · {section}번 부분.',
             'alternative': '다른 방법',
             'rented_fallback': '회사 서버를 쓸 수 없으면 빌린 서버를 확인하세요.',
             'open_rented': '기존 임대 서버와 비용 보기'},
 'connection': {'title': '컴퓨터 연결과 모델 응답 확인',
                'item': '확인 항목',
                'selected': '선택한 모델',
                'last_check': '마지막 확인',
                'received_at': '{time} · 이 컴퓨터가 응답을 받은 시각',
                'expected': '기대한 모델',
                'responding': '응답한 모델',
                'unknown': '아직 확인되지 않음',
                'address': '주소 설정',
                'configured': '설정됨. 실제 주소와 키는 표시하지 않음',
                'ready_condition': '기대한 모델의 응답이 와야 준비 완료입니다.',
                'details': '장비 상세와 설정 이름',
                'ssh_meaning': '다른 컴퓨터에 암호화된 명령을 보내는 방법이 보안 접속(SSH)입니다.',
                'tunnel_meaning': 'AI 요청을 전달하는 연결 통로가 SSH 터널입니다.',
                'devices': '계산 부품은 {count}장입니다. 한 번에 모델 하나를 올립니다.',
                'tunnel_owned': '통로: 열림. 포트 {port}. 이 앱이 열었습니다.',
                'no_process': '모델 프로세스는 없습니다. 사용 중인 계산 부품은 {count}장입니다.',
                'reload': '설정 다시 읽기',
                'confirm_close': '연결 닫기 확인하기',
                'tunnel_closed': '통로: 닫힘. 포트 {port}.',
                'tunnel_external': '통로: 열림. 포트 {port}. 이 앱이 연 연결이 아닙니다.',
                'tunnel_unknown': '연결 통로의 포트 설정을 확인하지 못했습니다.',
                'tunnel_time_unknown': '연결 통로를 연 시각은 확인하지 못했습니다.',
                'process': '프로세스 번호: {pid}',
                'processes': '실행 중인 모델과 장비 출력',
                'choose': '회사 서버에서 켤 모델 고르기',
                'choice': '{model} · 계산 부품 {cards}장',
                'none': '현재 확인된 모델 프로세스가 없습니다.',
                'loading_locked': '모델을 준비하고 있어 중복으로 켜지 않습니다.',
                'replace_locked': '다른 모델을 켜려면 지금 켜진 모델을 먼저 끄세요.'},
 'logs': {'summary': '서버 기록 · 최근 {limit}줄 중 기록 {count}줄',
          'path': 'runs/manual/server_log.md',
          'redaction': '명령 출력의 비밀값은 가립니다.',
          'manual_record': '운영용 수동 기록에도 사용 내역을 옮겨 둡니다.',
          'empty': '아직 서버 기록이 없습니다.',
          'manual_copy': '새 기록은 docs/plan/RunPod_사용기록.md에 손으로 옮기세요.'},
 'ready': {'title': '{model}가 준비됐습니다.',
           'expected': '기대한 모델이 응답했습니다.',
           'company_cost': '회사 서버를 사용합니다. 추가 임대료는 없습니다.',
           'return_trial': '시험으로 돌아가기',
           'target_preserved': '{doc}의 {section}번 부분을 그대로 보관했습니다.',
           'prompt_preserved': '편집 중 설명도 같은 화면 메모리에 남습니다.',
           'check': '응답 확인',
           'checked_at': '마지막 확인: {time}.',
           'expected_model': '기대한 모델: {model}.',
           'responding_model': '응답한 모델: {model}.',
           'confirm_unload': '모델 끄기 확인하기'},
 'rented': {'title': '기존 빌린 서버를 이어 쓰고 있습니다.',
            'responded': '{model}가 응답했습니다.',
            'adopted': '앱이 만든 예시 서버 {server}을 자동으로 이어받았습니다.',
            'cost': '실제 요금이 나갑니다: 시간당 약 ${cost_per_hour} (예시).',
            'estimated_cost': '가동 {hours}시간의 추정 비용은 ${cost}입니다.',
            'deletion_hours': '생성 후 4시간에 자동 삭제합니다. 지금은 {hours}시간 남았습니다.',
            'scheduler': '앱이 켜져 있어야 예약된 삭제를 확인합니다.',
            'list_storage': '서버 목록과 저장공간 비용',
            'ownership': '소유와 상태',
            'uptime': '가동 시간',
            'hourly_rate': '시간당 요금',
            'total_cost': '추정 비용',
            'owned_running': '앱이 만듦. 실행 중.',
            'confirm_delete': '삭제 확인하기',
            'external_stopped': '앱이 만든 서버 아님. 정지됨.',
            'unknown': '알 수 없음',
            'delete_forbidden': '삭제 권한 없음',
            'estimate_warning': '추정 비용은 최종 청구액과 다를 수 있습니다.',
            'unknown_cost': '확인하지 못한 비용을 무료로 표시하지 않습니다.',
            'volumes': '별도 저장공간(네트워크 볼륨)은 {count}개입니다.',
            'storage_cost': '저장공간은 서버 삭제 뒤에도 비용이 남을 수 있습니다.',
            'use_company': '회사 서버 사용하기',
            'confirm_create': '새 서버 요금 확인하기',
            'adoption_details': '모델과 인계 확인',
            'expected_reply': '기대한 모델과 응답한 모델은 {model}입니다.',
            'adopted_id': '자동 인계된 번호는 {pod_id}입니다.',
            'other_id': '다른 서버 번호는 {pod_id}입니다.',
            'no_manual_adoption': '임의 서버를 고르는 인계 단추는 제공하지 않습니다.',
            'title_list': '빌린 서버와 비용(RunPod)',
            'identity': '서버 이름과 번호',
            'owned': '이 앱이 만든 서버',
            'state': '상태: {state}',
            'no_delete': '지금은 삭제할 수 없습니다. 할 일: 서버 상태와 진행 작업을 확인하세요.',
            'volume_unknown': '별도 저장공간의 수를 확인하지 못했습니다.',
            'hourly': '${cost}/시간'},
 'creating': {'title': '새 빌린 서버에서 {model}를 켜고 있습니다.',
              'elapsed': '{minutes}분 경과',
              'last_check': '완료될 시각은 아직 모릅니다. 마지막 확인은 {time}입니다.',
              'read_results': '기다리는 동안 최근 결과 보기',
              'estimated_cost': '가동 {minutes}분의 추정 비용은 약 ${cost}입니다.',
              'deletion_remaining': '생성 후 4시간에 자동 삭제합니다. {hours}시간 {minutes}분 남았습니다.',
              'cost_running': '준비 중인 시간에도 요금이 나갑니다.',
              'target': '보관한 시험: {doc} · {section}번 부분.',
              'details': '서버와 준비 상태',
              'server_id': '새로 만든 번호: {pod_id}.',
              'no_reply': '앱이 만든 서버입니다. 아직 모델 응답이 없습니다.',
              'open_ready': '준비 완료 상태 보기',
              'open_company': '회사 서버 확인하기'},
 'deleting': {'title': '예시 서버 {server}의 삭제를 확인하고 있습니다.',
              'requested': '삭제 요청을 보냈습니다.',
              'cost': '삭제 완료가 확인되기 전에는 요금이 계속 나갈 수 있습니다.',
              'refresh': '삭제 결과 확인하기',
              'uptime': '마지막 확인 가동 시간: {hours}시간.',
              'estimated_cost': '마지막 확인 추정 비용: ${cost}.',
              'no_resend': '같은 삭제 요청을 다시 보내지 않습니다.'},
 'deleted': {'title': '예시 서버 {server}을 삭제했습니다.',
             'external_remaining': '남은 서버는 앱이 만들지 않은 예시 서버 {server}입니다.',
             'no_permission': '이 서버에는 삭제 권한이 없습니다.',
             'estimated_cost': '마지막 추정 비용은 ${cost}입니다. 최종 청구액은 아닙니다.',
             'storage_cost': '별도 저장공간이 남으면 그 비용은 계속 나갈 수 있습니다.',
             'prepare': '다시 시험할 모델 준비하기'},
 'empty': {'title': '이어 쓸 빌린 서버가 없습니다.',
           'count': '서버 목록 {count}개',
           'new_cost': '새 서버를 만들면 시간당 실제 요금이 발생합니다.',
           'recommendation': '추천 방법',
           'open_company': '회사 서버 먼저 확인하기'},
 'failed': {'title': '모델 상태를 확인하지 못했습니다.',
            'stale': '마지막 상태를 현재 상태로 쓰지 않습니다.',
            'todo': '서버 변경은 잠시 막았습니다. 할 일: 상태를 다시 확인하세요.',
            'retry': '다시 확인하기',
            'target': '대상은 {doc}의 {section}번 부분으로 유지합니다.',
            'error': '조회 오류',
            'no_reply': '서버 상태 요청에 응답이 없었습니다.',
            'no_inference': '준비됨이나 모델 없음으로 추정하지 않습니다.'},
 'checking': {'title': '모델의 응답을 확인하고 있습니다.',
              'wait': '확인이 끝날 때까지 기다리세요.',
              'state': '상태 확인 중',
              'results': '확인 결과 상태 보기',
              'open_ready': '준비된 모델 보기',
              'open_failed': '조회 실패 보기'},
 'busy': {'title': '시험 중에는 모델을 바꿀 수 없습니다.',
          'running': '{doc} 시험이 진행 중입니다.',
          'restricted': '모델 끄기와 교체와 연결 닫기를 제한했습니다.',
          'open_job': '진행 작업 보기',
          'allow_tunnel': '닫힌 연결 통로를 여는 행동은 허용합니다.',
          'open_tunnel': '연결 열기 확인하기'},
 'mismatch': {'title': '서버에 다른 AI 모델이 켜져 있습니다.',
              'limit': '회사 서버는 한 번에 모델 하나만 사용합니다.',
              'unload': '기존 모델 끄기 확인하기'},
 'env': {'title': '설정 파일의 {line_no}번째 줄을 읽지 못했습니다.',
         'state': '설정 확인 필요',
         'todo': '할 일: 설정 파일(.env)의 해당 줄을 고친 뒤 설정을 다시 읽으세요.',
         'names': '필요한 설정 이름',
         'company_name': 'RNGD_BASE_URL',
         'company_meaning': ': 회사 모델의 응답 주소.',
         'rented_name': 'RUNPOD_VLLM_API_KEY',
         'rented_meaning': ': 빌린 모델의 접속 키.',
         'hidden_values': '설정 값은 이 화면에 표시하지 않습니다.'},
 'account_failed': {'title': '빌린 서버 목록을 읽지 못했습니다.',
                    'state': '계정 확인 실패',
                    'todo': '할 일: 설정 파일의 관리 키와 계정 권한을 확인하세요.',
                    'cost_unknown': '가동 시간과 비용은 알 수 없습니다.'},
 'create_unknown': {'title': '새 서버 생성 결과를 확인하지 못했습니다.',
                    'state': '생성 여부 확인 필요',
                    'todo': '할 일: 다시 만들기 전에 서버 목록부터 확인하세요.',
                    'reload': '서버 목록 다시 확인하기'},
 'unloaded': {'title': '회사 서버의 {model}를 내렸습니다.',
              'process': '종료한 프로세스 번호: {pid} (예시).',
              'tunnel': '연결 통로는 열려 있습니다.',
              'select_model': '새 모델 고르기'},
 'models': {'title': '모델별 연결 상태',
            'connected': '연결됨',
            'off': '연결 안 됨',
            'unknown': '확인 못 함',
            'empty': '등록된 모델이 없습니다.',
            'tag': '모델 태그',
            'where': '서버 종류',
            'response': '응답 상태',
            'not_configured': '설정 없음',
            'match': '기대한 모델과 일치',
            'no_reply': '응답 없음',
            'state': '연결 상태'},
 'session': {'adopted': '앱을 다시 켠 뒤 기존 서버 {pod_id}을 이어 쓰고 있습니다.',
             'active': '시험과 본 실행은 서버 {pod_id}을 사용합니다.',
             'preparing': '모델 응답을 기다리고 있습니다. 준비 중에도 요금이 나갑니다.',
             'settings': '접속 키는 설정 파일의 RUNPOD_VLLM_API_KEY를 사용합니다.'},
 'time': {'hours_minutes': '{hours}시간 {minutes}분',
          'minutes': '{minutes}분',
          'since': '통로를 연 뒤 {elapsed} 지났습니다.',
          'auto_delete': '자동 삭제까지 {minutes}분',
          'no_schedule': '자동 삭제 예약은 확인하지 못했습니다.'},
 'reload': {'done': '설정을 다시 읽었습니다.', 'names': '채워진 설정 이름', 'changed': '바뀐 설정 이름', 'removed': '지운 설정 이름'},
 'disabled': {'fact': '서버 관리 기능이 꺼져 있습니다.', 'todo': '할 일: 서버 관리 기능을 켠 앱으로 다시 실행하세요. 저장된 결과는 계속 볼 수 있습니다.'},
 'result': {'done': '요청한 서버 변경을 마쳤습니다.',
            'created': '서버 {pod_id}을 만들었습니다. 모델의 응답을 확인한 뒤 시험하세요.',
            'watchdog': '4시간 뒤 자동 삭제 감시를 시작했습니다.',
            'no_watchdog': '자동 삭제 감시를 시작하지 못했습니다. 사용 뒤 직접 삭제하세요.',
            'deleted': '서버 {pod_id}이 목록에서 사라진 것을 확인했습니다. 남은 서버 {count}개.',
            'remaining': '남은 서버 번호: {ids}',
            'deleting': '삭제 요청 뒤에도 서버 {pod_id}이 목록에 남아 있습니다. 잠시 뒤 다시 확인하세요.',
            'started': '모델 프로세스를 시작했습니다. 응답까지 보통 15~25분 걸립니다.',
            'stopped': '멈춘 프로세스: {pids}',
            'process_remaining': '아직 남은 프로세스: {pids}',
            'tunnel_open': '연결 통로를 열었습니다. 모델의 응답을 확인하세요.',
            'tunnel_close': '연결 통로를 닫았습니다.',
            'log': '서버 기록: {line}'},
 'redacted': '[설정 값 숨김]'}
UI_TEXT.setdefault("errors", {})["connection"] = {'ssh_prefix': {'fact': 'RNGD_SSH 설정에 ssh 명령어까지 들어 있습니다.', 'todo': '할 일: 앞의 ssh를 빼고 접속 옵션만 적으세요.'},
 'ssh_missing': {'fact': '회사 서버 접속 설정(RNGD_SSH)이 없습니다.',
                 'todo': '할 일: .env.example의 RNGD_SSH 항목을 설정 파일에 채우세요.'},
 'certificate': {'fact': '빌린 서버 주소의 인증서를 확인하지 못했습니다.',
                 'todo': '할 일: Python 3.11을 쓴다면 인증서 설치 파일을 실행한 뒤 앱을 다시 켜세요.'},
 'model_key': {'fact': '모델 서버가 접속 키를 거절했습니다.', 'todo': '할 일: 설정 파일의 모델 접속 키와 서버를 켤 때 쓴 키를 맞추세요.'},
 'account_key': {'fact': '빌린 서버 관리 키가 거절됐습니다.', 'todo': '할 일: RunPod에서 관리 키를 다시 만든 뒤 설정 파일에 넣으세요.'},
 'no_response': {'fact': '모델 서버가 응답하지 않습니다.', 'todo': '할 일: AI 켜기와 비용에서 연결 통로와 모델 준비 상태를 확인하세요.'},
 'other': {'fact': '서버 상태를 읽지 못했습니다.', 'todo': '할 일: 오류 기록을 열어 설정과 연결 상태를 확인하세요.'},
 'model_key_changed': '서버를 만든 뒤 접속 키를 바꿨다면 서버를 다시 만들어야 합니다. 비용을 확인한 뒤 진행하세요.'}
UI_TEXT.setdefault("errors", {})["env"] = {'line': '설정 파일(.env)의 {line}번째 줄을 읽지 못했습니다.',
 'line_todo': '할 일: 해당 줄의 따옴표와 = 표시를 고친 뒤 설정 다시 읽기를 누르세요.',
 'missing': '설정 파일(.env)에 {variable} 설정이 없습니다.',
 'runpod_url': '할 일: RUNPOD_VLLM_BASE_URL에 빌린 서버의 중계 주소를 넣으세요.',
 'company_url': '할 일: RNGD_BASE_URL에 보안 연결을 거친 내 컴퓨터 쪽 주소를 넣으세요.',
 'unknown_url': '할 일: 모델 설정에서 {variable}에 필요한 주소 형식을 확인하세요.'}
COPY_EXCEPTIONS.update({'servers.models.title': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.models.connected': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.models.off': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.models.unknown': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.models.empty': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.models.tag': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.models.where': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.models.response': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.models.not_configured': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                                  '기록합니다.',
 'servers.models.match': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.models.no_reply': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.models.state': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.session.adopted': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.session.active': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.session.preparing': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.session.settings': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.time.hours_minutes': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                               '기록합니다.',
 'servers.time.minutes': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.time.since': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.time.auto_delete': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.time.no_schedule': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.rented.title_list': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.rented.identity': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.rented.owned': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.rented.state': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.rented.no_delete': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.rented.volume_unknown': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                                  '기록합니다.',
 'servers.rented.hourly': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.connection.tunnel_closed': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                                     '기록합니다.',
 'servers.connection.tunnel_external': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 '
                                       'BUILD에 기록합니다.',
 'servers.connection.tunnel_unknown': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 '
                                      'BUILD에 기록합니다.',
 'servers.connection.tunnel_time_unknown': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 '
                                           'BUILD에 기록합니다.',
 'servers.connection.process': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                               '기록합니다.',
 'servers.connection.processes': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                                 '기록합니다.',
 'servers.connection.choose': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.connection.choice': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.connection.none': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.connection.loading_locked': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 '
                                      'BUILD에 기록합니다.',
 'servers.connection.replace_locked': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 '
                                      'BUILD에 기록합니다.',
 'servers.reload.done': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.reload.names': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.reload.changed': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.reload.removed': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.disabled.fact': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.disabled.todo': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.logs.empty': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.logs.path': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.logs.manual_copy': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.confirm.delete.title': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                                 '기록합니다.',
 'servers.confirm.delete.action': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                                  '기록합니다.',
 'servers.confirm.create.action': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                                  '기록합니다.',
 'servers.confirm.expires': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.confirm.expired.fact': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                                 '기록합니다.',
 'servers.confirm.expired.todo': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                                 '기록합니다.',
 'servers.confirm.warning': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.confirm.no_expiry': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.result.done': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.result.created': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.result.watchdog': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.result.no_watchdog': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                               '기록합니다.',
 'servers.result.deleted': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.result.remaining': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.result.deleting': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.result.started': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.result.stopped': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.result.process_remaining': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                                     '기록합니다.',
 'servers.result.tunnel_open': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                               '기록합니다.',
 'servers.result.tunnel_close': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 '
                                '기록합니다.',
 'servers.result.log': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.',
 'servers.redacted': '동적 서버 상태와 실데이터 단위 또는 확인 절차에 필요한 문구를 보충합니다. 시안의 예시 표시와 실제 계약 차이는 BUILD에 기록합니다.'})

UI_TEXT["jobs"]["try_hint"] = {
    "ready": "응답한 모델이 {count}개 있습니다. 모델을 고른 뒤 실제 시험을 시작하세요.",
    "off": "응답한 모델이 없습니다. AI 없이 보낼 내용만 확인할 수 있습니다. 실제 시험을 하려면 AI 켜기와 비용에서 모델을 준비하세요.",
}

POLISH_TEXT = {**_LEGACY_POLISH_TEXT, **UI_TEXT}


START_TEXT: dict = {
    "intro": [
        "안전보건자료(MSDS)에서 정보를 뽑는 모델의 결과를 점수로 봅니다.",
        "틀린 값을 원문과 맞춰 봅니다.",
        "고칠 항 하나만 다시 시험할 수 있습니다.",
    ],
    "steps": [
        {"no": 1, "title": "점수를 먼저 봅니다.",
         "why": "어느 항목이 깎였는지 알아야 고칠 곳을 정할 수 있어요.",
         "button": "최근 실행 점수 보기", "tab": "score"},
        {"no": 2, "title": "깎인 항목을 고릅니다.",
         "why": "지금 상태 카드에서 ‘원문 대조로 →’를 누르면 그 항목으로 이동해요.",
         "button": "깎인 항목 고르기", "tab": "score"},
        {"no": 3, "title": "틀린 값의 원문을 확인합니다.",
         "why": "오른쪽에서 실버와 다른 값을 누르면 왼쪽 근거 줄이 노랗게 켜져요.",
         "button": "원문에서 값 고르기", "tab": "doc"},
    ],
    "later": [
        {"title": "두 실행 비교", "line": "바꾼 뒤 점수가 나아졌는지 확인합니다.",
         "button": "두 실행 비교하기", "tab": "diff"},
        {"title": "항 하나 시험", "line": "고칠 항 하나만 모델에 다시 보냅니다.",
         "button": "시험 준비하기", "tab": "jobs"},
        {"title": UI_TEXT["nav"]["servers"], "line": "모델을 새로 부를 때 준비합니다.",
         "button": UI_TEXT["context"]["prepare_model"], "tab": "servers"},
    ],
    "empty_runs": "runs/에 실행이 없습니다. 터미널에서 run_sections.py를 돌리거나 ④ 작업 탭을 보세요.",
    "no_drops": "두 목표를 모두 넘었습니다. ② 두 실행 비교에서 이전 실행과 비교해 보세요.",
    "no_line": "이 값은 원문 줄을 못 찾았습니다. 다른 값을 눌러 보세요.",
    "heading": "지금 할 일",
    "later_title": "다음에 할 수 있는 것",
    "offline": "모델 서버 없이 저장된 실제 실행 결과로 시작할 수 있습니다.",
    "loading": "실행 목록을 불러오는 중입니다.",
    "unscored": "아직 점수를 낸 실행이 없습니다. ① 점수판에서 실행 상태를 보세요.",
    "no_candidates": "원문으로 연결할 미달 항목이 없습니다. ① 점수판에서 전체 항목을 보세요.",
    "resume": "지금 상태 카드에서 원문으로 볼 항목을 다시 골라 주세요.",
    "success": "틀린 값의 원문 줄을 확인했습니다. 첫 안내를 마쳤습니다.",
    "done": "✓ 끝남", "current": "현재 단계", "skipped": "건너뜀",
    "dismiss": "이 안내 닫기", "replay": "처음부터 다시 보기",
    "compare_button": "두 실행 비교하기",
}


FIELD_HELP: dict[str, str] = {
    "model": "문서에서 값을 뽑을 모델입니다. 연결된 모델부터 보여 줍니다.",
    "doc": "시험할 개발용 문서입니다. 평가용 문서는 고를 수 없습니다.",
    "pages": "전처리한 쪽 글자가 있는 폴더입니다. 현재 실행 입력은 version9입니다.",
    "scope": "시험할 항을 고릅니다. 문서 전체는 16개 항을 보냅니다.",
    "prompt": "모델에게 줄 지시문입니다. 항을 하나만 고르면 고쳐 쓸 수 있습니다.",
    "base_run": "시험한 항의 답을 끼워 넣을 기준 실행입니다. 자동이면 같은 모델의 가장 최근 개발 10건 실행을 씁니다.",
    "dry_run": "서버를 부르지 않고 입력과 안내문 정보를 확인합니다.",
    "repeat": "같은 조건으로 실행할 횟수입니다. 1~10회로 정합니다.",
    "run_name": "결과를 모아 둘 폴더 이름입니다. 회차마다 _r1, _r2가 붙습니다.",
    "compare_label": "비교표에서 실행을 부를 이름입니다. 비우면 실행 이름을 씁니다.",
}

# 도움말 5장의 여섯 단계와 같은 설명이다.
TRY_STAGE_HELP: dict[str, str] = {
    "① 보낸 입력": "모델에게 준 줄 글자. 줄 번호(p2:L23 모양)가 앞에 붙어 있습니다.",
    "② 안내문": "모델에게 준 지시문. 화면에만 보이고 파일로 저장하지 않습니다.",
    "③ 모델 원문 답": "모델이 쓴 글 그대로입니다.",
    "④ 읽은 결과": "원문 답을 중간 형식으로 바꾼 것. 행 형식에서 버린 줄 수도 나옵니다.",
    "⑤ 펼친 TO21 칸": "중간 형식을 최종 JSON 칸으로 펼친 것입니다.",
    "⑥ 점수 전 → 후": "기준 실행의 해당 항 답을 새 답으로 바꿔 끼워 다시 채점한 점수입니다.",
}

JOB_UI_TEXT = {
    "send": "모델에 보내기",
    "preview": "입력·안내문 보기",
    "run_unavailable": "연결된 모델을 고르면 본 실행을 시작할 수 있습니다.",
    "more_summary": "본 실행과 비교표 만들기는 여기서 펼칩니다.",
}


def order_models(models: list[dict]) -> list[dict]:
    """같은 연결 상태의 순서는 유지하고, 원래 모델 정보에 선택지 글만 더한다."""
    rank = {True: 0, None: 1, False: 2}
    labels = {True: "연결됨", None: "연결 모름", False: "연결 안 됨"}
    return [{**m, "option_label": f"{m['label']} — {labels[m.get('connected')]}"}
            for m in sorted(models, key=lambda m: rank[m.get("connected")])]


def try_hint(models: list[dict], advanced: bool) -> dict:
    """연결을 확인한 모델이 없으면 서버 없는 시험만 안내한다."""
    count = sum(m.get("connected") is True for m in models)
    note = UI_TEXT["jobs"]["try_hint"]["ready" if count else "off"].format(count=count)
    return {"dry_run_forced": not count, "note": note}


# 용어만 맡는다. 채점 항목 23개의 설명은 b_app_runs.ITEM_HELP에 둔다.
# 예의 근거: guide.html 9장, b_app_runs.criteria/limit_kind, models.yaml,
# section_prompts.SECTION_PROMPT_VERSION, try_section의 옵션, app.js의 표시·조작.
# 문서 내용이나 실행 점수는 넣지 않는다.
GLOSSARY: dict[str, dict] = {
    "실버": {
        "short": "Claude가 만든 정답 초안으로, 틀린 곳이 있을 수 있습니다.",
        "example": "비교표는 data/silver/claude의 파일을 정답 자리에 놓습니다.",
        "also": ["정답 초안", "정답 초안(실버)", "silver"],
    },
    "골드": {
        "short": "사람이 내용을 확인한 정답입니다.",
        "example": "도움말의 ‘정답(골드)’는 Claude가 만든 초안과 구분됩니다.",
        "also": ["정답(골드)", "gold"],
    },
    "가중 종합": {
        "short": "각 항목 점수에 중요도별 무게를 곱해 평균 낸 점수입니다.",
        "example": "무게는 필수 3, 중요 2, 일반 1입니다.",
        "also": ["가중 종합 점수", "weighted"],
    },
    "필수 통과": {
        "short": "필수 항목 중 각자의 목표 점수 이상인 항목 수입니다.",
        "example": "17/17은 필수 17개가 모두 목표 이상이라는 표시입니다.",
        "also": ["must_passed"],
    },
    "필수": {
        "short": "가중 종합과 별개로 빠짐없이 목표를 넘어야 하는 등급입니다.",
        "example": "신호어는 필수 등급이며 점수 무게는 3입니다.",
        "also": ["필수 등급"],
    },
    "중요": {
        "short": "가중 종합에서 일반 항목보다 무게가 큰 등급입니다.",
        "example": "중요 등급의 점수 무게는 2입니다.",
        "also": ["중요 등급"],
    },
    "일반": {
        "short": "가중 종합에서 점수 무게가 가장 작은 등급입니다.",
        "example": "일반 등급의 점수 무게는 1입니다.",
        "also": ["일반 등급"],
    },
    "항": {
        "short": "안전보건자료를 나눈 법정 16개 구역 중 하나입니다.",
        "example": "3항은 구성성분, 14항은 운송에 관한 구역입니다.",
        "also": ["법정 항"],
    },
    "항목": {
        "short": "점수판에서 각각 점수를 매기는 검사 단위입니다.",
        "example": "점수판은 그림문자와 H 코드 등을 23개 항목으로 채점합니다.",
        "also": ["채점 항목"],
    },
    "안내문": {
        "short": "어떤 값을 어떻게 뽑을지 모델에게 알려 주는 지시문입니다.",
        "example": "작업 탭의 ‘고쳐 쓰기’는 항 하나의 안내문을 바꿔 시험합니다.",
        "also": ["프롬프트", "prompt"],
    },
    "안내문 버전": {
        "short": "안내문 내용이 바뀐 판을 구분하는 번호입니다.",
        "example": "s7은 16항 관리정보와 결과 칸의 대응을 더한 판입니다.",
        "also": ["prompt_version"],
    },
    "입력 판": {
        "short": "모델에게 보낼 쪽 글자 묶음을 구분하는 판입니다.",
        "example": "version9는 줄 앞에 L001처럼 번호를 붙이고 표 칸을 |로 나눕니다.",
        "also": ["입력판", "쪽 폴더", "쪽 글자 폴더"],
    },
    "쪽 글자": {
        "short": "PDF의 각 쪽에서 읽어 모델 입력으로 쓰는 글입니다.",
        "example": "원문 대조의 왼쪽에서 쪽 그림과 쪽 글자를 함께 봅니다.",
        "also": ["쪽 텍스트"],
    },
    "줄 번호": {
        "short": "결과 값의 근거가 원문 몇 쪽의 어느 줄인지 가리키는 표시입니다.",
        "example": "p2:L23은 2쪽의 23번 줄을 가리킵니다.",
        "also": ["근거 줄 번호"],
    },
    "기준 실행": {
        "short": "새로 뽑은 항의 답을 끼워 넣어 점수 변화를 볼 기존 실행입니다.",
        "example": "시험 결과의 ‘전’은 기준 실행, ‘후’는 새 답을 끼운 점수입니다.",
        "also": ["base_run"],
    },
    "dry-run": {
        "short": "모델 서버를 부르지 않고 입력과 안내문만 확인하는 방식입니다.",
        "example": "--dry-run은 ‘① 보낸 입력’과 ‘② 안내문’까지만 보여 줍니다.",
        "also": ["서버 없이 확인"],
    },
    "시험": {
        "short": "항 하나나 문서 하나를 다시 뽑아 변경 효과를 확인하는 작업입니다.",
        "example": "작업 탭의 ‘시험하기’는 처음에 11항이 선택되어 있습니다.",
        "also": ["수동 시험"],
    },
    "본 실행": {
        "short": "고른 개발용 문서들을 정한 횟수만큼 모두 추출하는 작업입니다.",
        "example": "작업 탭의 본 실행은 기본 반복 횟수가 2회입니다.",
        "also": ["전체 실행"],
    },
    "비교표": {
        "short": "여러 실행의 점수와 시간을 같은 기준으로 모은 표입니다.",
        "example": "작업 탭에서 만든 비교표의 파일 이름은 compare.md입니다.",
        "also": ["compare.md"],
    },
    "빠뜨림": {
        "short": "정답에는 있지만 추출 결과에는 없는 값입니다.",
        "example": "항목 신호등의 ‘빠뜨림’ 수를 보고 줄을 누르면 해당 값 목록이 열립니다.",
        "also": ["누락"],
    },
    "지어냄": {
        "short": "추출 결과에는 있지만 비교 기준인 정답에는 없는 값입니다.",
        "example": "항목 신호등의 ‘지어냄’은 ‘결과에는 있는데 정답에 없음’으로 표시합니다.",
        "also": ["과추출"],
    },
    "틀림": {
        "short": "정답과 추출 결과 양쪽에 있으나 내용이 다른 값입니다.",
        "example": "항목 신호등의 ‘틀림’은 ‘둘 다 있지만 값이 다름’으로 표시합니다.",
        "also": ["값 불일치"],
    },
    "값 없는 행": {
        "short": "자료없음이나 해당없음처럼 실제 값 대신 상태만 적힌 행입니다.",
        "example": "‘값 없는 행을 뺀 점수’는 자료없음·해당없음·비해당·미기재 행을 양쪽에서 뺍니다.",
        "also": ["무값 행"],
    },
    "호출 격자": {
        "short": "문서와 항별로 모델 요청의 상태를 보여 주는 표입니다.",
        "example": "호출 격자의 열은 1항부터 16항까지입니다.",
        "also": [],
    },
    "재추출": {
        "short": "검사에 걸린 항에 문제 설명을 붙여 한 번 더 뽑는 작업입니다.",
        "example": "둘째 답이 첫째 답보다 나을 때만 둘째 답을 채택합니다.",
        "also": ["다시 추출"],
    },
    "출력 한도": {
        "short": "모델이 한 번의 요청에서 답할 수 있는 최대 길이입니다.",
        "example": "Qwen3.6 설정은 일반 답 8,192토큰, 행 형식 답 16,384토큰까지 받습니다.",
        "also": ["한도 걸림", "출력 길이 한도"],
    },
    "공백폭주": {
        "short": "답 대신 공백이 길게 이어져 출력 한도를 소모한 상태입니다.",
        "example": "한도에 걸린 답의 공백 비율이 50%를 넘으면 공백폭주로 분류합니다.",
        "also": ["공백 폭주"],
    },
    "반복": {
        "short": "모델이 같은 글을 계속 되풀이하다 출력 한도에 걸린 상태입니다.",
        "example": "답 끝에서 20자 이상인 같은 글이 4번 이상 이어지면 반복으로 분류합니다.",
        "also": ["반복 출력"],
    },
    "모델 태그": {
        "short": "모델과 호출 설정을 고르는 짧은 식별 이름입니다.",
        "example": "qwen36_35b_runpod는 Qwen3.6의 RunPod 설정을 고르는 태그입니다.",
        "also": ["model_tag"],
    },
    "RunPod": {
        "short": "모델을 띄울 장비를 시간당 요금을 내고 빌리는 서비스입니다.",
        "example": "서버 탭의 RunPod 카드에서 ‘Pod 만들기(Qwen3.6)’를 고릅니다.",
        "also": [],
    },
    "RNGD": {
        "short": "이 프로젝트에서 모델을 띄우는 사내 연산 장비입니다.",
        "example": "서버 탭의 RNGD 카드는 장비 카드 4장을 안내합니다.",
        "also": ["사내 장비"],
    },
    "Pod": {
        "short": "RunPod에서 만들어 모델을 실행하는 서버 한 대입니다.",
        "example": "이 도구가 만든 Pod의 이름은 to21-b-로 시작합니다.",
        "also": ["팟"],
    },
    "회차": {
        "short": "같은 조건의 실행을 몇 번째로 돌렸는지 나타내는 번호입니다.",
        "example": "실행 이름 끝의 r2는 2회차를 뜻합니다.",
        "also": [],
    },
    "extras": {
        "short": "정해진 결과 칸에 들어가지 않아 따로 모은 남는 값입니다.",
        "example": "점수판의 ‘표 행 수’는 남는 값 extras의 행 수도 셉니다.",
        "also": ["남는 값", "extras(남는 값)"],
    },
    "실버 빈 곳": {
        "short": "정답 초안 자체에 빠졌거나 확인이 필요한 부분을 적어 둔 메모입니다.",
        "example": "항목 신호등의 노란 점에 실버 빈 곳의 메모와 출처가 나옵니다.",
        "also": [],
    },
    "동시 호출": {
        "short": "여러 항의 모델 요청을 한꺼번에 보내는 방식입니다.",
        "example": "Qwen3.6 설정의 concurrency: 16은 최대 16개 요청을 함께 보냅니다.",
        "also": ["동시 요청", "동시 수", "concurrency"],
    },
    "행 형식": {
        "short": "모델이 표의 값들을 정해진 열 순서로 한 줄에 한 행씩 쓰는 방식입니다.",
        "example": "3·8·9·11·12·14·15항은 행 형식으로 받는 표 항목입니다.",
        "also": [],
    },
    "흔들림": {
        "short": "같은 조건으로 여러 번 실행했을 때 결과 점수가 달라지는 현상입니다.",
        "example": "본 실행의 r1과 r2는 같은 조건의 회차별 결과를 비교하는 데 씁니다.",
        "also": [],
    },
}


def glossary_entries() -> list[dict]:
    """가나다 순의 사전 사본. 화면과 도움말이 같은 API를 쓴다."""
    return [{"term": term, **entry, "also": list(entry["also"])}
            for term, entry in sorted(GLOSSARY.items())]


def explain(term: str) -> str | None:
    """용어 또는 같은 뜻의 표기에 해당하는 쉬운 설명을 돌려준다."""
    for name, entry in GLOSSARY.items():
        if term == name or term in entry["also"]:
            return entry["short"]
    return None


_ROW_LABELS = {
    "components": "성분 (3항)", "exposure_limits": "노출기준 (8항)", "physchem": "물리·화학 성질 (9항)",
    "toxicity": "독성 (11항)", "cmr": "발암성 등 CMR (11항)", "ecotox": "생태 독성 (12항)",
    "regulations": "규제 (15항)", "intl_class": "국제 분류 (15항)", "extras": "남는 값 extras (자리가 없는 값)",
}


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def diff_headline(diff: dict, label_a: str, label_b: str) -> dict:
    """B − A의 서버 계산값을 승인 문구로 요약한다. API의 조건·문서 일치 판정을 따른다."""
    words = UI_TEXT["compare"]
    changed = [c["what"] for c in diff.get("conditions", []) if c.get("changed")]
    if diff.get("prompt_changed_sections"):
        changed.append(words["conditions"]["prompt_text"])
    same = not changed and diff.get("same_conditions", True) is True
    items = [i for i in diff.get("items", []) if _number(i.get("delta"))]
    if not items:
        return {"headline": words["headline"]["none"], "biggest": None, "same_conditions": same}
    item = max(items, key=lambda i: (abs(i["delta"]), i["delta"] < 0))
    biggest = {"name": item["name"], "delta": item["delta"]}
    delta = (diff.get("weighted") or {}).get("delta")
    direction = "unscored" if not _number(delta) else "equal" if delta == 0 else "lower" if delta < 0 else "higher"
    headline = words["headline"][direction].format(a=label_a, b=label_b, gap=f"{abs(delta):.1f}" if _number(delta) else "—")
    if item["delta"]:
        sign = "−" if item["delta"] < 0 else "+"
        headline += " " + words["headline"]["biggest"].format(item=item["name"], delta=f"{sign}{abs(item['delta']):.1f}")
    if same:
        headline += " " + words["conditions"]["same"] + " " + words["conditions"]["variation"]
    elif changed:
        headline += " " + ". ".join(words["conditions"]["changed"].format(condition=c) for c in changed) + "."
    else:
        headline += " " + words["different"]["title"]
    return {"headline": headline, "biggest": biggest, "same_conditions": same}


def diff_ui_text(diff: dict) -> dict:
    """표시 범위와 원인 후보의 안내. 원인 판정은 b_app_diff에 그대로 둔다."""
    hidden = sum(not _number(i.get("delta")) or i["delta"] >= 0 for i in diff.get("items", []))
    words = UI_TEXT["compare"]["items"]
    return {"hidden": words["hidden"].format(count=hidden), "empty": words["empty"], "candidate": words["candidate"]}


def connection_note(run_model: str | None, connected: list[str] | None, advanced_hint: str,
                    *, checked: bool = True) -> dict:
    """점수 조회와 재시험의 연결 요구를 구분한다. None은 조회 실패다."""
    words = UI_TEXT["context"]["model"]
    model = run_model or words["default_name"]
    state, level = ("checking", "hint") if not checked else ("failed", "error") if connected is None else (
        ("ready", "ok") if (run_model in connected if run_model else bool(connected)) else ("off", "hint"))
    return {"text": " ".join([words[state].format(model=model), words["reading"], words["action"]]), "level": level}


def connection_notes(run_model: str | None) -> dict:
    """옛 응답 키는 유지하지만 두 상태 모두 바로 보이는 모델 관리로 안내한다."""
    return {state: {mode: connection_note(run_model, connected, "", checked=state != "loading")
                    for mode in ("advanced_on", "advanced_off")}
            for state, connected in (("ok", [run_model] if run_model else ["모델"]),
                                     ("hint", []), ("error", None), ("loading", []))}


VALUE_FIELD_LABELS = {
    "value": "값", "text": "원문 글", "refs": "근거 줄", "cond": "조건",
    "std_code": "표준 코드", "match_score": "맞춤 점수", "seq": "순서", "key": "이름",
    "raw": "원래 표기", "unit": "단위", "status": "상태", "name": "이름",
    "code": "코드", "source_text": "근거 원문", "page": "쪽", "line": "근거 줄",
    "lines": "근거 줄", "source": "출처", "note": "비고", "type": "종류",
    "lower": "최솟값", "upper": "최댓값", "lower_op": "최솟값 비교 기호",
    "upper_op": "최댓값 비교 기호", "approx": "근삿값 여부", "dp": "소수 자릿수",
    "cas_no": "물질 식별 번호(CAS)", "ke_no": "국내 물질 번호(KE)", "comp_ref": "성분 참조",
}


def value_tip_lines(value, labels: dict) -> list[str]:
    """빈 칸을 뺀 한 줄씩의 설명. 모르는 키와 0·false는 보존한다."""
    def compact(item):
        if item is None:
            return ""
        if isinstance(item, dict):
            return ", ".join(f"{labels.get(k, k)}: {shown}" for k, v in item.items()
                             if (shown := compact(v)))
        if isinstance(item, list):
            return ", ".join(shown for v in item if (shown := compact(v)))
        if isinstance(item, bool):
            return UI_TEXT["source"]["value"]["true" if item else "false"]
        return " ".join(str(item).split())

    if isinstance(value, dict):
        return [f"{labels.get(k, k)}: {shown}" for k, v in value.items() if (shown := compact(v))]
    if isinstance(value, list):
        shown = compact(value)
        return [shown] if shown else []
    return []


def doc_legend() -> list[dict]:
    """승인 토큰과 UI_GUIDE의 주황 의미를 원문 범례에 쓴다."""
    return [{"key": key, "label": label, "color": color} for key, label, color in [
        ("same", UI_TEXT["source"]["legend"]["same"], "#53645e"),
        ("diff", UI_TEXT["source"]["legend"]["different"], "#bc4c00"),
        ("silver_only", UI_TEXT["source"]["legend"]["missing"], "#a52f35"),
        ("picked", UI_TEXT["source"]["legend"]["selected"], "#fff3c6"),
    ]]


def doc_ui_text(view: dict) -> dict:
    """원문 대조 사용법과 항별 값 수를 설명한다. 빠뜨린 칸은 결과 수와 따로 센다."""
    counts = {}
    for only, values in [(False, view.get("values", [])), (True, view.get("silver_only", []))]:
        for value in values:
            key = str(value["section"]) if value.get("section") is not None else "?"
            count = counts.setdefault(key, [0, 0, 0])
            if only:
                count[2] += 1
            else:
                count[0] += 1
                count[1] += not value.get("silver", {}).get("same", False)
    tips = {
        "result": {v["path"]: value_tip_lines(v.get("value"), VALUE_FIELD_LABELS)
                   for v in view.get("values", []) if "path" in v},
        "silver": {v["path"]: value_tip_lines(v.get("silver", {}).get("value"), VALUE_FIELD_LABELS)
                   for v in view.get("values", []) if "path" in v},
        "silver_only": {v["path"]: value_tip_lines(v.get("value"), VALUE_FIELD_LABELS)
                        for v in view.get("silver_only", []) if "path" in v},
    }
    return {"value_field_labels": VALUE_FIELD_LABELS, "value_tips": tips,
            "howto": UI_TEXT["source"]["doc"]["howto"],
            "silver_line_guess": UI_TEXT["source"]["doc"]["guess"],
            "silver_line_missing": UI_TEXT["source"]["doc"]["no_guess"],
            "sections": {key: UI_TEXT["source"]["doc"]["counts"].format(
                total=total, different=different, missing=missing)
                         for key, (total, different, missing) in counts.items()}}


# 이름에 "N항"이 없는 채점 항목(이름 앞부분) → 그 값을 만드는 항. b_app_doc.SECTION_OF와 같은 규칙이다.
# 관리정보는 개정 정보가 16항 값을 우선하므로 16항이다 (ADR-020). None은 한 항으로 갈 수 없는 항목이다.
ITEM_SECTION: dict[str, int | None] = {
    "MSDS 건수": None, "관리정보": 16, "제품명": 1,
    "신호어": 2, "그림문자": 2, "H 코드": 2, "P 코드": 2, "유해성 분류": 2,
    "구성성분": 3, "함유량": 3, "서술형": None,
}


def item_section(item: dict, criteria: dict) -> int | None:
    """이름의 "N항", ITEM_SECTION, ITEM_HELP에서 온 설명에 적힌 항 순서로 찾는다. 추측하지 않는다."""
    match = re.match(r"^(1[0-6]|[1-9])항", item["name"])
    if match:
        return int(match[1])
    prefix = max((k for k in ITEM_SECTION if item["name"].startswith(k)), key=len, default=None)
    if prefix is not None:
        return ITEM_SECTION[prefix]
    help_text = next((i.get("help", "") for i in criteria.get("items", []) if i.get("name") == item["name"]), "")
    match = re.search(r"(?<!\d)(1[0-6]|[1-9])항", help_text)
    return int(match[1]) if match else None


def _doc_losses(row: dict, per_doc: dict | None, weight_total: float) -> list[dict]:
    """항목 손실을 문서별로 나눈다. 항목 점수가 문서 평균이라 문서 손실의 합이 항목 손실과 같다."""
    scores = [(d, p["items"][row["name"]]) for d, p in (per_doc or {}).items()
              if _number((p.get("items") or {}).get(row["name"]))]
    docs = [{"doc_id": d, "score": s * 100, "loss": row["weight"] * (1 - s) / (len(scores) * weight_total) * 100}
            for d, s in scores]
    return sorted(docs, key=lambda d: -round(d["loss"], 9))


def score_losses(info: dict, criteria: dict, per_doc: dict | None = None) -> dict:
    """항목마다 가중 종합을 깎은 점수. 손실 = 무게×(1−점수)/무게 합×100이고 목표를 넘은 항목도 센다.
    모든 손실의 합은 100 − 가중 종합이다 (사용자 결정 10/31). 점수 없는 항목은 가중 종합에도 없으므로 뺀다."""
    weighted = info.get("weighted")
    if not _number(weighted):
        return {"losses": [], "top_problem": None, "loss_basis": None}
    items = [i for i in info.get("items", []) if _number(i.get("score"))]
    total = sum(WEIGHTS[i["level"]] for i in items)
    losses = [{"name": i["name"], "level": i["level"], "weight": WEIGHTS[i["level"]],
               "score": i["score"] * 100, "target": i["target"] * 100,
               "loss": WEIGHTS[i["level"]] * (1 - i["score"]) / total * 100,
               "below_target": i["score"] < i["target"], "section": item_section(i, criteria)}
              for i in items]
    for row, item in zip(losses, items):
        kinds = ("빠뜨림", "틀림", "지어냄")
        counts = {kind: item.get(kind, 0) for kind in kinds} if any(kind in item for kind in kinds) else None
        row["counts"] = counts
        row["cause"] = (max(kinds, key=lambda kind: counts[kind] or 0)
                        if counts and any(counts.values()) else None)
    # 같은 손실도 소수 끝자리가 다를 수 있어(3×0.1과 1×0.3) 줄 세울 때만 반올림한다. 같으면 기준 항목 순서다
    order = {c.get("name"): k for k, c in enumerate(criteria.get("items", []))}
    losses.sort(key=lambda r: (-round(r["loss"], 9), order.get(r["name"], len(order))))
    for rank, row in enumerate(losses, 1):
        row["rank"] = rank
    top = None
    if losses and round(losses[0]["loss"], 9) > 0:
        top = {**losses[0], "docs": _doc_losses(losses[0], per_doc, total)}
    return {"losses": losses, "top_problem": top, "loss_basis": {"weight_total": total, "loss_total": 100 - weighted}}


def score_targets(info: dict, criteria: dict) -> dict | None:
    """두 목표: 가중 종합 목표선(criteria의 pass_score)과 필수 항목 중 목표 달성 수. 점수 없는 실행은 None.
    필수 수는 실행의 must_total, 없으면 criteria의 필수 항목 수다. 채점 값은 바꾸지 않는다."""
    weighted = info.get("weighted")
    if not _number(weighted):
        return None
    line = criteria["pass_score"]
    total = info.get("must_total")
    if total is None:
        total = sum(i.get("level") == "필수" for i in criteria.get("items", []))
    met_count = info.get("must_passed") or 0
    return {"weighted": {"line": line, "value": weighted, "met": weighted >= line},
            "must": {"total": total, "met_count": met_count, "met": met_count >= total}}


def score_status(info: dict, criteria: dict, *, connected: bool | None = None,
                 per_doc: dict | None = None) -> dict:
    """채점 값은 그대로 두고 100점 단위의 요약과 확인 순서를 만든다. 목표는 두 개(score_targets)로 보인다.
    top_drops는 목표 아래 항목의 목표 차 순서이고, 총점 손실 순서는 score_losses의 세 키다."""
    targets = score_targets(info, criteria)
    losses = score_losses(info, criteria, per_doc)
    if targets is None:
        return {"headline": UI_TEXT["score"]["summary"]["unscored"], "verdict": "none", "top_drops": [],
                "next_action": UI_TEXT["score"]["summary"]["unscored_todo"], "targets": None, **losses}
    weighted, line = targets["weighted"]["value"], targets["weighted"]["line"]
    must = targets["must"]
    passed = targets["weighted"]["met"] and must["met"]
    copy = UI_TEXT["score"]["summary"]
    headline = copy["value"].format(score=f"{weighted:.1f}") + " "
    headline += copy["headline_met" if targets["weighted"]["met"] else "headline_below"].format(
        line=f"{line:g}", gap=f"{line - weighted:.1f}") + " "
    headline += copy["must_all" if must["met"] else "must_some"].format(
        total=must["total"], met=must["met_count"])

    drops = []
    for item in info.get("items", []):
        if item.get("pass") is not False or not all(_number(item.get(k)) for k in ("score", "target")):
            continue
        # max는 같은 수일 때 앞의 값을 택한다: 빠뜨림 > 틀림 > 지어냄.
        cause = max(("빠뜨림", "틀림", "지어냄"), key=lambda k: item.get(k) or 0)
        score, goal = item["score"] * 100, item["target"] * 100
        drops.append({"name": item["name"], "score": score, "target": goal,
                      "gap": round(goal - score, 10), "weight": WEIGHTS[item["level"]], "cause": cause,
                      "section": item_section(item, criteria),
                      "sentence": f"{item['name']} {score:.1f}점(목표 {goal:g}). 주원인은 {cause} {item.get(cause) or 0}개입니다."})
    drops.sort(key=lambda d: d["gap"] * d["weight"], reverse=True)
    drops = drops[:3]
    if losses["top_problem"]:
        top = losses["top_problem"]
        next_action = (copy["next_trial"].format(section=top["section"])
                       if connected is True and top["section"] is not None else
                       copy["next_source"].format(item=top["name"]))
    elif passed:
        next_action = copy["next_compare"]
    else:
        next_action = copy["next_items"]
    return {"headline": headline, "verdict": "pass" if passed else "fail", "top_drops": drops,
            "next_action": next_action, "targets": targets, **losses}


def card_summary(kind: str, info: dict) -> str:
    """접힌 카드의 요약. 격자는 화면과 같이 실패 > 한도 > 재추출 > 성공으로 한 번씩 센다."""
    if kind == "history":
        # 실버를 만든 실행은 그 실버로 채점하면 점수가 부풀므로 뺀다. 최고 점수는 비교 가능한 실행이 있으면 그중에서 고른다
        runs = [r for r in info.get("runs", [])
                if r.get("kind", "run") == "run" and r.get("run_kind") != "silver" and not r.get("error")
                and _number(r.get("weighted"))]
        if runs:
            best = max([r for r in runs if r.get("comparable")] or runs, key=lambda r: r["weighted"])
            title = (best.get("label") or {}).get("title") or best.get("name", "")
            return UI_TEXT["score"]["summary"]["history"].format(count=len(runs), score=f"{best['weighted']:.1f}", run=title)
    elif kind == "docs":
        docs = info.get("per_doc") or {}
        scored = [(d, p["weighted"]) for d, p in docs.items() if _number(p.get("weighted"))]
        timed = [(d, p["seconds"]) for d, p in docs.items() if _number(p.get("seconds"))]
        if docs and (scored or timed):
            low = min(scored, key=lambda x: x[1]) if scored else None
            slow = max(timed, key=lambda x: x[1]) if timed else None
            copy = UI_TEXT["score"]["summary"]
            score_text = copy["lowest"].format(doc=low[0], score=f"{low[1]:.1f}") if low else copy["no_scores"]
            time_text = copy["slowest"].format(doc=slow[0], seconds=f"{slow[1]:.0f}") if slow else copy["no_times"]
            return copy["docs"].format(count=len(docs), score_detail=score_text, time_detail=time_text)
    elif kind == "grid":
        cells = [c for cells in (info.get("grid") or {}).values() for c in cells.values() if c]
        if cells:
            counts = {k: 0 for k in ("성공", "재추출", "한도 걸림", "실패")}
            for c in cells:
                key = "실패" if not c.get("ok") else "한도 걸림" if c.get("limit_kind") else "재추출" if c.get("reextracted") else "성공"
                counts[key] += 1
            copy = UI_TEXT["score"]["summary"]
            return copy["grid"].format(count=len(cells)) + " " + ", ".join(
                copy["grid_count"].format(state=k, count=v) for k, v in counts.items())
    elif kind == "rows":
        rows = {k: v for k, v in (info.get("rows") or {}).items()
                if k in _ROW_LABELS and all(_number(v.get(f)) for f in ("pred", "gold"))}
        if rows and (info.get("docs") or any(v["pred"] or v["gold"] for v in rows.values())):
            short = [(k, v) for k, v in rows.items() if v["pred"] < v["gold"]]
            copy = UI_TEXT["score"]["summary"]
            result = copy["rows"].format(count=len(rows), short=len(short))
            if short:
                key, row = max(short, key=lambda kv: kv[1]["gold"] - kv[1]["pred"])
                result += " " + copy["rows_shortest"].format(table=UI_TEXT["score"]["tables"][key], pred=row["pred"], answer=row["gold"])
            return result
    return "자료 없음"


MODEL_LABELS: dict[str, str] = {
    "qwen36_35b_runpod": "Qwen3.6 35B (RunPod)",
    "qwen3_30b_a3b_rngd": "Qwen3 30B (RNGD)",
    "gpt_oss_20b_rngd": "gpt-oss 20B (RNGD)",
    "nuextract2_8b_runpod": "NuExtract 2.0 8B (RunPod)",
    "qwen3vl4b_rngd": "Qwen3-VL 4B (RNGD)",
    "qwen38": "Qwen3.8 27B (vLLM)",
    "claude": "Claude (실버 초안)",
    "gpt": "GPT",
}
_CONDITIONS = {
    "dev10": "개발 10건", "dev": "개발 10건", "eval": "평가 10건",
    "probe": "탐색", "cls": "분류 검사", "optonly": "선택 항목만",
    "wsonly": "공백 줄임만", "diag": "진단", "none": "안내문 없음",
    "ex": "예시 포함", "w1": "동시 1개", "p3": "안내문 p3",
}


RUN_KIND_LABELS: dict[str, str] = {
    "dev10": "개발 10건 본 실행", "single": "한 문서 시험", "probe": "일부 문서 탐색", "silver": "실버 만들기",
    "eval": "평가 실행(점수 없음)", "outside": "신규 문서 실행(점수 없음)", "models": "비교표",
}


def run_kind_label(kind: str | None) -> str:
    """b_app_runs.run_kind 값의 사람 말. 모르는 값은 그대로, 없으면 빈 글."""
    return RUN_KIND_LABELS.get(kind, kind or "")


def model_label(tag: str | None) -> str:
    """알려진 모델은 표시 이름으로, 모르는 모델은 태그 그대로 돌려준다."""
    return MODEL_LABELS.get(tag, tag or "")


# manifest 밖 문서를 지금 실행기로 돌릴 수 없다는 사실과 할 일. SET_TEXT["outside_wait"]와 작업 실패 글(job_error)이 같이 쓴다
_OUTSIDE_FACT = "문서 목록(manifest) 밖 문서라 지금 실행기로는 돌릴 수 없습니다."
_OUTSIDE_FIX = "실행기 고침(phase format40)이 합쳐지면, 즉 format40 이후 돌릴 수 있습니다."

# 문서 묶음(b_app_sets)에서 문서나 묶음을 고를 수 없는 이유. 키는 b_app_sets가 쓴다.
SET_TEXT: dict[str, str] = {
    "eval_locked": "평가용 문서라 열지 않습니다 (D-43).",
    "unknown_doc": "문서 목록(manifest)과 meta.json 어디에도 없어 용도를 알 수 없습니다.",
    "empty": "문서 폴더가 없는 빈 폴더입니다.",
    "eval_only": "평가용 문서만 있어 고를 수 없습니다 (D-43).",
    "no_line_numbers": "줄 번호(L001)가 없는 판이라 새 실행 입력으로 고를 수 없습니다. 지난 실행을 볼 때만 씁니다.",
    "nothing_open": "열 수 있는 문서가 없습니다.",
    # 원문 대조가 실행이 쓴 입력 폴더를 따라갈 때의 안내 (format으로 채운다)
    "run_moved": "이 실행은 {recorded}로 돌았고 그 폴더가 prev/로 옮겨져 {id}를 읽습니다.",
    "run_missing": "이 실행이 쓴 입력 폴더({recorded})를 찾지 못해 {name}을 보여 줍니다. 줄 번호가 다를 수 있습니다.",
    # 작업(시험·본 실행)에 넣을 수 없는 문서의 이유 (b_app_sets.job_check)
    "no_line_numbers_doc": "이 문서의 쪽 글자에 줄 번호(L001)가 없어 작업에 넣을 수 없습니다. 줄 번호가 있는 묶음을 고르세요.",
    "outside_try": "문서 목록(manifest) 밖 문서라 항목 시험을 할 수 없습니다. 항목 시험(try_section)은 아직 manifest 문서만 받습니다.",
    "outside_wait": f"{_OUTSIDE_FACT} {_OUTSIDE_FIX}",
    "dev_only": "개발용 문서만 넣을 수 있습니다",
}


def set_label(set_id: str) -> str:
    """묶음 id의 표시 이름. data/pages 바로 아래만 따로 부른다."""
    return "data/pages 바로 아래 (신규 문서)" if set_id == "." else set_id


# 정답지(b_app_sets.list_keys)를 고를 수 없는 이유와 정답지를 고를 때의 오류. 키는 b_app_sets와 b_app이 쓴다.
KEY_TEXT: dict[str, str] = {
    "key_empty": "파일이 없는 빈 폴더입니다.",
    "key_no_doc_files": "문서별 정답 파일(<문서 번호>.json, 예 T21-S003.json)이 없습니다.",
    "key_not_to21": "TO21 답 모양(msds 목록이 든 JSON)의 정답 파일이 없습니다.",
    "key_eval_only": "평가용 문서의 정답만 있어 고를 수 없습니다 (D-43).",
    # format으로 채운다
    "unknown_key": "없는 정답지입니다: {id}. 정답지 목록에서 고르세요.",
    "unusable_key": "고를 수 없는 정답지입니다: {reason}",
}


def key_label(key_id: str) -> str:
    """정답지 id의 표시 이름. 예: gold/a3 → "A 정답(골드) a3". 모르는 모양은 id 그대로."""
    if key_id == "silver/claude":
        return "Claude 정답 초안(실버)"
    kind, _, name = key_id.partition("/")
    if name and "/" not in name:
        if kind == "silver":
            return f"정답 초안(실버) {name}"
        if kind == "gold":
            return f"A 정답(골드) {name}"
    return key_id


def friendly_error(where: str, raw: str, env_names: dict[str, str] | None = None) -> dict:
    """오류를 안내로 바꾼다. 원문은 호출자가 비밀값을 가린 뒤 넘긴다."""
    words = UI_TEXT["errors"]["connection"]
    if "Could not resolve hostname ssh" in raw or "RNGD_SSH starts with ssh" in raw:
        kind = "ssh_prefix"
    elif raw == "RNGD_SSH 없음":
        kind = "ssh_missing"
    elif "SSLCertVerificationError" in raw or "CERTIFICATE_VERIFY_FAILED" in raw:
        kind = "certificate"
    elif where == "model" and "401" in raw:
        kind = "model_key"
    elif "401" in raw or "Unauthorized" in raw:
        kind = "account_key"
    elif where == "env" and env_names:
        variable = env_names.get("base_url") or next(iter(env_names.values()))
        env = UI_TEXT["errors"]["env"]
        fix_key = {"RNGD_BASE_URL": "company_url", "RUNPOD_VLLM_BASE_URL": "runpod_url"}.get(variable, "unknown_url")
        return {"message": env["missing"].format(variable=variable),
                "fix": env[fix_key].format(variable=variable), "raw": raw}
    elif any(token in raw for token in ("timed out", "Connection refused", "TimeoutError",
                                        "ConnectionRefusedError", "TimeoutExpired")):
        kind = "no_response"
    else:
        kind = "other"
    fix = words[kind]["todo"]
    if kind == "model_key":
        fix += " " + words["model_key_changed"]
    return {"message": words[kind]["fact"], "fix": fix, "raw": raw}


def env_problem(line: int) -> dict:
    """오류 줄 번호만 알린다. 설정 값이나 원문 줄은 담지 않는다."""
    words = UI_TEXT["errors"]["env"]
    return {"line": line, "message": words["line"].format(line=line), "fix": words["line_todo"]}


# 작업(시험·본 실행·비교표)이 실패했을 때의 글. job_error가 로그의 마지막 예외 줄로 고른다
JOB_ERROR_TEXT: dict[str, dict[str, str]] = {
    "pages": {"message": "쪽 글자 폴더나 파일이 없습니다.",
              "fix": "작업의 문서 묶음을 다시 고르세요. 기본 묶음은 prev/version9입니다."},
    "outside": {"message": _OUTSIDE_FACT, "fix": _OUTSIDE_FIX},
    "connect": {"message": "모델 서버에 연결하지 못했습니다.", "fix": "서버 상태의 진단(터널·Pod 준비)을 보세요."},
    "key": {"message": "모델 서버가 키를 거절했습니다.",
            "fix": "`.env`의 RUNPOD_VLLM_API_KEY(또는 RNGD_API_KEY)가 서버를 띄울 때 값과 같은지 보세요."},
    "eval": {"message": "평가용 문서는 작업에 넣을 수 없습니다 (D-43).", "fix": "개발용 문서를 고르세요."},
    "other": {"message": "작업이 오류로 끝났습니다.", "fix": "아래 마지막 오류 줄을 보세요."},
    "no_line": {"message": "작업이 오류로 끝났습니다.", "fix": "작업 로그를 열어 마지막 줄을 보세요."},
}
JOB_LOG_LINES = 200                                  # 예외 줄을 찾는 로그 끝 줄 수 (작업 로그 보기의 기본과 같다)
# 파이썬 예외 줄: 줄 맨 앞의 (모듈.)이름Error 등 + ": 글". 트레이스백의 들여 쓴 소스 줄(raise …)은 맞지 않는다
_EXCEPTION_LINE = re.compile(r"(?:[A-Za-z_]\w*\.)*[A-Za-z_]\w*(?:Error|Exception|Exit|Timeout|Interrupt|Expired)(?::.*)?")
_DOTENV_WARNING = re.compile(r"python-dotenv could not parse statement starting at line (\d+)", re.I)
_CONNECT_TOKENS = ("Connection refused", "APIConnectionError", "ConnectError", "ConnectTimeout", "ReadTimeout",
                   "timed out")


def job_error(log_text: str) -> dict | None:
    """작업 로그 끝(최대 JOB_LOG_LINES줄)의 마지막 예외 줄을 사람 말로 바꾼다. 키는 부르는 쪽이 먼저 가린다.
    {"message", "fix", "raw": 그 줄, "warnings": `.env`에서 읽지 못한 줄마다 env_problem}. 예외 줄도 경고도 없으면 None.
    경고는 넘겨받은 글 전체에서 찾는다(파이썬이 뜰 때 찍혀 로그 맨 앞에 있다)."""
    lines = log_text.splitlines()
    numbers = dict.fromkeys(int(m[1]) for m in map(_DOTENV_WARNING.search, lines) if m)
    warnings = [env_problem(n) for n in numbers]
    raw = next((line.rstrip() for line in reversed(lines[-JOB_LOG_LINES:])
                if _EXCEPTION_LINE.fullmatch(line.rstrip())), None)
    if raw is None:
        return {**JOB_ERROR_TEXT["no_line"], "raw": None, "warnings": warnings} if warnings else None
    name = raw.split(":", 1)[0].rsplit(".", 1)[-1]
    if name == "FileNotFoundError" and re.search(r"pNNN|p\d+\.txt|쪽 글자|pages", raw):
        kind = "pages"
    elif name == "KeyError" and "manifest에 없는" in raw:
        kind = "outside"
    elif any(token in raw for token in _CONNECT_TOKENS):
        kind = "connect"
    elif re.search(r"(?<![\w-])401(?!\d)", raw) or "AuthenticationError" in raw:   # 문서 번호 T21-401은 아니다
        kind = "key"
    elif "평가용" in raw:
        kind = "eval"
    else:
        kind = "other"
    return {**JOB_ERROR_TEXT[kind], "raw": raw, "warnings": warnings}


# 화면 API(b_app)의 400·404 오류 본문. error는 지금까지 쓰던 짧은 글 그대로, message는 사실 한 문장, fix는 할 일 한 문장.
# 잠긴 문서(평가용·용도 모름)도 doc_not_in_run·doc_not_in_set·missing_pages로 답하므로 이 글들은 잠긴 이유를 말하지 않는다
PROBLEM_TEXT: dict[str, dict[str, str]] = {
    "unknown_set": {"error": "없는 문서 묶음: {id}", "message": "없는 문서 묶음입니다: {id}.",
                    "fix": "문서 묶음 목록에서 다시 고르세요."},
    "unusable_set": {"error": "고를 수 없는 묶음입니다: {reason}", "message": "고를 수 없는 묶음입니다: {reason}",
                     "fix": "문서 묶음 목록에서 다른 묶음을 고르세요."},
    "unknown_key": {"error": KEY_TEXT["unknown_key"], "message": "없는 정답지입니다: {id}.",
                    "fix": "정답지 목록에서 다시 고르세요."},
    "unusable_key": {"error": KEY_TEXT["unusable_key"], "message": "고를 수 없는 정답지입니다: {reason}",
                     "fix": "정답지 목록에서 다른 정답지를 고르세요."},
    "missing_pages": {"error": "쪽 글자가 없습니다: {where}", "message": "{where}의 쪽 자료가 없습니다.",
                      "fix": "이 문서가 있는 문서 묶음을 다시 고르세요."},
    "missing_run": {"error": "없는 실행: {name}", "message": "없는 실행입니다: {name}.",
                    "fix": "실행 목록에서 다시 고르세요."},
    "doc_not_in_run": {"error": "이 실행에 없는 문서: {doc}", "message": "이 실행에서 열 수 없는 문서입니다: {doc}.",
                       "fix": "이 실행의 문서 목록에서 다시 고르세요."},
    "doc_not_in_set": {"error": "이 묶음에 없는 문서: {doc}", "message": "이 묶음에서 열 수 없는 문서입니다: {doc}.",
                       "fix": "이 묶음의 문서 목록에서 다시 고르세요."},
    "bad_query": {"error": "{detail}", "message": "{detail}", "fix": "입력을 고친 뒤 다시 보내세요."},
}


def problem(kind: str, **facts) -> dict:
    """라우트 오류 본문 {"error", "message", "fix"}. facts는 PROBLEM_TEXT의 칸(id, reason, where, name, doc, detail)을 채운다."""
    return {part: template.format(**facts) for part, template in PROBLEM_TEXT[kind].items()}


# 첫 사용 기록(b_app_journey, GET·PUT /api/journey)의 글. format으로 채운다
JOURNEY_TEXT: dict = {
    # 길의 오류 본문 {error, message, fix}. detail은 기록 검사(invalid)의 문장이다
    "errors": {
        "unavailable": {"error": "첫 사용 기록이 꺼져 있습니다", "message": "첫 사용 기록 파일의 자리가 정해지지 않았습니다.",
                        "fix": "작업 화면을 python scripts/b_app.py로 다시 켜세요."},
        "read_failed": {"error": "기록 파일을 열지 못했습니다", "message": "기록 파일을 열지 못했습니다.",
                        "fix": "runs/manual/journey.json을 읽을 수 있는지 확인하세요."},
        "save_failed": {"error": "기록을 저장하지 못했습니다", "message": "기록을 저장하지 못했습니다.",
                        "fix": "runs/manual 폴더에 쓸 수 있는지 확인하세요."},
        "too_big": {"error": "본문이 16KB를 넘습니다", "message": "보낸 기록이 16KB를 넘습니다.",
                    "fix": "진행 단계, 성공 횟수, 시각, 작업 번호만 담아 보내세요."},
        "bad_body": {"error": "{detail}", "message": "{detail}", "fix": "화면을 새로 고친 뒤 다시 하세요."},
    },
    # 기록 검사(validate)가 거부하는 이유. where는 칸 이름(예 progress.t1.step)
    "invalid": {
        "body": "본문은 journey 칸 하나만 든 JSON 객체여야 합니다.",
        "unknown_key": "받지 않는 칸입니다: {where}.",
        "missing_key": "빠진 칸이 있습니다: {where}.",
        "version": "기록 형식 번호(version)가 2가 아닙니다.",
        "bad_value": "{where} 값이 맞지 않습니다. 받는 값: {expect}.",
    },
    "expect": {
        "object": "객체",
        "object_or_null": "객체 또는 null",
        "time": "브라우저 시각(예 2026-10-31T00:58:00.000Z)",
        "time_or_null": "브라우저 시각(예 2026-10-31T00:58:00.000Z) 또는 null",
        "count": "1 이상의 정수",
        "step": "0~{top} 사이의 정수",
        "state": "not_started, in_progress, skipped, completed 중 하나",
        "active": "t1, t2, null 중 하나",
        "mode": "real 또는 practice",
        "id": "영문·숫자·_·- 64자 이하",
        "id_or_null": "영문·숫자·_·- 64자 이하 또는 null",
        "migrated_from": "1 또는 null",
    },
    # 기록 파일의 일부를 읽지 못해 처음 상태로 돌렸을 때(load의 problems). 화면은 이 문장을 그대로 보인다
    "parts": {
        "file_json": "기록 파일을 JSON으로 읽지 못했습니다.",
        "file_version": "기록 파일의 형식 번호(version)가 2가 아닙니다.",
        "progress": "안내 진행 단계(progress)의 모양이 맞지 않습니다.",
        "outcomes": "성공·연습 기록(outcomes)의 모양이 맞지 않습니다.",
        "pending": "판정 전 시도(pending)의 모양이 맞지 않습니다.",
        "migrated_from": "옛 기록 옮김 표시(migrated_from)의 모양이 맞지 않습니다.",
    },
}


def journey_problem(kind: str, **facts) -> dict:
    """/api/journey 오류 본문 {"error", "message", "fix"}."""
    return {part: template.format(**facts) for part, template in JOURNEY_TEXT["errors"][kind].items()}


# 서버 탭(b_app_servers)이 거절하거나 할 수 없을 때의 글. 사실 한 문장 + "할 일:" (format으로 채운다)
SERVER_TEXT: dict[str, str] = dict(UI_TEXT["servers"]["messages"])

def server_controls(*, running: bool, runpod_ok: bool, rngd_ok: bool, tunnel: dict | None = None,
                    ssh_set: bool = False) -> dict:
    """모델 연결과 별개로 관리 서버를 볼 수 있어야 변경 단추를 연다.
    터널 열기는 실행 중에도 된다(돌고 있는 실행을 해치지 않는다). tunnel은 b_app_servers.tunnel_status 값이다."""
    copy = UI_TEXT["servers"]["controls"]
    reasons = {}
    for action, ready, key in (("pod_create", runpod_ok, "create"), ("pod_delete", runpod_ok, "delete"),
                               ("rngd_up", rngd_ok, "up"), ("rngd_down", rngd_ok, "down")):
        reasons[action] = copy["busy"] if running else copy[key] if not ready else ""
    t = tunnel or {}
    reasons["tunnel_open"] = (copy["no_ssh"] if not ssh_set else copy["no_port"] if t.get("port") is None
                              else copy["open"] if t.get("open") else "")
    reasons["tunnel_close"] = (copy["busy"] if running else copy["closed"] if not t.get("open")
                               else copy["not_owned"] if not t.get("owned") else "")
    return {"can": {action: not reason for action, reason in reasons.items()}, "why": reasons}


LOADING_LATE_MIN = 25                                # 모델 올리기는 보통 15~25분 (RNGD 기록)


def rngd_diagnosis(diagnosis: str | None, loading_since: str | None, now: datetime) -> dict | None:
    """b_app_servers가 낸 RNGD 진단(ok·no_model·tunnel_closed·loading)의 글. 모르는 값이면 None.
    loading_since는 ISO 시각 글이고, now와 시간대가 달라도 된다. 읽지 못하면 지난 시간을 쓰지 않는다."""
    words = UI_TEXT["servers"]["diagnosis"]
    if diagnosis in ("ok", "no_model", "tunnel_closed"):
        copy = words["ready" if diagnosis == "ok" else diagnosis]
        return {"message": copy["fact"], "fix": copy["todo"]}
    if diagnosis != "loading":
        return None
    seconds = None
    try:
        seconds = max(0.0, (now - datetime.fromisoformat(loading_since)).total_seconds())
    except (TypeError, ValueError):
        pass
    copy = words["loading"]
    message = copy["elapsed"].format(minutes=int(seconds // 60)) if seconds is not None else copy["unknown"]
    fix = copy["todo"]
    if seconds is not None and seconds > LOADING_LATE_MIN * 60:
        fix += " " + copy["late"].format(minutes=LOADING_LATE_MIN)
    return {"message": message, "fix": fix}


def server_ui_text() -> dict:
    """옛 키를 보존하며 승인 문구로 안내한다."""
    copy = UI_TEXT["servers"]["status"]
    return {"guide": {"advanced_on": copy["guide"], "advanced_off": copy["guide"]},
            "busy": copy["busy"], "unavailable": copy["unavailable"],
            "action_failure": {"message": copy["failure"]["fact"], "fix": copy["failure"]["todo"]}}


def _date(name: str, started_at) -> str:
    candidates = []
    if re.match(r"^\d{8}(?:_|$)", name):
        candidates.append((name[:8], "%Y%m%d"))
    if started_at:
        candidates.append((str(started_at)[:10], "%Y-%m-%d"))
    for value, fmt in candidates:
        try:
            day = datetime.strptime(value, fmt)
            return f"{day.month}/{day.day}"
        except ValueError:
            continue
    return ""


def _prompt(token: str) -> bool:
    # 세 자리 s003은 안내문이 아니라 문서 번호다.
    return bool(re.fullmatch(r"s\d+", token) and not re.fullmatch(r"s\d{3}", token))


def _input_version(token: str) -> str:
    if token in ("cw", "chars_wrap"):
        return "chars_wrap"
    if re.fullmatch(r"v\d+", token):
        return "version" + token[1:]
    return token if re.fullmatch(r"version\d+", token) else ""


def _condition(token: str) -> str:
    if token in _CONDITIONS:
        return _CONDITIONS[token]
    doc = re.fullmatch(r"([smSM])(\d{3})", token)
    if doc:
        return f"문서 T21-{doc[1].upper()}{doc[2]} 한 건"
    match = re.fullmatch(r"(eval|probe|diag|r)(\d+)", token)
    if match:
        prefix, number = match.groups()
        return {"eval": f"평가 T21-{number} 한 건", "probe": f"탐색 {number}회",
                "diag": f"진단 {number}", "r": f"{number}회차"}[prefix]
    return token


def run_label(info: dict) -> dict:
    """summarize_run 결과(일부 키만 있어도 됨)를 제목·원래 이름·구성 글로 바꾼다."""
    name = info.get("name") or ""
    base = name.removeprefix("manual/")
    date = _date(base, info.get("started_at"))
    inferred = next((tag for tag in sorted(MODEL_LABELS, key=lambda t: (-len(t), t))
                     if re.search(rf"(?:^|_){re.escape(tag)}(?:_|$)", base)), "")
    tag = info.get("model_tag") or inferred
    model = "실버 초안(Claude)" if "_silver_" in name else model_label(tag)

    rest = re.sub(r"^\d{8}(?:_|$)", "", base)
    for known in dict.fromkeys((inferred, tag)):
        if known:
            rest = re.sub(rf"(^|_){re.escape(known)}(?=_|$)", r"\1", rest)
    # 두 토큰으로 나뉘는 입력 판도 한 조건으로 읽는다.
    tokens = re.findall(r"chars_wrap|[^_]+", rest)
    prompt = info.get("prompt_version") or next((t for t in tokens if _prompt(t)), "")
    pages_dir = info.get("pages_dir")
    version = PurePosixPath(str(pages_dir)).name if pages_dir else ""
    version = version or next((_input_version(t) for t in tokens if _input_version(t)), "")

    parts = [" ".join(v for v in (date, model) if v)]
    if prompt:
        parts.append(f"안내문 {prompt}")
    if version:
        parts.append(f"입력 {version}")
    parts.extend(_condition(t) for t in tokens
                 if t not in ("sections", "silver", prompt) and not _prompt(t) and not _input_version(t))
    title = " · ".join(p for p in parts if p)
    if info.get("kind") == "manual":
        title = "[수동] " + title
    return {"title": title, "subtitle": name, "parts": title.split(" · ")}
