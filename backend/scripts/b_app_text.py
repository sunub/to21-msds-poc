"""작업 화면의 표시 이름 (역할 B, 개발 전용, ADR-027).

파일이나 서버를 읽지 않는 순수 함수다. 실행 정보가 이름보다 우선하며,
모르는 조건은 그대로 남겨 표시 이름에서 실행 조건을 잃지 않는다.
"""
import re
from collections import Counter
from datetime import datetime
from math import isfinite
from pathlib import PurePosixPath

from msds.evaluate.score import WEIGHTS    # src 경로는 b_app이 먼저 부르는 _common이 등록한다


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
                     'gold': '사람이 확인한 정답 · {name}',
                     'gold_main': '사람이 확인한 정답'},
             'models': {'qwen36_35b_runpod': 'Qwen3.6 35B · 빌린 서버',
                        'qwen3_30b_a3b_rngd': 'Qwen3 30B · 회사 서버',
                        'gpt_oss_20b_rngd': 'gpt-oss 20B · 회사 서버',
                        'nuextract2_8b_runpod': 'NuExtract 2.0 8B · 빌린 서버',
                        'qwen3vl4b_rngd': 'Qwen3-VL 4B · 회사 서버',
                        'qwen38': 'Qwen3.8 27B (vLLM)',
                        'claude': 'Claude · AI 정답 초안',
                        'gpt': 'GPT · AI 정답 초안'},
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
             'documents': {'label': '시험할 문서 묶음(폴더)', 'count': '개발용 문서 {count}건'},
             'change_documents': '필요할 때 문서 바꾸기',
             'answer': {'label': '비교한 정답',
                        'gold_count': '사람이 확인한 정답 · {count}건',
                        'gold_scope': '정답이 있는 문서만 점수를 매깁니다.',
                        'doc_missing': '선택 문서의 정답 없음'},
             'answer_draft': 'AI 정답 초안 · 사람 확인 전',
             'change_answer': '필요할 때 정답 바꾸기',
             'answer_trust': '점수는 개선 방향을 보는 참고용입니다. 값은 원문과 맞춘 뒤 믿으세요.',
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
             'comparable': '네 결과는 같은 문서 {count}건과 같은 정답으로 비교했습니다.',
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
          'answer': '정답',
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
 'basis': {'label': '{key} 기준 · 채점 문서 {count}건', 'fallback': '확인 안 됨'},
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

COPY_EXCEPTIONS["context.models.gpt"] = "⑤ 수락 11/1 뒤 작은 문제: 정답 초안용 모델 이름"

COPY_EXCEPTIONS.update({'score.basis.label': '승인 구조의 동적 표시 또는 API 누락 상태에 대응하는 일반 문구가 COPY에 없어 보충했습니다.',
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
           'draft': '정답: {concentration} mg/m³.',
           'draft_warning': '정답도 틀릴 수 있습니다. 값을 믿기 전에 원문과 맞춰 보세요.'},
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
          'draft': '정답: 자료 없음.',
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
                        'cost': '켜진 동안 시간당 약 ${cost_per_hour}가 듭니다(예시). 준비 완료 시각은 모릅니다. 요청이 20분 없으면 앱이 지우고, '
                                '앱이 꺼져 있어도 서버 안 타이머가 4시간에 지웁니다.',
                        'action': '시간당 약 ${cost_per_hour} 서버 만들기'},
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
                        'cleanup': '사용 뒤 삭제하세요. 잊어도 요청이 20분 없으면 앱이 지우고, 서버 안 타이머가 4시간에 지웁니다.'}},
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
            'scheduler': '20분 자동 삭제는 앱이 켜져 있을 때 돕니다. 4시간 타이머는 서버 안에서 돌아 앱이 꺼져도 지웁니다.',
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

# Step 6: 승인 COPY의 시험과 작업 문구. 기존 공개 키는 유지한다.
UI_TEXT["jobs"].update({'result_missing': {'fact': '작업은 끝났지만 결과 파일이 없습니다.',
                    'target_kept': '대상을 유지했습니다.',
                    'todo': '결과 조회에 내용이 없습니다({status_code}). 할 일: 작업 기록을 확인하세요.',
                    'open_log': '작업 로그 보기'},
 'target_mismatch': {'fact': '받은 결과가 보낸 시험 대상과 다릅니다.',
                     'todo': '성공을 기록하지 않았습니다. 할 일: 작업 기록에서 보낸 문서와 결과 문서를 맞춰 보세요.'},
 'send_unknown': {'fact': '시험이 보내졌는지 확인하지 못했습니다.', 'todo': '자동으로 다시 보내지 않습니다. 할 일: 작업 기록에서 같은 시험이 있는지 보세요.'},
 'stopped': {'fact': '시험을 멈췄습니다.',
             'late_reply': '이후 늦게 온 응답도 성공으로 기록하지 않습니다.',
             'return_target': '시험 대상으로 돌아가기'},
 'no_runnable': {'fact': '지금 묶음에는 시험할 수 있는 문서가 없습니다.', 'todo': '할 일: 문서 목록에서 시험할 수 없는 이유를 확인하세요.'},
 'confirm': {'stop': {'title': '진행 중인 시험을 멈출까요?',
                      'target': '{doc}의 {section}번 부분. 작업 번호 {job_id}.',
                      'loss': '아직 저장되지 않은 결과를 잃을 수 있습니다.',
                      'action': '확인하고 시험 멈추기'}},
 'try_hint': {'ready': '응답한 모델이 {count}개 있습니다. 모델을 고른 뒤 실제 시험을 시작하세요.',
              'off': '응답한 모델이 없습니다. AI 없이 보낼 내용만 확인할 수 있습니다. 실제 시험을 하려면 AI 켜기와 비용에서 모델을 준비하세요.'},
 'fields': {'model': '문서에서 값을 뽑을 모델입니다. 연결된 모델부터 보여 줍니다.',
            'doc': '시험할 개발용 문서입니다. 평가용 문서는 고를 수 없습니다.',
            'pages': 'AI에게 보낼 원문 글자를 모은 폴더입니다.',
            'scope': '다시 시험할 부분을 고릅니다. 문서 전체를 고르면 16개 부분을 보냅니다.',
            'prompt': 'AI에게 시킬 일을 적습니다. 한 부분만 시험할 때 고칠 수 있습니다.',
            'base_run': '새 답을 끼워 넣어 점수를 비교할 이전 결과입니다. 자동 선택은 같은 모델의 최근 개발용 10건 결과를 씁니다.',
            'dry_run': 'AI 없이 보낼 원문과 시킬 일만 확인합니다.',
            'repeat': '같은 조건으로 실행할 횟수입니다. 1~10회로 정합니다.',
            'run_name': '결과를 모아 둘 폴더 이름입니다. 회차마다 _r1, _r2가 붙습니다.',
            'compare_label': '비교표에서 실행을 부를 이름입니다. 비우면 실행 이름을 씁니다.'},
 'stages': {'input': 'AI에게 보낸 원문 글자입니다. 앞에 붙은 p2:L23은 2쪽 23번째 줄입니다.',
            'prompt': 'AI에게 시킨 일입니다. 글 전체를 기록 파일에 남기지 않습니다.',
            'raw_answer': 'AI가 쓴 답을 그대로 보여 줍니다.',
            'parsed': 'AI의 답에서 읽어 낸 값입니다. 표로 읽지 못해 버린 줄 수도 보입니다.',
            'to21': '읽어 낸 값을 정해진 결과 칸(TO21 JSON)에 넣은 내용입니다.',
            'score': '이전 결과에서 시험한 부분의 답만 바꿔 다시 계산한 점수입니다. 전체를 새로 시험한 점수는 아닙니다.'},
 'actions': {'send': '실제 시험 시작하기',
             'preview': 'AI 없이 보낼 내용 확인하기',
             'run_unavailable': '응답한 모델을 고르면 시험할 수 있습니다.',
             'more_summary': '여러 문서 시험과 비교표 만들기를 펼쳐 보세요.'},
 'kinds': {'dev10': '개발용 10건 시험',
           'single': '문서 한 건 시험',
           'probe': '일부 문서 시험',
           'silver': 'AI 정답 초안 만들기',
           'eval': '평가용 기록 · 열람 제한',
           'outside': '새 문서 시험 · 점수 없음',
           'models': '비교표'},
 'trial': {'title': '같은 부분을 AI에게 다시 읽힐 준비가 됐습니다.',
           'target': '{doc} · {section}번 부분 · 작업장 공기 중 허용 농도',
           'base_result': '비교할 결과: {time} · {score}점',
           'company_ready': '{model}가 응답했습니다. 회사 서버를 사용합니다.',
           'company_cost': '회사 서버는 추가 임대료가 없습니다.',
           'duration': '시험은 약 {seconds}초~{minutes}분입니다(예시). 준비 시간은 별도입니다.',
           'practice_meaning': 'AI 없이 보낼 내용만 확인하는 연습입니다. 실제 시험 기록과 점수는 생기지 않습니다.',
           'next_options': '첫 시험 안내와 여러 문서 시험',
           'start_guide': '한 부분 시험 안내 시작하기',
           'open_batch': '여러 문서 시험하기',
           'rented_ready': '{model}가 응답했습니다. 빌린 서버를 사용합니다.',
           'rented_cost': '시간당 약 ${cost_per_hour}의 실제 요금이 나갑니다(예시).'},
 'prompt': {'hint': '예: “숫자와 단위를 원문 그대로 옮기세요.” 고친 글은 새로고침하면 사라집니다.',
            'retest_hint': '고쳐서 점수를 비교하세요. 그대로 같은 부분을 다시 시험해도 됩니다.',
            'details': '설명의 출처와 보관 방식 보기',
            'origin': '기본 설명은 모델별 기본 설정에서 가져옵니다.',
            'mode': '설명 사용 방식',
            'edit': '기본 설명 고쳐 쓰기',
            'default': '기본 설명 그대로',
            'review_foreign': '다른 모델이나 다른 부분의 글을 가져오면 전송 전에 재검토합니다.',
            'memory_only': '고친 글 전체는 현재 화면에만 보관합니다.',
            'delete_temp': '전송 임시 파일은 보낸 뒤 지웁니다.',
            'hash_only': '기록에는 내용 확인값(해시)만 남깁니다.',
            'open_review': '출처가 다른 설명 재검토 보기'},
 'focus': {'title': '원문 화면에서 고른 문제 값',
           'pair': '비교한 정답: {key_value} · AI가 쓴 값: {ai_value}',
           'missing': '비교한 정답: {key_value} · AI가 쓴 값: 없음(못 뽑음)',
           'made': '비교한 정답: 없음 · AI가 쓴 값: {ai_value}(만듦)',
           'line': '원문 {page}쪽 {line_no}번째 줄: {line_text}',
           'line_estimated': '원문 {page}쪽 {line_no}번째 줄(추정): {line_text}',
           'none': '원문 화면에서 고른 값이 없습니다. 이 부분 전체를 다시 시험합니다.'},
 'scope': {'expand': '시험 범위와 이전 결과 바꾸기',
           'label': '다시 읽힐 범위',
           'single': '한 부분 · {section}번 부분',
           'multiple': '여러 부분 · {section}번과 {other_section}번 부분',
           'whole': '문서 전체 · 16개 부분',
           'prompt_limit': '설명 수정은 한 부분 시험에서만 사용합니다.',
           'open_multiple': '여러 부분 시험 화면 보기',
           'open_whole': '문서 전체 시험 화면 보기',
           'doc_id': '문서 관리 번호',
           'sets': '원문과 다음 시험 자료',
           'base_run': '새 답을 끼워 넣을 이전 결과',
           'auto_selected': '자동 선택 ·',
           'check_runnable': '고른 문서를 시험할 수 있는지 확인합니다.',
           'open_mismatch': '묶음이 다른 경우 보기'},
 'off': {'title': '다시 시험하려면 AI 모델이 켜져 있어야 합니다.', 'model': '{model}는 아직 준비되지 않았습니다.', 'connect': 'AI 연결하기'},
 'running': {'title': '시험이 진행 중입니다.',
             'elapsed': '{minutes}분 {seconds}초 경과',
             'target': '{doc}의 {section}번 부분을 {model}가 읽고 있습니다.',
             'open_jobs': '작업 기록 보기',
             'leave_screen': '다른 화면으로 가도 시험은 계속됩니다.',
             'no_resend': '같은 시험을 자동으로 다시 보내지 않습니다.',
             'details': '보낸 조건과 중단',
             'sent': '보낸 값',
             'set': '문서 묶음',
             'previous_set': '이전 개발 자료',
             'answer': 'AI가 먼저 만든 정답 · 보낼 때 고른 기준',
             'job_id': '작업 번호',
             'real_call': '실제 호출',
             'real_trial': '실제 시험. 연습 아님.',
             'stop': '시험 멈추기',
             'open_finished': '완료 상태 보기',
             'open_success': '성공 결과 보기',
             'open_parse_failure': '값을 읽지 못한 결과 보기'},
 'done': {'title': '이 부분의 실제 시험이 끝났습니다.',
          'success': '실제 시험 성공',
          'target': '{doc} · {section}번 부분 · {model}',
          'keep_base': '저장된 이전 결과는 그대로 남아 있습니다.',
          'open_source': '같은 위치의 원문 보기'},
 'result': {'partial_score': '이 부분만 바꿔 계산한 점수: {before}점 → {after}점.',
            'partial_meaning': '이전 결과에서 {section}번 부분의 답만 바꿔 다시 계산했습니다. 전체를 새로 시험한 점수는 아닙니다.',
            'batch_effect': '이번 점수 차이는 한 문서의 한 부분만 반영합니다. 전체 문서에 미친 효과는 ‘여러 문서 시험하기’로 확인하세요.',
            'plain_done': '시험 작업이 끝났습니다.',
            'practice_unconfirmed': '실제 응답 기록이 없습니다. 연습 여부는 작업 기록을 확인하세요.',
            'section': '{section}번 부분',
            'raw_meta': '방식 {mode} · 끝난 이유 {reason} · {seconds}초',
            'no_answer': '답변 없음',
            'parse_meta': '버린 줄 {discarded}개 · 다시 뽑음 {retries}회 · 시도 {attempts}회',
            'ok': '해석 성공',
            'bad': '해석 실패',
            'json': '읽어 낸 값 보기',
            'input_meta': '원문 폴더 {pages} · 나눈 방법 {method} · 안전자료 {count}개(첫 번째 자료만 사용)',
            'input_rows': '{section}번 부분 · {format} · {count}줄(머리 {preamble}줄) · {first} ~ {last} · 쪽 '
                          '{pages} · 이미지 {images} · {method}',
            'format_rows': '표 형식',
            'format_json': 'JSON',
            'fields_count': '{name}: {count}개',
            'key': '점수 기준: {label}',
            'key_unknown': '기록 당시 정답지 미확인',
            'whole_stats': '성공 {ok}개 · 실패 {failed}개 · 다시 뽑음 {retries}회 · {seconds}초',
            'weighted': '가중 종합 {score}점',
            'before': '전',
            'after': '후',
            'changed': '바뀐 채점 항목',
            'unchanged': '바뀐 채점 항목이 없습니다.',
            'not_made': '이 단계의 결과가 없습니다.',
            'pending': '끝나면 결과를 읽습니다.',
            'retry': '결과 다시 읽기'},
 'detail': {'input': '1. 보낸 입력',
            'pages': '원문 폴더',
            'split': '나눈 방법',
            'heading_based': '제목 기준',
            'msds_count': '안전자료 수',
            'first_only': '{count}개. 첫 번째 자료만 사용.',
            'range_label': '부분과 범위',
            'range': '{section}번 부분. {page}쪽 {first_line}~{last_line}번째 줄.',
            'line_count': '글자 {count}줄. 쪽과 줄 번호를 앞에 붙임.',
            'unused': '사용 안 함',
            'prompt': '2. AI에게 시킨 일 기록',
            'prompt_edited': '{section}번 부분의 설명을 수정했습니다.',
            'prompt_hash': '내용 확인값(해시):',
            'no_full_text': '전문은 기록 파일에 남기지 않습니다.',
            'raw_answer': '3. AI의 원래 답',
            'response': '표 형식. 정상 종료. 응답 시간 {seconds}초.',
            'no_answer': '응답이 없을 때는 ‘답변 없음’을 표시합니다.',
            'parsed': '4. 읽어 낸 값',
            'parse_stats': '해석 성공. 버린 줄 {discarded}개. 다시 뽑음 {retries}회. 시도 {attempts}회.',
            'tokens': '입력 길이 {input_tokens}토큰. 출력 길이 {output_tokens}토큰.',
            'token_meaning': 'AI가 글을 처리하는 길이 단위가 토큰입니다.',
            'evidence_checked': '오류 없음. 근거 줄 검사 완료.',
            'converted': '5. 정해진 형식으로 바꾼 값',
            'fields': '노출기준 표 {rows}행. 객체 칸 {fields}개.',
            'no_extra': '해당 부분의 추가 설명은 없습니다.',
            'score': '6. 시험 전후 점수',
            'partial_score': '이 부분만 바꿔 계산하면 {before}점에서 {after}점이 됩니다.',
            'base_run': '새 답을 끼워 넣은 이전 결과:',
            'key': '보낼 때 고른 정답: AI가 먼저 만든 정답.',
            'key_hash': '정답 파일 내용의 확인값:',
            'hash_meaning': '확인값은 현재 정답 파일을 구분하는 표시입니다. 과거 정답을 복원할 수는 없습니다.',
            'changed_criterion': '바뀐 점수 기준: 작업장 공기 중 허용 농도.',
            'no_causality': '한 번의 결과로 개선 원인을 확정하지 않습니다.'},
 'completion': {'title': '결과 기록과 완료 판정',
                'job_id': '작업 번호:',
                'path': '결과 위치:',
                'evidence': '확인 근거',
                'value': '이 장면의 값',
                'state': '작업 상태',
                'exit_code': '종료 코드',
                'practice': '연습 여부',
                'shape': '결과 모양',
                'fields': 'plan, results, fields, base_run, score, score_skipped, saved',
                'parse': '선택 부분의 해석 결과',
                'target_match': '대상 일치',
                'same_section': '보낸 문서와 {section}번 부분이 같음',
                'record': '성공 기록',
                'real_success': '실제 성공 기록',
                'open_missing': '결과 파일이 없는 상태 보기'},
 'parse_failed': {'title': 'AI가 답했지만 {section}번 부분 값을 읽지 못했습니다.',
                  'state': '값 해석 실패',
                  'fact': '작업은 끝났지만 AI의 답을 값으로 읽지 못했습니다.',
                  'todo': '실제 시험 성공은 기록하지 않았습니다. 할 일: {stage}단계의 오류를 보고 다시 시험하세요.',
                  'retry': '같은 조건으로 다시 시험하기',
                  'columns': '해석 실패. 표의 열 수가 맞지 않습니다.',
                  'column_count': '오류: 필요한 {expected}개 칸 중 {received}개만 받았습니다.',
                  'no_fields': '해석에 실패해 최종 값을 만들지 못했습니다.',
                  'no_score': '이 부분을 해석하지 못해 점수 비교를 완료하지 못했습니다.',
                  'no_record': '기록하지 않음'},
 'practice_done': {'title': '입력과 설명만 확인했습니다.',
                   'state': '연습 완료',
                   'no_success': '실제 시험 성공은 아직 없습니다.',
                   'connect': '모델 연결하기',
                   'omitted_stages': '연습에서는 {first_stage}~{last_stage}단계의 모델 응답과 점수를 만들지 않습니다.',
                   'shape': 'plan만 있음',
                   'record': '연습에만 기록'},
 'score_skipped': {'fact': '시험 전후 점수는 계산하지 않았습니다.',
                   'no_key': '이 문서에 대응하는 정답이 없습니다.',
                   'reason': '정답이 없어 점수 계산을 생략했습니다.'},
 'multiple': {'title': '{section}번과 {other_section}번 부분을 함께 시험합니다.',
              'prompt': 'AI에게 시킬 일',
              'no_edit': '설명을 고쳐 쓰려면 한 부분만 고르세요.',
              'send': '선택한 부분 다시 시험하기',
              'change_scope': '범위 바꾸기',
              'single': '한 부분으로 돌아가기',
              'whole': '문서 전체 고르기',
              'default_prompt': '여러 부분은 각 부분의 기본 설명을 사용합니다.'},
 'whole': {'title': '{doc}의 전체를 시험합니다.',
           'prompts': '16개 부분의 기본 설명을 사용합니다.',
           'journey_scope': '첫 시험 안내는 한 부분 실제 시험으로 완료합니다.',
           'send': '문서 전체 다시 시험하기'},
 'whole_running': {'title': '문서의 16개 부분을 시험하고 있습니다.',
                   'state': '진행 중',
                   'elapsed': '{doc}. 시작 후 {minutes}분이 지났습니다.',
                   'open_result': '문서 전체 결과 보기'},
 'whole_done': {'title': '16개 부분 중 {failed}개를 해석하지 못했습니다.',
                'success': '성공한 부분',
                'failure': '실패한 부분',
                'failed_count': '{section}번 부분 {count}개',
                'duration': '걸린 시간',
                'raw_path': '원래 답 폴더',
                'kind': '이 결과는 문서 전체 시험 기록입니다.',
                'no_journey_success': '한 부분 안내의 실제 성공으로 대신 세지 않습니다.',
                'return_single': '한 부분 시험으로 돌아가기',
                'shape': '전체 결과의 기록 구조',
                'fields': 'plan, run, summary, score, base_run, saved',
                'summary': '각 부분의 결과는 summary에서 읽습니다. 항 시험의 results를 가정하지 않습니다.'},
 'set_mismatch': {'title': '원문과 다음 시험의 문서 묶음이 다릅니다.',
                  'source': '읽은 원문',
                  'recorded': '실행 당시 · 이전 개발 자료 {version}판',
                  'next': '다음 시험',
                  'current': '현재 선택 · 이전 개발 자료 {version}판',
                  'select': '시험에 쓸 묶음',
                  'source_option': '원문을 본 {version}판',
                  'current_option': '현재 선택한 {version}판',
                  'prepare': '고른 묶음으로 시험 준비하기',
                  'keep_context': '문서와 {section}번 부분과 편집한 설명은 유지합니다.'},
 'prompt_review': {'title': '이 설명은 다른 부분에서 가져왔습니다.',
                   'target': '현재 대상은 {doc}의 {section}번 부분입니다.',
                   'origin': '설명 출처는 {model}의 {section}번 부분입니다.',
                   'todo': '{section}번 부분에 맞는 설명으로 고쳐 주세요.',
                   'restore': '{section}번 부분 기본 설명으로 돌아가기'},
 'list': {'title': '진행 중인 작업과 결과를 여기에서 이어 봅니다.',
          'single_trial': '한 부분 시험',
          'target': '{doc} · {section}번 부분',
          'elapsed': '진행 중 · {minutes}분 {seconds}초',
          'batch_target': '개발용 {count}건 · {repeats}회',
          'rounds_done': '완료 · {completed}/{total}회',
          'selected_runs': '선택 결과 {count}개',
          'external': '다른 터미널 작업',
          'target_unknown': '대상 확인 안 됨',
          'unstoppable': '진행 중 · 중단 불가',
          'open_trial': '선택한 시험 상태 보기'},
 'selected': {'title': '선택한 작업의 상세',
              'target': '선택: {doc}의 {section}번 부분 시험.',
              'context': '시작 당시 조건',
              'key': 'AI가 만든 정답 ·',
              'prompt': '수정 설명',
              'no_warning': '설정 경고는 없습니다.',
              'path': '기록 위치:',
              'restore': '상세를 닫아도 선택 행과 읽던 위치는 유지합니다.',
              'legacy': '오래된 작업과 알 수 없는 상태',
              'open_missing_target': '기록 당시 대상이 없는 작업 보기',
              'open_unknown': '끝을 알 수 없는 작업 보기'},
 'external': {'title': '이 작업은 다른 터미널에서 시작했습니다.',
              'record': '현재 기록',
              'process': '문서를 처리하는 프로그램',
              'running': '실행 중',
              'unknown': '확인 안 됨',
              'unstoppable': '이 화면에서는 중단할 수 없음',
              'no_docs': '이 작업에는 처리한 문서가 기록되지 않았습니다.',
              'no_journey_success': '이 작업은 첫 시험 성공 기록에 넣지 않습니다.',
              'back': '작업 목록으로 돌아가기'},
 'legacy': {'title': '이 작업의 시작 당시 기준을 확인할 수 없습니다.',
            'no_target': '기존 작업에는 대상 기록이 없습니다.',
            'available': '보관된 로그와 종료 코드는 볼 수 있습니다.',
            'log': '기록 원문',
            'exit_code': '종료 코드: {count}.'},
 'batch': {'title': '여러 문서를 같은 조건으로 실행하세요.',
           'ready': '{model}가 준비되어 있습니다.',
           'select_docs': '문서 고르기',
           'select_all': '개발용 문서 {count}건 모두 고르기',
           'eval_locked': '평가용 {count}건 · 최종 성능 평가를 위해 잠김',
           'outside_locked': '목록 밖 예시 문서 · 현재 실행기가 본 실행을 지원하지 않음',
           'repeats': '같은 문서를 처리할 횟수',
           'summary': '선택 {count}건. 반복 {repeats}회. 이전 개발 자료를 사용합니다.',
           'key': '비교할 정답은 AI가 먼저 만든 정답입니다.',
           'start': '선택한 문서 시험 시작하기',
           'details': '실행 전 조건과 이름 규칙',
           'kind': '실행 종류는 서버가 분류한 값을 사용합니다.',
           'exclude_eval': '개발용 전체 선택에는 평가용 문서를 포함하지 않습니다.',
           'repeat_range': '반복은 1~10회입니다.',
           'suffix_intro': '두 번째 결과 이름 끝에는',
           'suffix': '_r2',
           'suffix_end': '가 붙습니다.',
           'base_auto': '비교할 이전 결과은 선택한 범위에 맞춰 자동으로 찾습니다.',
           'keep_awake': '실행 중에는 컴퓨터가 잠들지 않도록 유지합니다.',
           'confirm': '서버가 추가 확인을 요구하면 확인 후 시작합니다.',
           'open_confirm': '서버 확인이 필요한 경우 보기',
           'runnable': '문서별 실행 가능 여부',
           'outside_policy': '목록 밖 문서는 서버가 허용한 경우에만 실행합니다.',
           'no_name_inference': '문서 이름으로 허용 여부를 판단하지 않습니다.',
           'open_outside': '목록 밖 문서 실행 가능 상태 보기'},
 'outside': {'title': '이 문서는 여러 문서 시험에 넣을 수 있습니다.',
             'server_state': '서버가 알려 준 상태',
             'single_forbidden': '불가. 문서 목록에 등록되지 않음.',
             'batch_allowed': '가능. 실행기가 문서 정보를 읽을 수 있음.',
             'no_score': '정답이 없어 점수는 계산하지 않습니다.',
             'back': '여러 문서 선택으로 돌아가기'},
 'batch_running': {'title': '개발용 문서 {count}건을 실행하고 있습니다.',
                   'round': '{total}회 중 {round}회 진행 중',
                   'run_name': '실행 이름은 {run}입니다.',
                   'context': '시작 당시 문서 묶음과 모델을 계속 사용합니다.',
                   'rented': '빌린 서버에서 개발용 문서 {count}건을 실행하고 있습니다.'},
 'multiple_running': {'title': '{section}번과 {other_section}번 부분을 시험하고 있습니다.',
                      'sent': '선택한 두 부분을 보냈습니다.',
                      'progress': '{doc}의 한 부분씩 결과를 확인합니다.'},
 'status': {'running': '돌아감', 'done': '끝남', 'failed': '실패', 'stopped': '멈춤', 'unknown': '모름'},
 'kind': {'try': '한 부분 시험', 'run': '여러 문서 시험', 'compare': '비교표'},
 'record': {'unknown': '기록 당시 기준 미확인',
            'unknown_tip': '이전 앱에서 시작한 작업이라 끝난 상태를 모릅니다. 로그나 결과 폴더를 보세요.',
            'empty': '아직 작업이 없습니다.',
            'started': '시작 시각',
            'progress': '진행',
            'kind': '종류',
            'name': '이름표',
            'conditions': '대상과 조건 보기',
            'reload': '작업 다시 읽기',
            'recovered': '작업 목록을 다시 읽었습니다.',
            'options_recovered': '시험 조건을 다시 읽었습니다.',
            'seconds': '{seconds}초',
            'round': '{name}: {total}건 중 {done}건',
            'pid': '프로세스 번호: {pid}',
            'close_log': '로그 닫기',
            'log_empty': '아직 로그가 없습니다.',
            'stop': '작업 멈추기',
            'stopped': '작업을 멈췄습니다.',
            'not_stopped': '이미 끝났거나 멈출 수 없는 작업입니다.',
            'confirm_stop': '이 작업을 멈출까요?',
            'confirm_action': '확인하고 작업 멈추기',
            'exit_missing': '종료 코드는 기록되지 않았습니다.'},
 'form': {'model': 'AI 모델',
          'doc': '문서',
          'section': '{section}번 부분',
          'all': '문서 전체 · 16개 부분',
          'prompt': 'AI에게 시킬 일(지시문)',
          'load_prompt': '기본 설명 불러오기',
          'no_sections': '시험할 부분을 하나 이상 고르세요.',
          'prompt_empty': '설명이 비었습니다. 기본 설명을 불러온 뒤 고치세요.',
          'prompt_foreign': '다른 모델이나 부분의 설명입니다. 기본 설명을 다시 불러온 뒤 고치세요.',
          'prompt_loading': '기본 설명을 불러오고 있습니다.',
          'base_auto': '자동 선택',
          'run_name': '실행 이름',
          'suggest': '제안한 이름 쓰기',
          'select_all': '실행 가능한 문서 모두 고르기',
          'select_none': '선택 비우기',
          'count': '선택 {count}건 · 반복 {repeats}회',
          'reload': '시험 조건 다시 읽기',
          'waiting': '시험 결과를 고르면 여기에 표시합니다.',
          'no_models': '고를 수 있는 모델이 없습니다.',
          'no_doc': '문서를 고르세요.',
          'sent': '작업을 시작했습니다. 작업 기록에서 진행을 볼 수 있습니다.',
          'invalid_run': '문서와 실행 이름을 고르고 반복을 1~10회로 정하세요.',
          'missing_context': '문서 묶음과 정답지를 먼저 고르세요.',
          'sending': '보내는 중입니다.',
          'focus_line': '원문 줄: {line}',
          'focus_estimated': '원문 줄(추정): {line}',
          'source_set': '원문을 본 묶음: {set}',
          'next_set': '다음 시험의 묶음: {set}'},
 'compare': {'label': '비교표 표시 이름',
             'key_default': '비교표 파일은 기본 정답 초안(silver/claude)으로 계산합니다. 위에서 고른 정답지는 이 파일에 적용되지 않습니다.',
             'count': '선택한 실행 {count}개',
             'unavailable': '정답 생성·평가·비교표 기록은 선택할 수 없습니다.',
             'empty': '비교할 실행이 없습니다.',
             'need_title': '비교할 실행과 표 제목을 고르세요.'}})
UI_TEXT["errors"]["job"] = {'pages': {'message': '원문 쪽 글자가 있는 폴더나 파일을 찾지 못했습니다.', 'fix': '할 일: 해당 문서의 원문이 있는 묶음을 다시 고르세요.'},
 'outside': {'message': '현재 실행기는 이 문서를 시험할 수 없습니다.', 'fix': '할 일: 시험 가능한 개발 문서를 고르세요.'},
 'connect': {'message': '모델 서버에 연결하지 못했습니다.', 'fix': '할 일: AI 켜기와 비용에서 모델 상태를 확인하세요.'},
 'key': {'message': '모델 서버가 키를 거절했습니다.', 'fix': '할 일: 모델 접속 키가 서버를 켤 때 쓴 키와 같은지 설정 파일에서 확인하세요.'},
 'eval': {'message': '평가용 문서는 시험할 수 없습니다.', 'fix': '할 일: 개발용 문서를 고르세요.'},
 'other': {'message': '작업이 오류로 끝났습니다.', 'fix': '할 일: 마지막 오류 기록을 확인하세요.'},
 'no_line': {'fix': '할 일: 작업 기록을 열어 마지막 오류를 확인하세요.'}}
COPY_EXCEPTIONS.update({'jobs.status.running': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.status.done': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.status.failed': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.status.stopped': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.status.unknown': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.kind.try': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.kind.run': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.kind.compare': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.unknown': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.unknown_tip': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.empty': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.started': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.progress': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.kind': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.name': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.conditions': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.reload': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.recovered': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.options_recovered': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.seconds': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.round': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.pid': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.close_log': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.log_empty': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.stop': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.stopped': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.not_stopped': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.confirm_stop': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.confirm_action': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.record.exit_missing': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.model': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.doc': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.section': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.all': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.prompt': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.load_prompt': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.no_sections': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.prompt_empty': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.prompt_foreign': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.prompt_loading': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.base_auto': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.run_name': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.suggest': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.select_all': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.select_none': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.count': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.reload': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.waiting': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.no_models': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.no_doc': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.sent': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.invalid_run': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.missing_context': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.sending': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.focus_line': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.focus_estimated': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.source_set': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.form.next_set': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.compare.label': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.compare.key_default': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.compare.count': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.compare.unavailable': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.compare.empty': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.compare.need_title': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.plain_done': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.practice_unconfirmed': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.section': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.raw_meta': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.no_answer': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.parse_meta': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.ok': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.bad': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.json': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.input_meta': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.input_rows': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.format_rows': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.format_json': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.fields_count': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.key': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.key_unknown': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.whole_stats': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.weighted': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.before': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.after': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.changed': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.unchanged': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.not_made': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.pending': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.',
 'jobs.result.retry': '동적 작업 조건과 상태 및 API 빈칸을 표시하는 일반 문구입니다. BUILD step 6에 근거를 기록합니다.'})

UI_TEXT["journey"] = {'record': {'errors': {'unavailable': {'message': '첫 사용 기록의 저장 위치가 설정되지 않았습니다.',
                                       'fix': '할 일: 앱을 켠 터미널에서 python scripts/b_app.py로 다시 시작하세요.'},
                       'read_failed': {'message': '기록 파일을 열지 못했습니다.',
                                       'fix': '할 일: runs/manual/journey.json 파일을 읽을 수 있는지 확인하세요.'},
                       'save_failed': {'message': '기록을 저장하지 못했습니다.',
                                       'fix': '할 일: runs/manual 폴더에 파일을 쓸 수 있는지 확인하세요.'},
                       'too_big': {'message': '보낸 기록이 16KB를 넘습니다.',
                                   'fix': '할 일: 기록에는 진행 단계와 횟수와 시각과 작업 번호만 보내세요.'},
                       'bad_body': {'fix': '할 일: 화면을 새로 고친 뒤 안내를 다시 여세요.'}},
            'invalid': {'body': '안내 기록의 형식이 맞지 않습니다. journey 칸 하나가 필요합니다.',
                        'unknown_key': '사용할 수 없는 기록 칸입니다: {where}.',
                        'missing_key': '기록에 필요한 칸이 빠졌습니다: {where}.',
                        'version': '안내 기록의 형식 번호가 2가 아닙니다.',
                        'bad_value': '{where} 칸의 값이 맞지 않습니다. 필요한 값: {expect}.'},
            'expect': {'object': '이름과 값을 묶은 기록(JSON 객체)',
                       'object_or_null': '이름과 값을 묶은 기록 또는 비어 있음(null)',
                       'time': '화면에서 기록한 시각(예: 2026-10-31T00:58:00.000Z)',
                       'time_or_null': '화면에서 기록한 시각 또는 비어 있음(null)',
                       'count': '1 이상의 정수',
                       'step': '0부터 {top}까지의 정수',
                       'state': '시작 전(not_started), 진행 중(in_progress), 건너뜀(skipped), 완료(completed) 중 하나',
                       'active': '갈래 1(t1), 갈래 2(t2), 선택 없음(null) 중 하나',
                       'mode': '실제 시험(real) 또는 연습(practice)',
                       'id': '영문과 숫자 및 _와 -만 사용한 64자 이하 이름',
                       'id_or_null': '영문과 숫자 및 _와 -만 사용한 64자 이하 이름 또는 비어 있음(null)',
                       'migrated_from': '1 또는 비어 있음(null)',
                       'screen': '안내 화면 이름 G01부터 G15까지 중 하나 또는 비어 있음(null)',
                       'choices': '처음 해 볼 일 score, source, retest, ai 중 겹치지 않는 목록',
                       'practices': '직접 해 보기 p1, p2, p3 중 겹치지 않는 목록'},
            'parts': {'file_json': '안내 기록 파일을 읽을 수 있는 형식이 아닙니다.',
                      'file_version': '안내 기록 파일의 형식 번호가 2가 아닙니다.',
                      'progress': '안내 진행 기록을 읽지 못했습니다.',
                      'outcomes': '실제 성공과 연습 기록을 읽지 못했습니다.',
                      'pending': '결과 확인을 기다리는 시험 기록을 읽지 못했습니다.',
                      'migrated_from': '옛 기록을 옮겼는지 확인하지 못했습니다.'}},
 'start': {'intro': '저장된 점수에서 문제 값을 찾고 원문과 맞춰 봅니다.',
           'first': '먼저 저장된 결과로 시작하세요. AI를 켜지 않아도 됩니다.',
           'step_one': '최근 점수와 목표를 읽으세요.',
           'step_two': '가장 큰 문제의 원문을 여세요.',
           'step_three': '문제 값과 선택된 원문 줄을 맞춰 보세요.',
           'empty': '저장된 결과가 없어 결과 읽기 안내를 시작할 수 없습니다. 할 일: 한 부분 시험을 준비하세요.',
           'unscored': '점수가 있는 결과가 없습니다. 할 일: 결과 목록에서 상태를 확인하세요.',
           'no_problem': '열어 볼 문제 값이 없어 안내를 마칠 수 없습니다. 할 일: 기준별 점수를 보거나 안내를 건너뛰세요.',
           'no_line': '이 값의 원문 줄을 찾지 못했습니다. 할 일: 해당 부분의 원문을 직접 읽으세요.',
           'resume': '안내를 이어가려면 최근 결과에서 문제를 다시 고르세요.',
           'success': '문제 값과 실제 원문 줄을 함께 확인했습니다.',
           'later': '다음에 할 수 있는 일',
           'done': '안내 완료',
           'current': '현재 단계',
           'skipped': '건너뜀',
           'dismiss': '안내 닫기',
           'replay': '처음부터 다시 보기',
           'loading': '저장된 결과 목록을 읽고 있습니다.'},
 'choice': {'title': '먼저 끝내고 싶은 일을 고르세요.',
            'read_title': '1. 저장된 점수와 원문 읽기 · 추천',
            'read_action': '저장된 점수에서 가장 큰 문제를 엽니다.',
            'read_success': '문제 값과 실제 원문 줄을 함께 확인하면 끝납니다.',
            'read_ready': '저장된 결과가 있어 바로 시작할 수 있습니다.',
            'start_read': '저장된 결과로 시작하기',
            'trial_title': '2. 한 부분을 실제로 시험하기',
            'trial_action': '개발용 문서의 한 부분을 모델에 보냅니다.',
            'trial_success': 'AI가 뽑은 값을 읽는 데 성공한 결과를 열면 끝납니다.',
            'trial_requires_model': '실제 시험에는 AI를 먼저 켜야 합니다.',
            'start_trial': '한 부분 시험 준비하기',
            'practice': 'AI 없이 보낼 내용만 확인하는 연습도 할 수 있습니다.',
            'skip': '안내 건너뛰고 최근 결과 보기',
            'unknown': '준비 상태를 확인하지 못했습니다.'},
 'history': {'title': '안내 기록 · 실제 성공과 연습은 별도',
             'real_success': '실제로 해냄',
             'read_track': '1. 점수와 원문',
             'none': '아직 없음',
             'trial_track': '2. 한 부분 시험',
             'first_count': '{time} 처음. 모두 {count}회.',
             'replay_progress': '다시 보기는 진행 단계만 처음으로 돌립니다.',
             'keep_outcomes': '실제 성공 시각과 연습 횟수는 지우지 않습니다.',
             'details': '기록과 중단 상태 보기',
             'resume': '중간부터 이어하기',
             'open_save_failure': '기록 저장 실패 보기',
             'open_pending': '지난 시험 이어 보기'},
 'replay': {'start': '안내 다시 시작하기', 'keep_job': '진행 중인 시험은 멈추지 않습니다. 결과는 작업 기록에서 봅니다.'},
 'read': {'track': '갈래 {track} 안내',
          'instruction': '최근 점수와 목표 점수을 읽으세요.',
          'two_targets': '전체 점수의 목표와 필수 기준의 목표는 따로 봅니다.',
          'next_problem': '다음: 가장 큰 문제 보기',
          'completed': '갈래 1을 마쳤습니다. 성공 기록은 안내를 다시 봐도 남습니다.',
          'key_unusable': '고른 정답지를 쓸 수 없습니다.',
          'key_todo': '할 일: 정답지를 바꾼 뒤 최근 결과를 다시 읽으세요.',
          'same': '이 값은 정답과 같습니다. 할 일: 정답과 다른 값을 고르세요.',
          'other': '안내 중인 문제와 다른 항목입니다. 할 일: 가장 큰 문제로 돌아가세요.',
          'no_section': '이 문제는 한 항에 묶이지 않습니다. 할 일: 항목별 문제를 보거나 갈래를 건너뛰세요.'},
 'problem': {'loss': '{section}번 부분에서 전체 점수 {loss}점이 깎였습니다.',
             'evidence': '틀린 값은 AI가 적은 근거 줄이 있어 바로 맞춰 볼 수 있습니다.',
             'unavailable': '열어 볼 수 없는 경우',
             'none': '문제 없음',
             'unlinked': '문서나 부분 연결 없음'},
 'unlinked': {'title': '이 문제의 원문 줄로 바로 이어 드릴 수 없습니다.',
              'stay': '안내는 이 단계에 머뭅니다.',
              'reason': '문서나 부분을 확인할 연결 정보가 없습니다.',
              'open_items': '항목별 문제 보기',
              'manual': '직접 확인하기',
              'open_doc': '문서 원문 읽기',
              'skip': '갈래 건너뛰기'},
 'trial': {'select_instruction': '시험할 문서와 부분을 고르세요.',
           'select_title': '한 문서의 한 부분을 시험합니다.',
           'eval_locked': '평가용 {count}건 · 개발 중 사용 금지',
           'section_label': '시험할 부분',
           'section': '{section}번 부분 · 노출기준',
           'prefilled': '갈래 1에서 본 문서와 부분을 채웠습니다.',
           'single_only': '이 안내에서는 부분을 하나만 고릅니다.',
           'next_model': '다음: AI 준비 확인하기',
           'model_instruction': '실제 시험에 쓸 모델을 준비하세요.',
           'model_title': '실제 시험에는 켜진 AI 모델이 필요합니다.',
           'saved_target': '{doc}의 {section}번 부분을 보관했습니다.',
           'already_ready': '이미 모델이 켜져 있을 때',
           'fresh_reply': '단계에 들어온 뒤 받은 모델 응답으로 확인합니다.',
           'continue_ready': '준비된 모델로 계속하기',
           'send_instruction': '대상과 설명을 읽고 실제 시험을 보내세요.',
           'waiting': '보낸 시험의 결과를 기다리고 있습니다.',
           'opened_result': '실제 시험의 결과를 열었습니다.',
           'completed': '갈래 2를 마쳤습니다. 실제 성공 기록이 남습니다.',
           'parse_failed': '작업은 끝났지만 값을 읽지 못했습니다.',
           'practice_stay': '갈래 2는 모델 준비 확인 단계에 머뭅니다.',
           'parse_todo': '할 일: ‘④ 해석한 값’에서 오류를 확인하고 같은 조건으로 다시 시험하세요.'},
 'skipped': {'title': '첫 사용 안내를 건너뛰었습니다.',
             'restart': '처음 사용 안내에서 언제든 다시 시작할 수 있습니다.',
             'keep_job': '이미 보낸 시험은 멈추지 않습니다.',
             'keep_outcomes': '실제 성공 기록과 연습 기록은 그대로입니다.',
             'open_recent': '최근 결과 보기'},
 'resume': {'title': '갈래 2의 모델 준비 확인을 이어갑니다.',
            'practice_only': 'AI 없이 입력 확인 연습은 {count}회 마쳤습니다. 실제 성공은 아직 없습니다.',
            'target_missing': '새로 열어 대상이 없을 때',
            'memory_target': '고른 문서와 부분은 이 화면 메모리에 보관합니다.',
            'reselect': '새로 열어 대상이 사라졌다면 다시 고릅니다.',
            'select_target': '시험 대상 다시 고르기',
            'action': '이어하기'},
 'pending': {'title': '지난번에 보낸 시험이 끝났습니다.',
             'checked': '보관한 작업 번호로 작업 기록을 확인했습니다.',
             'open_result': '결과 보기',
             'missing': '기록을 찾지 못한 경우',
             'not_found': '지난번 시험 기록을 찾지 못했습니다.',
             'todo': '할 일: 작업 기록을 확인하세요. 자동으로 다시 보내지 않습니다.',
             'unknown': '보냈는지 확인하지 못했습니다.'},
 'save_failed': {'title': '첫 사용 기록을 저장하지 못했습니다.',
                 'continue': '안내와 시험은 계속할 수 있습니다.',
                 'todo': '할 일: 앱을 켠 터미널이 열려 있는지 보세요. 다음 단계에서 다시 저장합니다.',
                 'action': '안내 계속하기',
                 'notify_once': '저장 실패 알림은 한 번만 보입니다.',
                 'memory': '이 탭의 메모리에서 진행을 이어갑니다.'},
 'partial_record': {'title': '안내 기록 일부를 읽지 못했습니다.',
                    'reset_progress': '진행 상태만 처음으로 돌렸습니다.',
                    'keep_outcomes': '실제 성공 기록과 연습 기록은 남아 있습니다.',
                    'todo': '할 일: 남아 있는 기록으로 안내를 계속하세요.'},
 'target_missing': {'title': '안내할 자리를 찾지 못했습니다.',
                    'stopped': '이 단계에서 멈췄습니다.',
                    'todo': '메뉴는 사용할 수 있습니다. 할 일: 안내로 돌아가 다시 시작하세요.',
                    'back': '안내로 돌아가기'},
 'detached': {'title': '보낸 시험을 안내에서 분리했습니다.',
              'keep_job': '시험 대상이 바뀌었습니다. 진행 중인 작업은 멈추지 않습니다.',
              'no_progress': '분리된 결과는 현재 안내 단계를 올리지 않습니다.',
              'real_success': '실제 시험이 성공한 뒤 결과를 열면 실제 사용 기록에는 남습니다.',
              'open_job': '보낸 작업 보기'},
 'track': '해 볼 일',
 'practice': '연습',
 'skip': '건너뛰기',
 'band': {'title': '처음이라면 두 가지 중 하나를 해 보세요.',
          'read': '하나는 서버 없이 점수와 가장 큰 문제를 읽습니다.',
          'trial': '다른 하나는 모델에 문서 한 항을 보내 시험합니다.',
          'open': '첫 사용 안내 열기',
          'closed': '닫아도 위쪽 ‘처음 사용’에서 다시 열 수 있습니다.',
          'resume': '첫 사용 안내 갈래 {track}가 {total}단계 중 {step}단계에서 멈춰 있습니다.',
          'running': '지난번에 보낸 시험이 아직 진행 중입니다.'},
 'steps': {'count': '{count}단계입니다.',
           'position': '갈래 {track} · {total}단계 중 {step}단계',
           'done': '확인한 단계',
           'target': '안내 대상',
           'todo': '할 일: {action}',
           'skip_read': '성공 기록 없이 원문을 계속 볼 수 있습니다.',
           'skip_trial': '작업과 성공 기록을 새로 만들지 않습니다. 이미 보낸 시험은 계속됩니다.'},
 'tracks': {'t1': {'steps': {'1': '최근 점수와 목표를 읽으세요.', '2': '가장 큰 문제의 원문을 여세요.', '3': '문제 값과 선택된 원문 줄을 맞춰 보세요.'}},
            't2': {'steps': {'1': '시험할 문서와 부분을 고르세요.', '2': '실제 시험에 쓸 모델을 준비하세요.', '3': '대상과 설명을 읽고 실제 시험을 보내세요.', '4': '실제 시험의 결과를 열었습니다.'}}}}
COPY_EXCEPTIONS.update({'journey.band.title': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.band.read': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.band.trial': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.band.open': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.band.closed': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.band.resume': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.band.running': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.steps.count': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.steps.position': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.steps.done': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.steps.target': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.steps.todo': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.steps.skip_read': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.steps.skip_trial': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.trial.parse_todo': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.pending.unknown': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.read.key_unusable': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.read.key_todo': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.read.same': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.read.other': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.read.no_section': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.choice.unknown': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.',
 'journey.partial_record.todo': '승인 STRUCTURE의 안내 띠·단계·복구 문구이며 COPY에 동적 일반형이 없어 보충했습니다.'})


# Step 8: 승인된 도움말과 용어. 주소 예시는 상위 보안 규칙에 따라 설정 이름으로 대신한다.
UI_TEXT["help"] = {'settings': {'runpod_url_pattern': '빌린 서버의 중계 주소는 RUNPOD_VLLM_BASE_URL 설정에서 준비합니다.',
              'runpod_url_fact': 'RUNPOD_VLLM_BASE_URL은 빌린 서버의 중계 주소입니다. SSH 연결 주소가 아닙니다.',
              'company_url_pattern': '회사 모델의 내 컴퓨터 쪽 주소는 RNGD_BASE_URL 설정에서 준비합니다.',
              'certificates': '인증서 설치 파일: /Applications/Python 3.11/Install Certificates.command',
              'runpod_url_name': 'RUNPOD_VLLM_BASE_URL',
              'runpod_url_meaning': '빌린 서버의 중계 주소(RunPod 프록시). SSH 연결 주소가 아닙니다.',
              'runpod_key_meaning': '빌린 서버의 모델 접속 키',
              'company_url_meaning': '회사 모델에 요청을 보내는 내 컴퓨터 쪽 주소',
              'company_key_name': 'RNGD_API_KEY',
              'company_key_meaning': '회사 모델의 접속 키',
              'management_key_name': 'RUNPOD_API_KEY',
              'management_key_meaning': '빌린 서버를 만들고 삭제할 때 쓰는 관리 키',
              'ssh_name': 'RNGD_SSH',
              'ssh_meaning': '회사 서버에 접속하는 보안 연결(SSH) 설정',
              'runpod_key_name': 'RUNPOD_VLLM_API_KEY',
              'company_url_name': 'RNGD_BASE_URL'},
 'title': '하려는 일에 맞는 설명을 펼치세요.',
 'replay_read': '결과 읽기 안내 다시 보기',
 'return_trial': '다시 시험으로 돌아가기',
 'flow': {'title': '앱과 처리 순서',
          'purpose': 'AI는 안전 문서의 내용을 정해진 칸으로 옮깁니다.',
          'pdf': 'PDF에서 쪽별 글자를 읽습니다.',
          'sections': '문서를 16개 부분으로 나눕니다.',
          'extract': 'AI가 필요한 값을 뽑습니다.',
          'save': '정해진 결과 형식(JSON)으로 저장합니다.',
          'score': '답안과 비교해 점수를 매깁니다.',
          'audience': '이 화면은 그 결과를 검토하는 사람을 위한 도구입니다.'},
 'score': {'title': '점수와 비교 읽기',
           'weight': '중요한 항목에는 더 큰 비중을 줍니다.',
           'target': '전체 목표 점수은 90점입니다.',
           'must': '필수 17개 항목의 목표 달성 수는 따로 확인합니다.',
           'draft': '정답도 틀릴 수 있습니다.',
           'cause': '2점 이상 하락한 항목의 원인 후보는 추정입니다.',
           'open_methods': '23개 기준의 측정 방법 보기'},
 'source': {'title': '원문으로 확인하기',
            'compare': 'AI가 채운 값과 같은 위치의 원문 줄을 비교합니다.',
            'example': '예: 2쪽 23번째 줄에는 5 mg/m³가 적혀 있습니다.',
            'no_fallback': '근거가 없으면 임의의 줄을 대신 선택하지 않습니다.',
            'open': '선택한 값과 원문 보기'},
 'setup': {'title': '처음 준비하기',
           'read_offline': '저장 결과를 읽는 데는 서버 설정이 필요 없습니다.',
           'file_intro': '실제 시험에 쓸 설정은 프로젝트의',
           'filename': '.env',
           'file_end': '파일에서 준비합니다.',
           'names_only': '아래는 설정 이름뿐입니다.',
           'name_column': '설정 이름',
           'meaning_column': '뜻',
           'template_intro': '양식 파일은',
           'template_name': '.env.example',
           'template_end': '입니다.',
           'no_secrets': '비밀값은 화면이나 기록에 넣지 않습니다.',
           'command_label': '앱 시작 명령:',
           'command': '(cd backend && .venv/bin/python scripts/b_app.py)'},
 'trial': {'title': '한 부분 시험하기',
           'meaning': '문서의 같은 부분을 다시 보내 수정 효과를 확인합니다.',
           'open_stages': '입력부터 결과까지 6단계 보기'},
 'cli': {'title': '터미널 명령과 옵션',
         'help_label': '명령 도움말:',
         'help_command': 'try_section.py --help',
         'option_column': '옵션',
         'section_flag': '--section',
         'section_meaning': '시험할 문서 부분',
         'all_flag': '--all',
         'all_meaning': '문서 전체 16개 부분',
         'dry_run_flag': '--dry-run',
         'dry_run_meaning': 'AI 호출 없이 입력 확인',
         'system_file_flag': '--system-file',
         'system_file_meaning': '기본 설명 대신 보낼 파일',
         'base_run_flag': '--base-run',
         'base_run_meaning': '전후 비교의 기준 결과',
         'show_prompt_flag': '--show-prompt',
         'show_prompt_meaning': '설명 전문을 화면에 표시',
         'json_flag': '--json',
         'json_meaning': '결과를 구조화된 형식으로 출력'},
 'prompt': {'title': 'AI에게 시킬 일 바꾸기',
            'code_default': '기본 설명은 코드의 기본값에서 가져옵니다.',
            'model_default': '모델별 설정에 있는 설명이 기본값을 덮을 수 있습니다.',
            'trial_override': '시험 화면에서 고친 설명을 그 시험에만 사용할 수 있습니다.',
            'persist': '영구 반영은 해당 모델의 설명 파일을 수정하고 버전을 올립니다.',
            'memory': '임시 전문은 화면 메모리에만 남깁니다.',
            'hash': '기록에는 확인값만 남겨 다음 반복과 비교합니다.'},
 'servers': {'title': 'AI 연결과 비용 관리',
             'cost': '빌린 서버는 켜진 시간에 따라 비용이 듭니다.',
             'company': '회사 서버는 연결 통로와 AI 준비를 따로 확인합니다.',
             'manual_record': '서버 기록은 운영용 수동 기록에도 옮겨 둡니다.',
             'open_rented': '빌린 서버 관리하기',
             'open_company': '회사 서버 관리하기'},
 'recovery': {'title': '막혔을 때 복구하기',
              'length': '답이 너무 길면 출력 길이 제한에 도달할 수 있습니다.',
              'whitespace': '공백을 계속 생성해도 출력 길이 제한에 도달할 수 있습니다.',
              'repetition': '같은 내용을 반복해도 출력 길이 제한에 도달할 수 있습니다.',
              'columns': '표의 열 수가 맞지 않으면 AI에게 시킬 일의 답변 형식을 검토합니다.',
              'slow': '처리가 300초를 넘으면 느린 항목의 요청 기록을 봅니다.',
              'connection': '연결 오류는 장비의 응답 상태부터 확인합니다.',
              'open_states': '상태별 복구 방법 보기'},
 'protection': {'title': '자료 보호와 용어',
                'eval_locked': '평가용 10건은 개발 과정에서 열거나 시험하지 않습니다.',
                'private_data': '문서 원문과 회사 자료는 밖으로 공유하지 않습니다.',
                'keys': '접속 키는 설정 파일에만 둡니다.',
                'delete_rented': '빌린 서버는 사용 뒤 삭제합니다.',
                'no_eval': '개발 중에는 평가용 문서를 사용하지 않습니다.',
                'tests': '자동 검사에서는 원문 자료를 덮어쓰는 전처리 시험을 제외합니다.',
                'command_label': '검사 명령:',
                'harness_intro': '자동 실행기(하네스)가 동작 중일 때는 보호된',
                'docs_path': 'docs/',
                'harness_end': '파일을 고치지 않습니다.',
                'command': '(cd backend && .venv/bin/python -m pytest -q --ignore=tests/test_preprocess.py)'},
 'terms': {'distinction': '문서 부분(항)과 점수 기준은 서로 다릅니다.',
           'section_count': '문서 부분은 16개입니다.',
           'criterion_count': '점수 기준은 23개입니다.',
           'load_failed': '용어를 불러오지 못하면 ‘설명을 읽지 못했습니다’와 다시 읽기를 제공합니다.',
           'open_score': '전체 점수 용어 보기',
           'title': '화면에서 쓰는 말 40개',
           'columns': '쉬운 설명과 원래 용어',
           'failure': '설명을 읽지 못한 상태',
           'open_failure': '용어를 읽지 못한 상태 보기'},
 'journey': {'title': '첫 사용 기록과 재시작',
             'storage': '안내 기록은 프로젝트 파일에 보관합니다.',
             'replay': '다시 보기는 진행만 처음으로 돌립니다.',
             'open': '처음 사용 안내 다시 보기'},
 'failed': {'title': '용어 설명을 읽지 못했습니다.',
            'scope': '설명만 확인할 수 없습니다.',
            'todo': '다른 기능은 사용할 수 있습니다. 할 일: 용어 설명만 다시 읽으세요.',
            'reload': '설명 다시 읽기'},
 'guide': {'flow': {'title': '앱은 어떤 일을 하나요?', 'summary': '문서에서 값을 뽑아 저장하고 정답과 비교하는 순서를 설명합니다.'},
           'score': {'title': '점수와 문제 건수는 어떻게 읽나요?', 'summary': '두 목표와 정답의 신뢰 범위를 구분합니다.'},
           'source': {'title': '문제 값을 원문에서 어떻게 확인하나요?', 'summary': '실제 근거 줄과 추정 줄을 구분해 읽습니다.'},
           'setup': {'title': '실제 시험 전에 무엇을 준비하나요?', 'summary': '저장 결과 읽기와 모델 접속 설정을 구분합니다.'},
           'retest': {'title': '한 부분을 어떻게 다시 시험하나요?', 'summary': 'AI 없이 확인하는 연습과 실제 시험을 구분합니다.'},
           'prompt': {'title': 'AI에게 시킬 일은 어떻게 고치나요?', 'summary': '원문에서 확인한 오류를 한 가지 규칙으로 바꿉니다.'},
           'servers': {'title': '어느 서버를 고르고 언제 끄나요?', 'summary': '추가 임대료와 준비 시간과 삭제 시점을 확인합니다.'},
           'recovery': {'title': '오류가 나면 어디서 다시 시작하나요?', 'summary': '화면의 사실과 할 일을 읽고 같은 대상에서 이어갑니다.'},
           'protection': {'title': '어떤 문서와 정보를 보호하나요?', 'summary': '평가용 문서 잠금과 접속 키 보관 원칙을 확인합니다.'}},
 'navigation': {'return': '이전 화면으로 돌아가기',
                'full': '이 장 전체 읽기',
                'methods_failed': '채점 기준을 읽지 못했습니다.',
                'methods_todo': '할 일: 채점 기준만 다시 읽으세요. 도움말과 용어는 계속 읽을 수 있습니다.',
                'methods_reload': '채점 기준 다시 읽기',
                'loading': '용어와 채점 기준을 읽고 있습니다.',
                'example': '예',
                'search': '용어 찾기',
                'empty': '찾는 용어가 없습니다. 다른 말로 찾아보세요.'},
 'facts': {'run_name': '실행 폴더 이름은 날짜와 모델 설정과 지시문 버전과 입력 자료와 회차를 이어 쓴 기록입니다.',
           'run_example': '예: s8은 AI에게 시킬 일의 8번째 판입니다. _r2는 같은 조건의 두 번째 시험입니다.',
           'run_conditions': '실행 조건을 펼치면 원래 폴더 이름과 각 조건을 확인할 수 있습니다. 없는 기록은 추정하지 않습니다.',
           'scores': '필수 17개는 각각 무게 3입니다. 중요 4개는 각각 무게 2입니다. 일반 2개는 각각 무게 1입니다.',
           'targets': '각 기준의 목표는 점수 계산 기준에서 확인합니다. 필수는 대부분 95%입니다. 유해성 분류와 급성독성은 90%입니다.',
           'two_targets': '전체 점수와 필수 기준의 목표 달성 수를 따로 읽습니다. 목표 달성은 제품의 안전 판정이 아닙니다.',
           'empty_rows': '값 없는 행은 자료없음·해당없음·비해당·미기재처럼 상태만 적힌 줄입니다. 표기 규칙은 정답 담당자가 정합니다.',
           'auxiliary': '보조 점수는 정답과 AI 결과 양쪽에서 값 없는 행을 뺀 뒤 계산합니다. 차이가 크면 그 행의 표기를 확인하세요.',
           'draft_gap': '정답지 주의에는 빈칸과 출처가 표시됩니다. 값 없는 노출기준 행의 기준 종류도 확인 대상입니다.',
           'old_draft': '이전 정답 초안의 검토 기록에서는 값 없는 독성 행 232개 중 209개의 숫자 칸이 비었습니다. 현재 정답지에도 같은 문제가 있다고 단정하지 '
                        '않습니다.',
           'ranking': '정답 초안 기준 점수는 모델과 지시문을 비교하는 참고값입니다. 원문에서 맞는 값을 확인하세요.',
           'cause_conditions': '조건: 모델과 지시문과 입력 자료와 동시 요청 수가 달라졌는지 봅니다.',
           'cause_calls': '요청: 두 번째 결과에서만 실패나 길이 제한이나 재추출이 생겼는지 봅니다.',
           'cause_counts': '문제 종류: 못 뽑음과 만듦과 틀림의 건수가 늘었는지 봅니다.',
           'cause_docs': '문서: 점수가 가장 많이 내려간 문서를 최대 세 건 봅니다.',
           'cause_rows': '표: 정답과의 행 수 차이가 5% 또는 1행 이상 더 커졌는지 봅니다.',
           'cause_variation': '흔들림: 조건이 같으면 반복 실행의 차이일 수 있습니다. 원인은 원문에서 확인합니다.',
           'source_select': '값을 누르면 근거 줄이 선택됩니다. 줄을 누르면 그 줄을 근거로 쓴 값이 선택됩니다.',
           'source_estimated': '못 뽑은 값의 위치는 글자를 맞춰 추정합니다. 추정 줄만 열어서는 결과 읽기 안내를 완료하지 않습니다.',
           'source_colors': '같음과 다름과 정답에만 있음은 글로 구분합니다. 지금 고른 값과 줄은 노란 바탕으로 표시합니다.',
           'journey': '첫 사용 안내는 결과 읽기와 한 부분 실제 시험의 두 갈래입니다. 다시 보기는 성공 기록과 연습 기록을 지우지 않습니다.',
           'journey_read': '가장 큰 문제의 값과 실제 근거 줄을 함께 열면 결과 읽기를 마칩니다. 근거가 없으면 임의의 줄로 대신하지 않습니다.',
           'journey_try': '실제 시험의 해석이 성공한 결과 요약을 열면 실제 성공을 기록합니다. 입력 확인 연습은 따로 기록합니다.',
           'storage': '안내 기록은 runs/manual/journey.json에 보관합니다. 저장이 실패해도 다른 기능은 쓸 수 있습니다.',
           'cards': '카드 접힘은 브라우저에 보관합니다. 저장소를 쓸 수 없어도 화면은 사용할 수 있습니다.',
           'setup_copy': '프로젝트 최상위의 .env.example을 복사한 파일 이름을 .env로 바꿉니다. .env는 Git에 올리지 않습니다.',
           'setup_open': '프로젝트 최상위에서 앱을 켭니다. 내 컴퓨터 127.0.0.1에서만 열립니다. 터미널에 표시된 주소를 브라우저에 입력하세요.',
           'setup_reload': '설정을 고친 뒤 AI 켜기와 비용에서 설정 다시 읽기를 누르세요.',
           'rngd_tunnel': '회사 서버는 보안 연결 통로(SSH 터널)를 사용합니다. RNGD_SSH에서 접속 옵션을 준비합니다.',
           'trial_scope': '다시 시험에서 개발용 문서와 문서 부분과 모델을 고릅니다. 여러 부분이나 문서 전체도 시험할 수 있습니다.',
           'trial_ready': '모델 준비 상태를 확인하세요. 연결된 모델이 없으면 AI 켜기와 비용에서 준비합니다.',
           'trial_practice': '입력 확인 연습은 AI를 부르지 않습니다. 보낼 입력과 지시문만 확인합니다.',
           'trial_send': '실제 시험 시작을 누른 뒤 결과 요약을 엽니다. 여섯 단계를 차례로 펼쳐 보세요.',
           'trial_many': '여러 문서 시험에서 개발용 문서와 반복 횟수를 고릅니다. 두 결과 비교에서는 여러 결과의 비교표도 만들 수 있습니다.',
           'jobs': '작업 기록에서 진행과 오류를 봅니다. 중단이 허용된 작업만 멈출 수 있습니다.',
           'cli_command': '(cd backend && .venv/bin/python scripts/try_section.py --model <태그> --doc <문서 번호> '
                          '--section 11 --dry-run)',
           'cli_repeat': '--section은 여러 번 줄 수 있습니다. --system-file은 한 부분 시험에서만 씁니다.',
           'prompt_spec': '기본 지시문은 TO21 v0.6 명세서의 칸 정의와 규칙에서 만듭니다.',
           'prompt_code': 'section_prompts.py가 공통 지시와 문서 부분별 설명을 더합니다.',
           'prompt_rows': '표의 답변 형식은 rows.py의 rows_guide가 만듭니다.',
           'prompt_work': '한 부분을 고른 뒤 현재 설명을 불러오세요. 원문에서 확인한 오류를 한 가지 규칙으로 고쳐 시험합니다.',
           'prompt_persist': '공통 규칙을 바꾸려면 section_prompts.py나 rows.py에 반영합니다. 모델별 설명 파일이 있으면 그 파일도 확인합니다.',
           'prompt_version': 'SECTION_PROMPT_VERSION을 올린 뒤 여러 개발 문서로 반복 시험합니다. 한 번의 점수만으로 개선을 확정하지 않습니다.',
           'prompt_private': '지시문에는 회사 명세서가 들어 있습니다. 전문을 공유 파일이나 실행 기록에 남기지 않습니다.',
           'prompt_temporary': '고친 글은 화면을 닫거나 새로고침하면 사라집니다. 요청을 전달할 때만 쓰는 임시 파일은 전달 뒤 지웁니다.',
           'server_confirmation': '서버를 바꾸기 전에 대상과 비용을 확인합니다. 확인 화면의 실행 단추를 눌러야 요청합니다.',
           'server_locked': '시험이나 실행이 진행 중이면 서버 변경을 막습니다. 회사 연결 통로 열기는 진행 중에도 가능합니다.',
           'server_owner': '앱이 만든 빌린 서버만 삭제할 수 있습니다. 앱을 다시 켜면 같은 서버를 이어 씁니다.',
           'server_cost': '앱이 만든 서버는 요청이 20분 없으면 앱이 지웁니다. 앱이 꺼져 있어도 서버 안 타이머가 4시간에 지웁니다.',
           'server_record': '서버 기록은 runs/manual/server_log.md에 남습니다. 운영 기록은 docs/plan/RunPod_사용기록.md에 따로 '
                            '옮깁니다.',
           'limit': '길이 제한은 답이 길거나 공백을 계속 쓰거나 같은 글을 반복할 때 생깁니다. 끝난 이유가 length인지 요청 기록에서 확인하세요.',
           'limit_rule': '한도에 걸린 답의 공백 비율이 50%를 넘으면 공백폭주입니다. 끝의 같은 글이 20자 이상이고 4번 이상 이어지면 반복입니다.',
           'limit_where': '최근 결과의 문서와 부분별 AI 요청 표에서 시도 횟수와 시간을 봅니다. 실패와 길이 제한 뒤 성공은 다른 상태입니다.',
           'columns': '시험 결과의 해석한 값에서 버린 줄 수를 봅니다. 모델의 원래 답과 정해진 열 수를 비교하세요.',
           'slow': '최근 결과의 문서별 시간에서 300초 목표선을 봅니다. 재요청으로 느려질 수 있습니다. 가장 오래 걸린 부분의 기록을 확인하세요.',
           'connection': '회사 연결 통로와 빌린 서버의 전원 상태를 각각 확인합니다. 오래 실행할 때는 컴퓨터가 잠들지 않게 설정하세요.',
           'protect_eval': '평가용 문서를 개발에 쓰면 평가 점수가 부풀 수 있습니다. 앱은 원문 조회와 시험을 거부합니다.',
           'protect_keys': '설정 파일 밖의 파일과 로그와 시험과 채팅에 접속 키를 적지 않습니다. 저장소와 실행 기록은 팀이 함께 봅니다.',
           'protect_docs': '자동 실행기 동작 중 docs/를 고치면 보호 검사로 그 단계가 실패합니다.',
           'protect_tests': 'tests/test_preprocess.py는 실제 data/pages/를 옛 방식 결과로 덮어씁니다. 검사할 때 항상 이 파일을 '
                            '제외하세요.'}}
UI_TEXT["glossary"] = {'silver': {'term': 'AI 정답 초안(실버)', 'meaning': 'AI가 먼저 만든 비교용 답입니다. 예: data/silver/claude에 있는 답입니다.'},
 'gold': {'term': '사람이 확인한 정답(골드)',
          'meaning': '사람이 검토해 확정한 답입니다. 예: data/gold/T21-S001.json입니다.'},
 'weighted': {'term': '중요도를 반영한 전체 점수(가중 종합)',
              'meaning': '각 기준에 중요도만큼 비중을 주어 계산한 점수입니다. 예: 최근 전체 점수 82.4점의 목표는 90점입니다.'},
 'must_count': {'term': '필수 기준의 목표 달성 수',
                'meaning': '필수 기준 중 각자의 목표 점수에 닿은 기준 수입니다. 예: 12/17은 필수 17개 중 12개가 목표에 닿았다는 뜻입니다.'},
 'must': {'term': '각각 목표를 채워야 하는 기준(필수)',
          'meaning': '전체 점수와 별개로 각 기준의 목표를 확인하는 등급입니다. 예: 필수 기준 하나의 점수 비중은 3입니다.'},
 'important': {'term': '그다음으로 중요한 기준(중요)',
               'meaning': '필수보다 작은 비중으로 전체 점수에 반영하는 등급입니다. 예: 중요 기준 하나의 점수 비중은 2입니다.'},
 'ordinary': {'term': '나머지 점수 기준(일반)', 'meaning': '전체 점수에 가장 작은 비중으로 반영하는 등급입니다. 예: 일반 기준 하나의 점수 비중은 1입니다.'},
 'section': {'term': '안전 문서를 나눈 주제(항)',
             'meaning': '화학제품 안전 설명서(MSDS)를 나눈 16개 주제 중 하나입니다. 예: 3번 부분은 성분을 다룹니다.'},
 'item': {'term': '점수를 매기는 기준(항목)', 'meaning': 'AI가 값을 제대로 옮겼는지 확인하는 검사 단위입니다. 예: 이 앱은 23개 기준으로 점수를 매깁니다.'},
 'prompt': {'term': 'AI에게 시킬 일(지시문)',
            'meaning': '어떤 값을 어떤 형식으로 뽑을지 AI에게 주는 설명입니다. 예: “숫자와 단위를 원문 그대로 옮기세요.”'},
 'prompt_version': {'term': 'AI에게 시킬 일을 고친 차례',
                    'meaning': 'AI에게 보내는 글의 변경 순서를 구분하는 번호입니다. 예: 8번째 설명은 s8로 기록합니다.'},
 'input': {'term': '원문 글자를 모은 폴더',
           'meaning': 'AI에게 보낼 원문의 쪽별 글자를 모아 둔 곳입니다. 예: 시안의 이전 개발 자료는 prev/version9입니다.'},
 'page_text': {'term': '문서 한 쪽의 글자', 'meaning': '문서 한 페이지에서 읽어 낸 글입니다. 예: 원문 화면에서 예시 문서 1의 2쪽 글자를 읽습니다.'},
 'line': {'term': '원문의 쪽과 줄 번호', 'meaning': '값이 원문 어디에 있는지 나타내는 위치입니다. 예: p2:L23은 2쪽 23번째 줄입니다.'},
 'base_run': {'term': '새 답을 끼워 넣을 이전 결과(기준 실행)',
              'meaning': '새로 시험한 부분의 답만 바꿔 점수를 계산할 이전 결과입니다. 예: 82.4점에서 한 부분만 바꿔 계산한 점수는 82.8점입니다.'},
 'practice': {'term': 'AI 없이 보낼 내용 확인(입력 확인 연습)',
              'meaning': 'AI를 부르지 않고 원문과 시킬 일만 확인하는 연습입니다. 예: 연습 결과에는 보낼 내용만 있고 AI의 답은 없습니다.'},
 'try': {'term': '같은 문서를 다시 처리하기(다시 시험)',
         'meaning': '고른 문서의 일부나 전체를 AI에게 다시 읽히는 작업입니다. 예: 예시 문서 1의 8번 부분만 다시 시험합니다.'},
 'batch': {'term': '여러 문서 시험(본 실행)', 'meaning': '고른 개발용 문서를 같은 조건으로 처리하는 작업입니다. 예: 개발용 10건을 2회 반복합니다.'},
 'comparison': {'term': '여러 결과를 모은 표(비교표)',
                'meaning': '선택한 결과의 점수와 시간을 나란히 보여 주는 표입니다. 예: 선택한 첫 결과가 첫 번째 열에 들어갑니다.'},
 'missing': {'term': '정답에 있는데 못 뽑음(빠뜨림)',
             'meaning': '정답에는 있고 AI 결과에는 없는 값입니다. 예: 성분 B의 2 mg/m³가 결과에서 빠졌습니다.'},
 'invented': {'term': '정답에 없는 값을 만듦(지어냄)',
              'meaning': 'AI 결과에는 있고 정답에는 없는 값입니다. 예: 자료가 없는 성분 H에 AI가 3 mg/m³를 적었습니다.'},
 'wrong': {'term': '정답과 다른 값을 뽑음(틀림)',
           'meaning': '같은 칸의 값이 정답과 다른 경우입니다. 예: 성분 A의 5 mg/m³를 AI가 8 mg/m³로 옮겼습니다.'},
 'empty_row': {'term': '자료 없음으로 적힌 행(값 없는 행)',
               'meaning': '실제 수치 대신 자료 없음 같은 상태만 적힌 표의 줄입니다. 예: 빈 행을 뺀 보조 점수는 83.0점입니다.'},
 'calls': {'term': '문서와 부분별 AI 요청 표(호출 격자)',
           'meaning': '각 부분을 처리한 AI 요청의 상태를 모은 표입니다. 예: 첫 번째 안전자료의 1~16번 부분이 표시됩니다.'},
 'reextract': {'term': 'AI에게 다시 뽑도록 요청(재추출)',
               'meaning': '첫 답에서 발견한 문제를 알려 한 번 더 요청하는 처리입니다. 예: 두 번째 답이 첫 답보다 나을 때만 두 번째 답을 씁니다.'},
 'output_limit': {'term': '답변 길이 제한(출력 한도)',
                  'meaning': 'AI가 한 번에 답할 수 있는 최대 길이입니다. 예: 길이 제한에 걸린 요청은 요청 기록에서 구분합니다.'},
 'whitespace': {'term': '빈칸만 계속 답함(공백폭주)',
                'meaning': 'AI가 답 대신 긴 빈칸을 내보내는 상태입니다. 예: 한도에 걸린 답의 공백 비율이 50%를 넘으면 이 상태로 분류합니다.'},
 'repetition': {'term': '같은 답을 계속 되풀이함(반복)',
                'meaning': 'AI가 같은 글을 반복하다 답변 길이 제한에 걸린 상태입니다. 예: 끝부분의 같은 글이 20자 이상이고 4번 이상 이어지면 반복으로 '
                           '분류합니다.'},
 'model_tag': {'term': 'AI 설정의 짧은 이름(모델 태그)',
               'meaning': '모델과 접속 설정을 구분하는 이름입니다. 예: 시안의 AI 모델 A는 demo-model-a입니다.'},
 'runpod': {'term': '시간당 요금을 내는 빌린 서버(RunPod)',
            'meaning': '모델을 켜 둔 시간에 따라 요금을 내는 서버입니다. 예: 시간당 $2.49로 2시간을 쓰면 추정 비용은 $4.98입니다.'},
 'rngd': {'term': '회사에서 쓰는 AI 서버(RNGD)',
          'meaning': '한 번에 모델 하나를 준비하는 회사 장비입니다. 예: 추가 임대료는 없고 모델 준비에는 보통 15~25분 걸립니다.'},
 'pod': {'term': '빌린 서버 한 대(Pod)',
         'meaning': 'RunPod에서 만들어 AI 모델을 실행하는 서버 한 대입니다. 예: 시안의 demo-pod-a는 앱이 만든 서버입니다.'},
 'repeat': {'term': '같은 조건을 반복한 차례(회차)', 'meaning': '동일한 조건으로 몇 번째 시험했는지 나타내는 번호입니다. 예: _r2는 두 번째 시험입니다.'},
 'extras': {'term': '표 밖에 남은 값(extras)',
            'meaning': '정해진 결과 칸에 넣지 못해 따로 보관한 값입니다. 예: 표 행 수 비교에는 남은 값 3개도 표시됩니다.'},
 'key_gap': {'term': '정답 초안에서 확인할 빈칸',
             'meaning': '정답 자체에서 빠졌거나 검토해야 하는 곳입니다. 예: 시안은 성분 B의 출처 칸 1개를 확인 대상으로 표시합니다.'},
 'concurrency': {'term': '한꺼번에 보내는 AI 요청 수(동시 호출)',
                 'meaning': '동시에 처리하도록 보낸 요청의 수입니다. 예: 비교 화면의 두 실행은 한 번에 2개씩 보냈습니다.'},
 'rows': {'term': '한 줄에 한 행씩 받는 답(행 형식)',
          'meaning': '표의 열 순서대로 AI가 한 줄씩 답하는 방식입니다. 예: 성분 A | 작업장 기준 | 5 mg/m³'},
 'variation': {'term': '같은 조건에서 생기는 결과 차이(흔들림)',
               'meaning': '같은 조건을 반복해도 점수가 달라지는 현상입니다. 예: 같은 조건의 반복 결과를 두 결과 비교에서 확인합니다.'},
 'exposure': {'term': '작업장 공기의 기준(노출기준)',
              'meaning': '공기 속 물질이 얼마나 있어도 되는지 정한 값이 허용 농도입니다. 예: 가짜 원문의 성분 A 허용 농도는 5 mg/m³입니다.'},
 'concentration_unit': {'term': '공기 속 물질의 양을 나타내는 단위(mg/m³)',
                        'meaning': '공기 1세제곱미터에 든 물질의 양을 밀리그램으로 나타냅니다. 예: 5 mg/m³는 공기 1세제곱미터에 물질 5밀리그램이 있다는 '
                                   '뜻입니다.'}}
COPY_EXCEPTIONS.update({'help.settings.runpod_url_pattern': '주소 예시를 표시하지 않는 상위 규칙에 따라 설정 이름만 안내합니다.',
 'help.settings.company_url_pattern': '주소 예시를 표시하지 않는 상위 규칙에 따라 설정 이름만 안내합니다.',
 'help.terms.title': '실제 용어는 40개라 승인 표의 38개 제목을 바로잡았습니다.',
 'help.navigation.return': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.navigation.full': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.navigation.methods_failed': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.navigation.methods_todo': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.navigation.methods_reload': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.navigation.loading': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.navigation.search': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.navigation.empty': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.run_name': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.run_example': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.run_conditions': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.scores': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.targets': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.two_targets': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.empty_rows': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.auxiliary': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.draft_gap': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.old_draft': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.ranking': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.cause_conditions': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.cause_calls': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.cause_counts': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.cause_docs': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.cause_rows': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.cause_variation': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.source_select': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.source_estimated': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.source_colors': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.journey': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.journey_read': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.journey_try': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.storage': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.cards': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.setup_copy': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.setup_open': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.setup_reload': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.rngd_tunnel': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.trial_scope': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.trial_ready': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.trial_practice': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.trial_send': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.trial_many': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.jobs': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.cli_command': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.cli_repeat': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.prompt_spec': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.prompt_code': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.prompt_rows': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.prompt_work': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.prompt_persist': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.prompt_version': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.prompt_private': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.prompt_temporary': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.server_confirmation': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.server_locked': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.server_owner': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.server_cost': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.server_record': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.limit': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.limit_rule': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.limit_where': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.columns': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.slow': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.connection': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.protect_eval': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.protect_keys': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.protect_docs': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.',
 'help.facts.protect_tests': '옛 도움말의 사실과 직접 이동 및 복구 조작을 보존합니다. BUILD step 8 글 출처에 근거를 기록합니다.'})
for _approved_help_key in ('source.empty.pages',
 'source.empty.lines',
 'source.labels.run',
 'source.labels.doc',
 'source.labels.section',
 'source.labels.page',
 'source.labels.selected',
 'source.kinds.wrong',
 'source.kinds.made',
 'source.kinds.missing',
 'source.kinds.same',
 'source.section_names.1',
 'source.section_names.2',
 'source.section_names.4',
 'source.section_names.5',
 'source.section_names.6',
 'source.section_names.7',
 'source.section_names.8',
 'source.section_names.10',
 'source.section_names.11',
 'source.section_names.12',
 'source.section_names.13',
 'source.section_names.14',
 'source.section_names.16',
 'source.table_names.components',
 'source.table_names.exposure_limits',
 'source.table_names.physchem',
 'source.table_names.toxicity',
 'source.table_names.transport',
 'source.table_names.regulations',
 'source.table_names.extras',
 'compare.conditions.labels.모델',
 'compare.conditions.labels.입력 판',
 'compare.criteria.same',
 'compare.values.kind',
 'compare.values.content',
 'compare.rows.table',
 'compare.unknown',
 'servers.models.connected',
 'servers.models.empty',
 'jobs.status.failed',
 'jobs.kind.try',
 'jobs.kind.compare',
 'jobs.record.progress',
 'jobs.record.kind',
 'jobs.form.model',
 'jobs.form.doc',
 'jobs.form.section',
 'jobs.form.all',
 'jobs.form.prompt',
 'jobs.form.run_name',
 'jobs.result.section'):
    COPY_EXCEPTIONS.pop(_approved_help_key, None)

UI_TEXT["help"]["facts"]["counts"] = "문제 건수는 그 기준에서 찾은 문제 값의 수입니다. 건수만으로 손실 점수를 계산하지 않습니다."
COPY_EXCEPTIONS["help.facts.counts"] = "실행 수치가 없는 일반 도움말이므로 counts 자리표시 대신 건수의 뜻을 설명합니다."

UI_TEXT["common"]["screen_shown"] = "{screen} 화면을 표시했습니다."
COPY_EXCEPTIONS["common.screen_shown"] = "화면 이동 완료를 알립니다. 자료 조회나 모델 실행 성공을 뜻하지 않습니다."
UI_TEXT["context"]["answer_mismatch"] = "이 결과의 정답지는 현재 선택과 다릅니다. 결과: {result_key}. 현재 선택: {selected_key}."
COPY_EXCEPTIONS["context.answer_mismatch"] = "S5 결정 2: ⑤ 수락 11/1 승인"

# S5 step 1: 승인 글에 없는 상태별 안내. ⑤ 수락에서 함께 검토한다.
UI_TEXT["score"]["problem"].update({
    "open_made": "만든 값 {count}건의 원문 보기",
    "open_missing": "못 뽑은 값 {count}건의 원문 보기",
    "made_hint": "정답에 없는 값을 먼저 봅니다. AI가 적은 근거가 있으면 원문과 함께 확인합니다.",
    "missing_hint": "못 뽑은 값부터 봅니다. 원문 줄은 추정 위치이며, 찾지 못한 값은 해당 부분을 직접 읽습니다.",
    "wrong_hint": "틀린 값부터 봅니다. 연결된 원문 줄이 없으면 해당 부분을 직접 읽습니다.",
    "evidence_unrecorded": "문제 수는 기록 없음입니다. 문제 값을 열어 원문과 맞춰 보세요.",
})
UI_TEXT["score"]["calculation"].update({
    "scorer_counts": "점수 계산에 쓴 행 단위 문제 수",
    "scorer_counts_hint": "앞 화면은 칸 단위로 셉니다. 아래는 점수 계산 프로그램이 행 단위로 센 수입니다.",
})
UI_TEXT["source"]["labels"]["choose_scope"] = "문서와 부분을 먼저 고르세요."
UI_TEXT["source"]["filter"]["all_values"] = "전체 보기"
UI_TEXT["source"]["field_names"] = {"q": UI_TEXT["source"]["fields"]["value"], "limit_type": "기준 종류"}
for _copy_key in (
    "score.problem.open_made", "score.problem.open_missing", "score.problem.made_hint",
    "score.problem.missing_hint", "score.problem.wrong_hint", "score.problem.evidence_unrecorded",
    "score.calculation.scorer_counts", "score.calculation.scorer_counts_hint",
    "source.labels.choose_scope", "source.field_names.limit_type", "source.filter.all_values",
):
    COPY_EXCEPTIONS[_copy_key] = "S5 결정 2: ⑤ 수락 11/1 승인"

# S5 step 2: 승인 장면의 행동과 여러 결과 순서 조작에 필요한 글.
UI_TEXT["compare"]["values"]["open_changed"] = "바뀐 값의 원문 보기"
UI_TEXT["compare"]["empty"] = {"next": "비교할 결과를 준비하거나 문서 묶음을 바꾸세요."}
UI_TEXT["compare"]["builder"].update({"move_up": "앞으로 옮기기", "move_down": "뒤로 옮기기"})
for _copy_key in ("compare.values.open_changed", "compare.empty.next", "compare.builder.move_up", "compare.builder.move_down"):
    COPY_EXCEPTIONS[_copy_key] = "S5 결정 2: ⑤ 수락 11/1 승인"

# S5 step 3: 계약에서 확인한 요금과 문서별 정답 범위를 표시한다.
COPY_EXCEPTIONS.pop("servers.confirm.create.action", None)
UI_TEXT["servers"]["confirm"]["create"]["cost_unknown"] = "시간당 요금을 확인하지 못했습니다. 할 일: 취소한 뒤 새 서버 요금을 다시 확인하세요."
UI_TEXT["context"]["picker"].update({
    "outside_count": "목록 밖 문서 {count}건",
    "coverage_label": "정답이 있는 문서",
    "coverage": "{found}/{total}건에 정답이 있습니다.",
})
for _copy_key in ("servers.confirm.create.cost_unknown", "context.picker.outside_count", "context.picker.coverage_label", "context.picker.coverage"):
    COPY_EXCEPTIONS[_copy_key] = "S5 결정 2: ⑤ 수락 11/1 승인"

# S5 문구 마감: 승인된 이름 복원과 ⑤ 수락에 올릴 짧은 설명.
UI_TEXT['score']['basis']['label'] = '{key} 기준 · 점수를 계산한 문서 {count}건'
COPY_EXCEPTIONS['score.basis.label'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['score']['loading']['scoring'] = '실행 {count}개의 점수를 계산 중입니다. 처음에는 수십 초 걸릴 수 있습니다.'
COPY_EXCEPTIONS['score.loading.scoring'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['source']['labels']['criterion'] = '점수를 매기는 기준: {item}'
COPY_EXCEPTIONS['source.labels.criterion'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['compare']['items']['name'] = '점수를 매기는 기준'
COPY_EXCEPTIONS['compare.items.name'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['navigation']['methods_failed'] = '점수를 매기는 기준을 읽지 못했습니다.'
COPY_EXCEPTIONS['help.navigation.methods_failed'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['navigation']['methods_todo'] = '할 일: 점수를 매기는 기준만 다시 읽으세요. 도움말과 용어는 계속 읽을 수 있습니다.'
COPY_EXCEPTIONS['help.navigation.methods_todo'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['navigation']['methods_reload'] = '점수를 매기는 기준 다시 읽기'
COPY_EXCEPTIONS['help.navigation.methods_reload'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['navigation']['loading'] = '용어와 점수를 매기는 기준을 읽고 있습니다.'
COPY_EXCEPTIONS['help.navigation.loading'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['compare']['selection']['reasons']['outside'] = '새 문서 시험에는 점수를 매길 정답이 없습니다.'
COPY_EXCEPTIONS['compare.selection.reasons.outside'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['compare']['selection']['reasons']['unknown'] = '전체 실행 비교 대상이 아닙니다. 실행 종류와 점수를 계산한 범위를 확인하세요.'
COPY_EXCEPTIONS['compare.selection.reasons.unknown'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['score']['conditions']['nonempty_meaning'] = '정답과 결과 양쪽에서 자료없음·해당없음·비해당·미기재 행을 뺍니다. 같은 점수 계산 방법으로 다시 잰 보조 점수입니다.'
COPY_EXCEPTIONS['score.conditions.nonempty_meaning'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['score']['summary']['target_line'] = '목표 점수 {line}점'
COPY_EXCEPTIONS.pop('score.summary.target_line', None)
UI_TEXT['compare']['target_line'] = '목표 점수 {line}점'
COPY_EXCEPTIONS.pop('compare.target_line', None)
UI_TEXT['score']['summary']['must_progress'] = '각각 목표를 채워야 하는 필수 기준 {total}개 중 {met}개가 목표에 닿았습니다.'
COPY_EXCEPTIONS['score.summary.must_progress'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['score']['criteria']['weight'] = '{level} · 점수에 반영하는 비중 {weight}'
COPY_EXCEPTIONS['score.criteria.weight'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['score']['calculation']['weight'] = '{level} 기준 {count}개 · 점수에 반영하는 비중 {weight}'
COPY_EXCEPTIONS['score.calculation.weight'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['score']['calculation']['loss_formula'] = '잃은 점수 = 비중 × (1 − 기준 점수) ÷ 점수가 있는 항목의 비중 합 × 100'
COPY_EXCEPTIONS['score.calculation.loss_formula'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['score']['calculation']['weight_basis'] = '점수가 있는 항목의 비중 합: {weight}'
COPY_EXCEPTIONS['score.calculation.weight_basis'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['scores'] = '점수에 반영하는 비중은 필수 기준 17개가 각각 3입니다. 중요 기준 4개는 각각 2입니다. 일반 기준 2개는 각각 1입니다.'
COPY_EXCEPTIONS['help.facts.scores'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['compare']['prompt']['open'] = '{section}번 부분에서 AI에게 시킨 일의 차이 보기'
COPY_EXCEPTIONS['compare.prompt.open'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['compare']['prompt']['loading'] = '{section}번 부분에서 AI에게 시킨 일을 다시 만드는 중입니다. 몇 초 걸릴 수 있습니다.'
COPY_EXCEPTIONS['compare.prompt.loading'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['compare']['prompt']['failed'] = 'AI에게 시킨 일의 차이를 읽지 못했습니다.'
COPY_EXCEPTIONS['compare.prompt.failed'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['compare']['prompt']['retry'] = 'AI에게 시킨 일의 차이 다시 불러오기'
COPY_EXCEPTIONS['compare.prompt.retry'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['compare']['prompt']['same'] = '두 결과에서 AI에게 시킨 일이 같습니다.'
COPY_EXCEPTIONS['compare.prompt.same'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['compare']['prompt']['note'] = '부분을 펼칠 때만 당시 AI에게 시킨 일을 다시 읽습니다.'
COPY_EXCEPTIONS['compare.prompt.note'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['run_name'] = '실행 폴더 이름은 날짜와 AI 설정과 AI에게 시킬 일의 버전과 입력 자료와 반복한 차례를 이어 쓴 기록입니다.'
COPY_EXCEPTIONS['help.facts.run_name'] = "S5 결정 2: ⑤ 수락 11/1 승인"
# 11/2 사용자 요청: 원문 자료와 정답 장
UI_TEXT['help']['data'] = {
    "source_meaning": "원문 자료(문서 묶음)는 PDF를 쪽마다 글자와 그림으로 바꿔 둔 파일입니다. AI는 이 글자를 읽고, 근거도 이 글자의 줄 번호로 댑니다.",
    "source_example": "예: p5:L22는 5쪽 22번째 줄입니다.",
    "source_change": "바꾸기: 화면 위 ‘필요할 때 문서 바꾸기’에서 다른 묶음을 고릅니다. 그 묶음으로 돌린 저장 결과만 보입니다.",
    "source_add_title": "원문 자료를 새로 더하는 순서입니다.",
    "source_add1": "data/pages/<묶음 이름>/<문서 번호>/ 폴더를 만듭니다.",
    "source_add2": "쪽마다 p001.txt(글자)와 p001.png(그림)를 넣습니다. 글자 줄 앞에 L001 같은 줄 번호가 있어야 새 시험에 쓸 수 있습니다.",
    "source_add3": "data/manifest.csv에 없는 문서 번호라면 meta.json도 넣습니다. 안의 doc_id가 폴더 이름과 같아야 열립니다.",
    "source_add4": "화면을 새로고침하면 목록에 나타납니다. 앱을 다시 켤 필요는 없습니다.",
    "source_caution": "평가용 문서는 점수가 부풀려지지 않도록 개발 중에는 열지 않습니다. 목록에 잠김으로 보입니다. data/pages는 git에 올리지 않습니다.",
    "answer_meaning": "정답은 AI 값과 견주는 기준입니다. 점수는 AI가 뽑은 값이 정답과 얼마나 같은지로 계산합니다. 정답을 바꾸면 같은 결과의 점수도 달라집니다.",
    "answer_gold": "사람이 확인한 정답(골드)은 사람이 검토해 확정한 답입니다. data/gold에 있습니다.",
    "answer_silver": "AI 정답 초안(실버)은 AI가 먼저 만든 비교용 답입니다. data/silver 아래 폴더에 있고, 틀릴 수 있습니다.",
    "answer_change": "바꾸기: 화면 위 ‘필요할 때 정답 바꾸기’에서 고릅니다. 저장된 결과를 AI 없이 다시 채점합니다.",
    "answer_add_title": "정답을 새로 더하는 순서입니다.",
    "answer_add1": "data/silver/<이름>/ 또는 data/gold/<이름>/ 폴더를 만듭니다.",
    "answer_add2": "문서마다 <문서 번호>.json을 넣습니다. 예: T21-S001.json. 정해진 결과 형식(TO21 JSON)이어야 합니다.",
    "answer_add3": "화면을 새로고침하면 목록에 나타납니다. 앱을 다시 켤 필요는 없습니다.",
    "answer_caution": "골드는 A 담당이 검수해 올립니다. 고칠 곳을 찾으면 파일을 직접 바꾸지 말고 A 담당에게 알립니다. 평가용 문서의 정답은 열지 않고 개수만 셉니다."
}
UI_TEXT['help']['guide']['data'] = {'title': '원문 자료와 정답은 무엇이고 어떻게 바꾸나요?', 'summary': 'AI가 읽는 글과 점수 기준의 뜻, 바꾸고 새로 더하는 순서를 설명합니다.'}
UI_TEXT['help']['facts']['ranking'] = '점수는 모델과 AI에게 시킬 일을 비교하는 참고값입니다. 원문에서 맞는 값을 확인하세요.'
COPY_EXCEPTIONS['help.facts.ranking'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['cause_conditions'] = '조건: 모델과 AI에게 시킬 일과 입력 자료와 한꺼번에 보내는 요청 수가 달라졌는지 봅니다.'
COPY_EXCEPTIONS['help.facts.cause_conditions'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['prompt_private'] = 'AI에게 시킬 일에는 회사 명세서가 들어 있습니다. 전문을 공유 파일이나 실행 기록에 남기지 않습니다.'
COPY_EXCEPTIONS['help.facts.prompt_private'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['compare']['prompt']['rows'] = '한 줄에 한 행씩 받는 답(행 형식)'
COPY_EXCEPTIONS.pop('compare.prompt.rows', None)
UI_TEXT['compare']['prompt']['json'] = '정해진 결과 형식(JSON)'
COPY_EXCEPTIONS['compare.prompt.json'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['jobs']['result']['format_json'] = '정해진 결과 형식(JSON)'
COPY_EXCEPTIONS['jobs.result.format_json'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['servers']['models']['off'] = 'AI 꺼짐'
COPY_EXCEPTIONS.pop('servers.models.off', None)
UI_TEXT['servers']['models']['tag'] = 'AI 설정의 짧은 이름(모델 태그)'
COPY_EXCEPTIONS.pop('servers.models.tag', None)
UI_TEXT['jobs']['result']['weighted'] = '중요도를 반영한 전체 점수 {score}점'
COPY_EXCEPTIONS['jobs.result.weighted'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['jobs']['result']['changed'] = '점수를 매기는 기준별 변화'
COPY_EXCEPTIONS['jobs.result.changed'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['jobs']['result']['unchanged'] = '점수를 매기는 기준 중 값이 바뀐 것은 없습니다.'
COPY_EXCEPTIONS['jobs.result.unchanged'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['journey']['band']['trial'] = '다른 하나는 모델에 문서 한 부분을 보내 시험합니다.'
COPY_EXCEPTIONS['journey.band.trial'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['journey']['read']['no_section'] = '이 문제는 한 부분에 묶이지 않습니다. 할 일: 기준별 문제를 보거나 갈래를 건너뛰세요.'
COPY_EXCEPTIONS['journey.read.no_section'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['journey']['band']['open'] = '처음 사용 안내 열기'
COPY_EXCEPTIONS.pop('journey.band.open', None)
UI_TEXT['journey']['band']['resume'] = '처음 사용 안내 갈래 {track}가 {total}단계 중 {step}단계에서 멈춰 있습니다.'
COPY_EXCEPTIONS['journey.band.resume'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['cause_calls'] = '요청: 두 번째 결과에서만 실패나 길이 제한이 생겼는지 봅니다. AI에게 다시 뽑도록 요청했는지도 봅니다.'
COPY_EXCEPTIONS['help.facts.cause_calls'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['cause_variation'] = '같은 조건에서 생기는 결과 차이: 조건이 같아도 반복 실행마다 결과가 달라질 수 있습니다. 원인은 원문에서 확인합니다.'
COPY_EXCEPTIONS['help.facts.cause_variation'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['journey_try'] = '실제 시험의 답을 읽는 데 성공한 결과 요약을 열면 실제 성공을 기록합니다. AI 없이 보낼 내용 확인은 따로 기록합니다.'
COPY_EXCEPTIONS['help.facts.journey_try'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['trial_practice'] = 'AI 없이 보낼 내용 확인은 AI를 부르지 않는 연습입니다. 보낼 원문과 AI에게 시킬 일만 확인합니다.'
COPY_EXCEPTIONS['help.facts.trial_practice'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['servers']['session']['active'] = '한 부분 시험과 여러 문서 시험은 서버 {pod_id}을 사용합니다.'
COPY_EXCEPTIONS['servers.session.active'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['source']['table_names']['hazard.h_statements'] = '위험 문구 번호(H 코드)'
COPY_EXCEPTIONS['source.table_names.hazard.h_statements'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['source']['table_names']['hazard.p_statements'] = '예방 문구 번호(P 코드)'
COPY_EXCEPTIONS['source.table_names.hazard.p_statements'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['source']['table_names']['composition'] = '들어 있는 성분 목록과 양'
COPY_EXCEPTIONS['source.table_names.composition'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['source']['table_names']['cmr'] = '암·유전·생식 관련 독성'
COPY_EXCEPTIONS.pop('source.table_names.cmr', None)
UI_TEXT['source']['table_names']['ecotox'] = '환경에 미치는 영향'
COPY_EXCEPTIONS.pop('source.table_names.ecotox', None)
UI_TEXT['source']['section_names']['9'] = '물리·화학 성질'
COPY_EXCEPTIONS.pop('source.section_names.9', None)
UI_TEXT['help']['facts']['slow'] = '최근 결과의 문서별 시간에서 300초 목표 시간을 봅니다. 다시 요청하면 느려질 수 있습니다. 가장 오래 걸린 부분의 기록을 확인하세요.'
COPY_EXCEPTIONS['help.facts.slow'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['raw_error'] = '오류 기록 펼치기'
COPY_EXCEPTIONS['common.raw_error'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['score']['load_failed']['todo'] = '할 일: 기록을 다시 읽으세요. 계속 실패하면 앱을 실행한 명령 입력 창(터미널)의 오류를 확인하세요.'
COPY_EXCEPTIONS['score.load_failed.todo'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['compare']['load_failed']['todo'] = '할 일: 비교 결과를 다시 불러오세요. 계속 실패하면 앱을 실행한 명령 입력 창(터미널)의 오류를 확인하세요.'
COPY_EXCEPTIONS['compare.load_failed.todo'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['score']['calls']['mode'] = '답을 받는 방식: {mode}'
COPY_EXCEPTIONS['score.calls.mode'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['jobs']['result']['raw_meta'] = '답을 받는 방식: {mode}. 끝난 이유: {reason}. 걸린 시간: {seconds}초.'
COPY_EXCEPTIONS['jobs.result.raw_meta'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['score']['calls']['limit_reason'] = '답변 길이 제한에 걸린 원인: {reason}'
COPY_EXCEPTIONS['score.calls.limit_reason'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['servers']['rented']['state'] = '서버 상태: {state}'
COPY_EXCEPTIONS['servers.rented.state'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['servers']['connection']['tunnel_closed'] = '연결 통로가 닫혀 있습니다. 서버 연결에 쓰는 통로 번호(포트)는 {port}입니다.'
COPY_EXCEPTIONS['servers.connection.tunnel_closed'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['servers']['connection']['tunnel_external'] = '연결 통로가 열려 있습니다. 서버 연결에 쓰는 통로 번호(포트)는 {port}입니다. 이 앱이 연 연결이 아닙니다.'
COPY_EXCEPTIONS['servers.connection.tunnel_external'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['servers']['connection']['tunnel_unknown'] = '서버 연결에 쓰는 통로 번호(포트)를 확인하지 못했습니다.'
COPY_EXCEPTIONS['servers.connection.tunnel_unknown'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['servers']['connection']['process'] = '실행 중인 프로그램의 식별 번호: {pid}'
COPY_EXCEPTIONS['servers.connection.process'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['servers']['connection']['none'] = '현재 확인된 모델 실행 프로그램이 없습니다.'
COPY_EXCEPTIONS['servers.connection.none'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['servers']['result']['started'] = '모델 실행 프로그램을 시작했습니다. 응답까지 보통 15~25분 걸립니다.'
COPY_EXCEPTIONS['servers.result.started'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['servers']['result']['stopped'] = '멈춘 모델 프로그램 번호: {pids}'
COPY_EXCEPTIONS['servers.result.stopped'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['servers']['result']['process_remaining'] = '아직 실행 중인 모델 프로그램 번호: {pids}'
COPY_EXCEPTIONS['servers.result.process_remaining'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['jobs']['record']['pid'] = '실행 중인 프로그램의 식별 번호: {pid}'
COPY_EXCEPTIONS['jobs.record.pid'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['jobs']['record']['unknown_tip'] = '이전 앱에서 시작한 작업이라 끝난 상태를 모릅니다. 작업이 남긴 실행 기록(로그)이나 결과 폴더를 보세요.'
COPY_EXCEPTIONS['jobs.record.unknown_tip'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['jobs']['record']['close_log'] = '작업 실행 기록 닫기'
COPY_EXCEPTIONS['jobs.record.close_log'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['jobs']['record']['log_empty'] = '아직 작업이 남긴 실행 기록(로그)이 없습니다.'
COPY_EXCEPTIONS['jobs.record.log_empty'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['jobs']['record']['exit_missing'] = '작업이 끝난 이유를 나타내는 번호(종료 코드)가 기록되지 않았습니다.'
COPY_EXCEPTIONS['jobs.record.exit_missing'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['jobs']['result']['input_meta'] = '원문 글자를 모은 폴더: {pages}. 부분을 나눈 방법: {method}. 안전자료 {count}개 중 첫 번째 자료를 사용합니다.'
COPY_EXCEPTIONS['jobs.result.input_meta'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['jobs']['result']['input_rows'] = '{section}번 부분 · {format} · {count}줄(앞에 덧붙인 공통 줄 {preamble}줄) · {first} ~ {last} · 쪽 {pages} · 이미지 {images} · 부분을 나눈 방법: {method}'
COPY_EXCEPTIONS['jobs.result.input_rows'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['cards'] = '상세 영역을 펼치거나 접은 상태는 브라우저에 보관합니다. 보관할 수 없어도 화면은 사용할 수 있습니다.'
COPY_EXCEPTIONS['help.facts.cards'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['setup_copy'] = '프로젝트 최상위의 설정 예제 파일(.env.example)을 복사해 실제 설정 파일(.env)을 만듭니다. 실제 설정 파일은 코드 변경 기록 저장소(Git)에 올리지 않습니다.'
COPY_EXCEPTIONS['help.facts.setup_copy'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['cli_command'] = '(cd backend && .venv/bin/python scripts/try_section.py --model <AI설정이름> --doc <문서번호> --section 11 --dry-run)'
COPY_EXCEPTIONS['help.facts.cli_command'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['prompt_spec'] = 'AI에게 시킬 일의 기본 설명은 결과 형식을 정한 문서(TO21 v0.6 명세서)의 칸 정의와 규칙에서 만듭니다.'
COPY_EXCEPTIONS['help.facts.prompt_spec'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['prompt_version'] = 'AI에게 시킬 일의 버전 번호(SECTION_PROMPT_VERSION)를 올린 뒤 여러 개발 문서로 반복 시험합니다. 한 번의 점수만으로 개선을 확정하지 않습니다.'
COPY_EXCEPTIONS['help.facts.prompt_version'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['limit'] = '답이 길거나 빈칸 또는 같은 글을 계속 쓰면 길이 한도에 걸립니다. 요청 기록에서 끝난 이유가 길이 한도를 뜻하는 값(length)인지 확인하세요.'
COPY_EXCEPTIONS['help.facts.limit'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['setup_open'] = '프로젝트 최상위에서 앱을 켭니다. 내 컴퓨터 127.0.0.1에서만 열립니다. 앱을 실행한 명령 입력 창(터미널)에 표시된 주소를 브라우저에 입력하세요.'
COPY_EXCEPTIONS['help.facts.setup_open'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['protect_keys'] = '설정 파일 밖의 파일과 실행 기록(로그)에 접속 키를 적지 않습니다. 시험과 채팅에도 적지 않습니다. 저장소와 실행 기록은 팀이 함께 봅니다.'
COPY_EXCEPTIONS['help.facts.protect_keys'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['source']['labels']['raw_value'] = '원래 값과 위치 보기'
COPY_EXCEPTIONS['source.labels.raw_value'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['code_record'] = '원래 기록 값 보기'
COPY_EXCEPTIONS['common.code_record'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common'].setdefault('codes', {})
UI_TEXT['common']['codes']['unknown'] = '설명되지 않은 기록 값입니다. 원래 기록 값을 확인하세요.'
COPY_EXCEPTIONS['common.codes.unknown'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes'].setdefault('mode', {})
UI_TEXT['common']['codes']['mode']['json_schema'] = '정해진 칸과 값 형식으로 받기'
COPY_EXCEPTIONS['common.codes.mode.json_schema'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['mode']['json_schema_compact'] = '정해진 칸과 값 형식으로 빈칸 없이 받기'
COPY_EXCEPTIONS['common.codes.mode.json_schema_compact'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['mode']['json_object'] = '이름과 값을 짝지은 결과로 받기'
COPY_EXCEPTIONS['common.codes.mode.json_object'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['mode']['none'] = '응답 형식을 강제하지 않고 받기'
COPY_EXCEPTIONS['common.codes.mode.none'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['mode']['rows'] = '한 줄에 한 행씩 받기'
COPY_EXCEPTIONS['common.codes.mode.rows'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['mode']['nuextract_template'] = '추출 전용 틀에 맞춰 받기'
COPY_EXCEPTIONS['common.codes.mode.nuextract_template'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes'].setdefault('finish', {})
UI_TEXT['common']['codes']['finish']['stop'] = '답변을 끝내고 멈춤'
COPY_EXCEPTIONS['common.codes.finish.stop'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['finish']['length'] = '답변 길이 한도에 도달함'
COPY_EXCEPTIONS['common.codes.finish.length'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['finish']['content_filter'] = '서버의 내용 제한으로 중단됨'
COPY_EXCEPTIONS['common.codes.finish.content_filter'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['finish']['tool_calls'] = '도구 호출 요청으로 끝남'
COPY_EXCEPTIONS['common.codes.finish.tool_calls'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes'].setdefault('limit', {})
UI_TEXT['common']['codes']['limit']['whitespace'] = '빈칸만 계속 답함'
COPY_EXCEPTIONS['common.codes.limit.whitespace'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['limit']['repetition'] = '같은 답을 계속 되풀이함'
COPY_EXCEPTIONS['common.codes.limit.repetition'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['limit']['long'] = '답이 길어 한도에 도달함'
COPY_EXCEPTIONS['common.codes.limit.long'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes'].setdefault('pod', {})
UI_TEXT['common']['codes']['pod']['RUNNING'] = '서버 실행 중'
COPY_EXCEPTIONS['common.codes.pod.RUNNING'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['pod']['EXITED'] = '서버 실행 끝남'
COPY_EXCEPTIONS['common.codes.pod.EXITED'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['pod']['STOPPED'] = '서버 멈춤'
COPY_EXCEPTIONS['common.codes.pod.STOPPED'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['pod']['CREATED'] = '서버 생성됨'
COPY_EXCEPTIONS['common.codes.pod.CREATED'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['pod']['PENDING'] = '서버 실행 대기 중'
# 이 앱이 쓰는 Pod의 상태는 _pod_view가 글로 보낸다. 라벨 표에 없으면 "설명되지 않은 기록 값"으로 나온다 (11/2 수정)
UI_TEXT['common'].setdefault('code_aliases', {}).setdefault('pod', {}).update({'준비됨': 'READY', '준비 중': 'LOADING'})
UI_TEXT['common']['codes']['pod'].update({'READY': '준비됨', 'LOADING': '준비 중'})
for _key in ('common.code_aliases.pod.준비됨', 'common.code_aliases.pod.준비 중', 'common.codes.pod.READY', 'common.codes.pod.LOADING'):
    COPY_EXCEPTIONS[_key] = "11/2 서버 상태 표시 수정: 앱이 보내는 상태 이름"
COPY_EXCEPTIONS['common.codes.pod.PENDING'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes'].setdefault('split', {})
UI_TEXT['common']['codes']['split']['file'] = '저장된 부분 구간을 사용함'
COPY_EXCEPTIONS['common.codes.split.file'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['split']['provisional'] = '문서 제목으로 임시 구간을 나눔'
COPY_EXCEPTIONS['common.codes.split.provisional'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['split']['fallback'] = '부분 구간을 찾지 못해 문서 전체를 사용함'
COPY_EXCEPTIONS['common.codes.split.fallback'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['split']['title'] = '제목을 기준으로 구간을 나눔'
COPY_EXCEPTIONS['common.codes.split.title'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['split']['synonym'] = '같은 뜻의 제목을 기준으로 구간을 나눔'
COPY_EXCEPTIONS['common.codes.split.synonym'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['codes']['split']['failed'] = '부분 구간 나누기에 실패함'
COPY_EXCEPTIONS['common.codes.split.failed'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['help']['facts']['cli_model'] = '아래 명령의 <AI설정이름>에는 AI 설정의 짧은 이름(모델 태그)을 넣으세요.'
COPY_EXCEPTIONS['help.facts.cli_model'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['servers']['connection']['tunnel_owned'] = '이 앱이 연 연결 통로입니다. 서버 연결에 쓰는 통로 번호(포트)는 {port}입니다.'
COPY_EXCEPTIONS['servers.connection.tunnel_owned'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['jobs']['legacy']['exit_code'] = '작업이 끝난 이유를 나타내는 번호(종료 코드): {count}'
COPY_EXCEPTIONS['jobs.legacy.exit_code'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common'].setdefault('code_aliases', {})
UI_TEXT['common']['code_aliases'].setdefault('limit', {})
UI_TEXT['common']['code_aliases']['limit']['공백폭주'] = 'whitespace'
COPY_EXCEPTIONS['common.code_aliases.limit.공백폭주'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['code_aliases']['limit']['반복'] = 'repetition'
COPY_EXCEPTIONS['common.code_aliases.limit.반복'] = "S5 결정 2: ⑤ 수락 11/1 승인"
UI_TEXT['common']['code_aliases']['limit']['긴출력'] = 'long'
COPY_EXCEPTIONS['common.code_aliases.limit.긴출력'] = "S5 결정 2: ⑤ 수락 11/1 승인"
COPY_EXCEPTIONS['journey.record.expect.screen'] = "처음 사용 안내 Wispr 구조 승인 10/31: progress.guide 검사 문장"
COPY_EXCEPTIONS['journey.record.expect.choices'] = "처음 사용 안내 Wispr 구조 승인 10/31: progress.guide 검사 문장"
COPY_EXCEPTIONS['journey.record.expect.practices'] = "처음 사용 안내 Wispr 구조 승인 10/31: progress.guide 검사 문장"

# 윗줄의 빌린 서버 요금과 자동 삭제 (자료 바꾸기 시안 6, 11/2).
UI_TEXT["context"]["model"].update({
    "off_no_cost": "요금이 나가지 않습니다.",
    "rented_hourly": "시간당 약 ${cost}",
    "rented_auto_close": "요청이 {idle}분 없으면 자동으로 닫힙니다.",
    "rented_auto_left": "{minutes}분 남았습니다.",
    "rented_close_where": "지금 닫으려면 AI 켜기와 비용 화면으로 가세요.",
    "auto_closed_idle": "요청 없이 {limit}분이 지나 서버를 닫았습니다.",
    "auto_closed_no_reply": "모델이 {limit}분 동안 응답하지 않아 서버를 닫았습니다.",
    "auto_closed_cost": "켠 시간 {minutes}분, 추정 ${cost}.",
})

UI_TEXT["help"]["setup"]["new_data"] = "새 문서 폴더나 새 정답을 받았으면 화면 위쪽의 새 자료 받기를 누르세요. 문서 폴더는 검사한 뒤 앱으로 복사하고, 정답은 GitHub에서 받는 명령을 알려 줍니다."
UI_TEXT["help"]["servers"]["states"] = "화면 위쪽에서 상태를 봅니다. AI 꺼짐은 정상입니다. 빌린 서버를 만들면 켜는 중이 3~6분 보이고, 연결된 모델이 보이면 시험을 보낼 수 있습니다."
UI_TEXT["help"]["servers"]["waiting"] = "10분이 지나도 켜는 중이면 AI 켜기와 비용의 서버 기록을 확인하세요. 모델이 40분 동안 응답하지 않으면 앱이 서버를 지웁니다."

# 자료 바꾸기 화면(S11). design/COPY.md의 swap 표가 정본이다.
UI_TEXT["nav"]["swap"] = "새 자료 받기"
UI_TEXT["swap"] = {
    "context": {"score_docs": "점수를 매길 수 있는 문서 {count}건", "no_score": "점수 없음 · 양식만 확인",
                "gold_note": "최근 올린 날 {date} · 정답 {count}건 사용",
                "gold_changed": "새 정답이 들어왔습니다. 문서 {count}건이 바뀌어 점수를 다시 계산합니다.",
                "gold_changed_open": "무엇이 바뀌었나요"},
    "steps": {"a11y": "폴더 바꾸기 단계", "pick": "1 폴더 고르기", "check": "2 검사", "apply": "3 적용"},
    "back": "처음으로",
    "start": {"title": "어떤 자료를 새로 받았나요?",
              "lead": "받은 자료에 따라 하는 일이 다릅니다. 검사와 복사에는 AI를 쓰지 않아 요금이 들지 않습니다.",
              "docs_title": "새 문서 폴더",
              "docs_note": "PDF를 글자로 바꾸는 담당이 보내 준 폴더입니다. 문서마다 쪽별 글자가 들어 있고, AI가 이 글을 읽습니다. 예: Downloads/version17_신규40",
              "docs_action": "폴더 고르기",
              "gold_title": "새 정답 파일",
              "gold_note": "정답 담당이 GitHub에 올린 파일입니다. AI 결과와 견줘 점수를 매기는 기준입니다.",
              "gold_action": "새 정답 받기",
              "have_title": "새로 받은 자료가 없을 때",
              "have_note": "앱에 이미 있는 폴더나 정답으로 바꾸기만 합니다. 파일은 복사하지 않습니다.",
              "have_action": "앱에 있는 것으로 바꾸기"},
    "pick": {"title": "어느 문서 폴더를 쓸까요?",
             "lead": "Downloads에서 문서 폴더처럼 보이는 것을 찾았습니다. 앱에 없는 폴더는 검사한 뒤 앱으로 복사합니다. 검사만으로는 파일이 옮겨지지 않습니다.",
             "in_app": "앱에 있음", "not_in_app": "앱에 없음",
             "meta": "문서 {count}건 · {time}에 받음",
             "check": "검사하기",
             "empty": "Downloads에서 문서 폴더를 찾지 못했습니다. 아래에 경로를 직접 적어 주세요.",
             "unreadable": "Downloads 폴더를 읽지 못했습니다. 아래에 경로를 직접 적어 주세요.",
             "other_label": "다른 곳에 있는 폴더의 전체 경로",
             "other_placeholder": "/Users/내이름/Downloads/version18",
             "other_hint": "압축 파일은 먼저 풀어 주세요."},
    "check": {"checking": "폴더를 검사하고 있습니다. 파일은 옮기지 않습니다.",
              "title": {"score": "이 폴더로 시험하고 점수도 볼 수 있습니다.",
                        "format_only": "이 폴더는 쓸 수 있지만 점수는 나오지 않습니다.",
                        "unusable": "이 폴더로는 시험할 수 없습니다."},
              "no_overlap_title": "이 폴더의 문서와 겹치는 정답이 없습니다.",
              "no_overlap_body": "정답이 있는 문서와 문서 번호가 다릅니다. 이 폴더는 처음 보는 문서에서 AI 결과가 양식에 맞는지 볼 때 고릅니다.",
              "alternative": "점수를 보려면 정답이 있는 문서 {count}건이 든 {set} 폴더를 고르세요.",
              "unusable_body": "시험할 수 있는 문서가 없습니다. 줄 번호가 없거나 열지 않는 문서뿐입니다. 폴더를 보낸 담당에게 줄 번호가 있는 판을 요청하세요.",
              "can_title": "이 폴더로 할 수 있는 일",
              "yes": "가능", "no": "안 됨",
              "batch_yes": "{count}건을 한꺼번에 시험하기. AI 결과가 정해진 양식에 맞는지 봅니다.",
              "score_yes": "점수 매기기. 정답이 있는 문서 {count}건에 점수가 나옵니다.",
              "score_no": "점수 매기기. 비교할 정답이 없습니다.",
              "try_yes": "문서 하나의 한 부분만 다시 시험하기. 고를 수 있는 문서 {count}건.",
              "try_no": "문서 하나의 한 부분만 다시 시험하기. 지금은 개발용 문서 목록에 있는 문서만 됩니다.",
              "facts_title": "검사 결과",
              "docs_label": "문서", "docs_value": "{count}건",
              "lines_label": "줄 번호",
              "lines_all": "열 수 있는 {count}건 모두 있음. AI가 근거로 적는 번호라 있어야 시험할 수 있습니다. 예: L001",
              "lines_some": "열 수 있는 문서 중 {count}건에 없음. 이 문서들은 시험에서 빠집니다. AI가 근거로 적는 번호입니다. 예: L001",
              "locked_label": "열지 않는 문서",
              "locked_none": "없음",
              "locked_eval": "최종 평가 문서 {count}건. 점수가 부풀지 않도록 복사만 하고 열지 않습니다.",
              "locked_same": "{doc}는 최종 평가 문서 {eval_doc}와 원본이 같습니다.",
              "locked_unknown": "용도를 확인할 수 없는 문서 {count}건. 문서 폴더의 meta.json에 문서 번호가 있어야 열립니다.",
              "target_label": "앱에 넣을 곳",
              "target_new": "이 앱을 켠 작업 폴더에만 들어갑니다. 받은 폴더는 그대로 둡니다.",
              "target_same": "이미 앱에 있습니다. 복사하지 않습니다.",
              "target_conflict_title": "앱에 같은 이름의 다른 폴더가 있습니다.",
              "target_conflict": "덮어쓰지 않습니다. 받은 폴더의 이름을 바꾼 뒤 다시 검사하세요. 예: version18_2",
              "past_label": "지난 결과",
              "past_value": "지우지 않습니다. 이전 문서 묶음으로 돌아가면 다시 보입니다.",
              "apply_note_new": "누르면 이 폴더를 앱으로 복사하고 화면 위쪽의 시험할 문서 묶음을 이 폴더로 바꿉니다. 다음 화면의 되돌리기 단추로 이전 묶음으로 돌아갈 수 있습니다.",
              "apply_note_same": "누르면 복사 없이 화면 위쪽의 시험할 문서 묶음만 이 폴더로 바꿉니다. 다음 화면의 되돌리기 단추로 이전 묶음으로 돌아갈 수 있습니다.",
              "apply": "이 폴더로 바꾸기", "applying": "폴더를 복사하고 있습니다.", "switching": "문서 묶음을 바꾸고 있습니다.", "other": "다른 폴더 고르기"},
    "done": {"title": "이제 이 폴더로 시험합니다.",
             "changed": "화면 위쪽의 시험할 문서 묶음이 바뀌었습니다.",
             "results_none": "이 폴더로 만든 결과가 아직 없어 최근 결과 화면은 비어 있습니다.",
             "results_found": "이 폴더로 만든 결과 {count}개를 최근 결과에서 볼 수 있습니다.",
             "off_title": "다음 할 일: AI 켜기",
             "off_note": "시험하려면 AI가 켜져 있어야 합니다. 이 단추는 서버 고르는 화면만 엽니다. 요금은 그 화면에서 서버를 만든 때부터 나갑니다.",
             "off_action": "서버 고르는 화면 열기",
             "on_title": "다음 할 일: 여러 문서 시험하기",
             "on_note": "AI가 연결되어 있습니다. 이 단추는 시험할 문서를 고르는 화면만 엽니다. 시험은 그 화면에서 시작합니다.",
             "on_action": "시험 화면 열기",
             "undo_title": "되돌리기",
             "undo_note": "이전 문서 묶음({set})으로 돌아갑니다. 복사한 파일은 지우지 않습니다.",
             "undo": "되돌리기", "undone": "이전 문서 묶음으로 돌아갔습니다."},
    "gold": {"title": "새 정답은 GitHub에서 받습니다.",
             "lead": "정답 담당이 검수해 올립니다. 앱에서 정답 파일을 고치지 않습니다. 고칠 곳을 찾으면 담당에게 알려 주세요.",
             "now_title": "내 컴퓨터에 받아 둔 정답",
             "name_label": "이름", "name_value": "사람이 확인한 정답",
             "commit_label": "최근에 올린 것", "commit_none": "기록을 읽지 못했습니다.",
             "docs_label": "점수에 쓰는 정답", "docs_value": "개발용 문서 {count}건",
             "eval_label": "최종 평가용 정답", "eval_value": "{count}건. 점수가 부풀지 않도록 파일을 열지 않고 개수만 셉니다.",
             "selected_label": "지금 비교 중인 정답",
             "other_selected": "지금 점수는 이 정답이 아니라 다른 정답과 비교합니다.",
             "use_gold": "이 정답으로 바꾸기",
             "checking": "GitHub를 확인하고 있습니다.",
             "behind_title": "GitHub에 더 새 정답이 있습니다. 개발용 문서 {dev}건, 최종 평가 문서 {eval_docs}건이 다릅니다.",
             "behind_body": "터미널에서 아래 명령으로 받은 뒤 다시 확인하기를 누르세요. 앱을 다시 켤 필요는 없습니다.",
             "branch_note": "이 앱은 {branch} 가지에서 켜져 있어 main의 정답을 합치는 명령을 보여 줍니다.",
             "latest": "GitHub의 정답과 같습니다. 받을 것이 없습니다.",
             "offline": "GitHub에 연결하지 못했습니다. 받아 둔 정답은 그대로 쓸 수 있습니다.",
             "changed_title": "지난번 뒤로 새 정답이 들어왔습니다. 개발용 문서 {dev}건, 최종 평가 문서 {eval_docs}건이 바뀌었습니다.",
             "changed_docs": "바뀐 개발용 문서: {docs}",
             "after": "새 정답을 받으면 저장된 결과의 점수를 AI 없이 다시 계산합니다. 저장된 AI 결과는 바뀌지 않습니다.",
             "recheck": "다시 확인하기", "open_scores": "최근 결과의 점수 보기"},
    "problems": {
        "swap_no_path": {"message": "폴더를 찾지 못했습니다: {path}", "fix": "폴더의 전체 경로를 적어 주세요. 예: /Users/내이름/Downloads/version18"},
        "swap_doc_folder": {"message": "{name}은 문서 하나의 폴더입니다.", "fix": "그 위 폴더를 고르세요."},
        "swap_bad_name": {"message": "폴더 이름을 쓸 수 없습니다: {name}", "fix": "글자, 숫자, 밑줄만 남도록 이름을 바꾼 뒤 다시 검사하세요. 예: version18"},
        "swap_no_docs": {"message": "{name} 바로 안에 문서 폴더가 없습니다.", "fix": "압축을 풀었는지 확인하세요. 한 단계 안쪽 폴더일 수도 있습니다. 문서 폴더에는 p001.txt 같은 파일이 있습니다."},
        "swap_unusable": {"message": "{name}에는 시험할 수 있는 문서가 없습니다.", "fix": "폴더를 보낸 담당에게 줄 번호가 있는 판을 요청하세요."},
        "swap_conflict": {"message": "앱에 같은 이름의 다른 폴더가 있습니다: {target}", "fix": "받은 폴더의 이름을 바꾼 뒤 다시 검사하세요. 예: version18_2"},
        "swap_copy_failed": {"message": "폴더를 복사하지 못했습니다: {detail}", "fix": "디스크 공간과 폴더 권한을 확인한 뒤 다시 누르세요. 복사하다 만 파일은 남지 않습니다."},
    },
}

POLISH_TEXT = UI_TEXT


START_TEXT: dict = UI_TEXT["journey"]


FIELD_HELP: dict[str, str] = dict(UI_TEXT["jobs"]["fields"])

# 공개 키는 옛 API와 호환한다. 새 화면의 제목은 jobs.detail을 쓴다.
TRY_STAGE_HELP: dict[str, str] = dict(zip(
    ("① 보낸 입력", "② 안내문", "③ 모델 원문 답", "④ 읽은 결과", "⑤ 펼친 TO21 칸", "⑥ 점수 전 → 후"),
    (UI_TEXT["jobs"]["stages"][key] for key in ("input", "prompt", "raw_answer", "parsed", "to21", "score")),
))
JOB_UI_TEXT = dict(UI_TEXT["jobs"]["actions"])


def order_models(models: list[dict]) -> list[dict]:
    """같은 연결 상태의 순서는 유지하고, 원래 모델 정보에 선택지 글만 더한다."""
    rank = {True: 0, None: 1, False: 2}
    labels = {state: UI_TEXT["context"]["model"][f"state_{key}"]
              for state, key in ((True, "ready"), (None, "unknown"), (False, "off"))}
    return [{**m, "option_label": f"{m['label']} — {labels[m.get('connected')]}"}
            for m in sorted(models, key=lambda m: rank[m.get("connected")])]


def try_hint(models: list[dict], advanced: bool) -> dict:
    """연결을 확인한 모델이 없으면 서버 없는 시험만 안내한다."""
    count = sum(m.get("connected") is True for m in models)
    note = UI_TEXT["jobs"]["try_hint"]["ready" if count else "off"].format(count=count)
    return {"dry_run_forced": not count, "note": note}


# term·뜻·예는 승인 COPY에서 옮긴 같은 UI_TEXT를 쓴다. 예는 가짜 자료 또는 표시 설명이다.
_GLOSSARY_ALIASES = {'silver': ['실버', 'silver', '정답 초안', '정답 초안(실버)'],
 'gold': ['골드', 'gold', '정답(골드)'],
 'weighted': ['가중 종합', 'weighted', '가중 종합 점수'],
 'must_count': ['필수 통과', 'must_count', 'must_passed'],
 'must': ['필수', 'must', '필수 등급'],
 'important': ['중요', 'important', '중요 등급'],
 'ordinary': ['일반', 'ordinary', '일반 등급'],
 'section': ['항', 'section', '법정 항'],
 'item': ['항목', 'item', '채점 항목'],
 'prompt': ['안내문', 'prompt', '프롬프트'],
 'prompt_version': ['안내문 버전', 'prompt_version'],
 'input': ['입력 판', 'input', '입력판', '쪽 폴더', '쪽 글자 폴더'],
 'page_text': ['쪽 글자', 'page_text', '쪽 텍스트'],
 'line': ['줄 번호', 'line', '근거 줄 번호'],
 'base_run': ['기준 실행', 'base_run'],
 'practice': ['dry-run', 'practice', '서버 없이 확인'],
 'try': ['시험', 'try', '수동 시험'],
 'batch': ['본 실행', 'batch', '전체 실행'],
 'comparison': ['비교표', 'comparison', 'compare.md'],
 'missing': ['빠뜨림', 'missing', '누락'],
 'invented': ['지어냄', 'invented', '과추출'],
 'wrong': ['틀림', 'wrong', '값 불일치'],
 'empty_row': ['값 없는 행', 'empty_row', '무값 행'],
 'calls': ['호출 격자', 'calls'],
 'reextract': ['재추출', 'reextract', '다시 추출'],
 'output_limit': ['출력 한도', 'output_limit', '한도 걸림', '출력 길이 한도'],
 'whitespace': ['공백폭주', 'whitespace', '공백 폭주'],
 'repetition': ['반복', 'repetition', '반복 출력'],
 'model_tag': ['모델 태그', 'model_tag'],
 'runpod': ['RunPod', 'runpod'],
 'rngd': ['RNGD', 'rngd', '사내 장비'],
 'pod': ['Pod', 'pod', '팟'],
 'repeat': ['회차', 'repeat'],
 'extras': ['extras', '남는 값', 'extras(남는 값)'],
 'key_gap': ['실버 빈 곳', 'key_gap'],
 'concurrency': ['동시 호출', 'concurrency', '동시 요청', '동시 수'],
 'rows': ['행 형식', 'rows'],
 'variation': ['흔들림', 'variation'],
 'exposure': ['exposure', '노출기준', '허용 농도'],
 'concentration_unit': ['concentration_unit', 'mg/m³']}
GLOSSARY: dict[str, dict] = {}
for _glossary_key, _glossary_copy in UI_TEXT["glossary"].items():
    _short, _separator, _example = _glossary_copy["meaning"].partition(" 예: ")
    GLOSSARY[_glossary_copy["term"]] = {
        "short": _short, "example": "예: " + _example,
        "also": list(_GLOSSARY_ALIASES[_glossary_key]),
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
        ("diff", UI_TEXT["source"]["legend"]["different"], "#53645e"),
        ("silver_only", UI_TEXT["source"]["legend"]["missing"], "#53645e"),
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


_FIELD_KINDS = {"빠뜨림": "missing", "틀림": "wrong", "지어냄": "made"}


def _field_count(row: dict, counter) -> dict:
    """한 항목의 칸 단위 문제 수. 원문 대조 화면처럼 항목 이름과 항으로 거른다. 항을 모르면 모든 항의 칸을 센다."""
    return {kind: sum(n for (item, section, k), n in counter.items()
                      if item == row["name"] and k == key and (row["section"] is None or section == row["section"]))
            for kind, key in _FIELD_KINDS.items()}


def _doc_losses(row: dict, per_doc: dict | None, weight_total: float,
                field_counts: dict | None = None) -> list[dict]:
    """항목 손실을 문서별로 나눈다. 항목 점수가 문서 평균이라 문서 손실의 합이 항목 손실과 같다."""
    scores = [(d, p["items"][row["name"]]) for d, p in (per_doc or {}).items()
              if _number((p.get("items") or {}).get(row["name"]))]
    docs = [{"doc_id": d, "score": s * 100, "loss": row["weight"] * (1 - s) / (len(scores) * weight_total) * 100}
            for d, s in scores]
    if field_counts:
        for d in docs:
            d["counts"] = _field_count(row, field_counts[d["doc_id"]]) if d["doc_id"] in field_counts else None
    return sorted(docs, key=lambda d: -round(d["loss"], 9))


def score_losses(info: dict, criteria: dict, per_doc: dict | None = None, field_counts: dict | None = None) -> dict:
    """항목마다 가중 종합을 깎은 점수. 손실 = 무게×(1−점수)/무게 합×100이고 목표를 넘은 항목도 센다.
    모든 손실의 합은 100 − 가중 종합이다 (사용자 결정 10/31). 점수 없는 항목은 가중 종합에도 없으므로 뺀다.
    field_counts(문서 → b_app_doc.field_counts)를 주면 문제 건수는 원문 대조 화면과 같은 칸 단위로 세고,
    점수 프로그램의 행 단위 수는 scorer_counts에 둔다 (사용자 결정 10/31)."""
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
        if field_counts:
            row["scorer_counts"], row["counts_basis"] = counts, "field"
            counts = _field_count(row, sum(field_counts.values(), Counter()))
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
        top = {**losses[0], "docs": _doc_losses(losses[0], per_doc, total, field_counts)}
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
                 per_doc: dict | None = None, field_counts: dict | None = None) -> dict:
    """채점 값은 그대로 두고 100점 단위의 요약과 확인 순서를 만든다. 목표는 두 개(score_targets)로 보인다.
    top_drops는 목표 아래 항목의 목표 차 순서이고, 총점 손실 순서는 score_losses의 세 키다."""
    targets = score_targets(info, criteria)
    losses = score_losses(info, criteria, per_doc, field_counts)
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
                      "sentence": copy["drop"].format(item=item["name"], score=f"{score:.1f}", goal=f"{goal:g}",
                                                       cause=cause, count=item.get(cause) or 0)})
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
                copy["grid_count"].format(state=UI_TEXT["common"]["legacy"]["cell_labels"][state], count=counts[k])
                for k, state in (("성공", "c_ok"), ("재추출", "c_re"), ("한도 걸림", "c_limit"), ("실패", "c_fail")))
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


MODEL_LABELS: dict[str, str] = dict(UI_TEXT["context"]["models"])

_CONDITIONS = {**UI_TEXT["common"]["conditions"], "dev": UI_TEXT["common"]["conditions"]["dev10"]}


RUN_KIND_LABELS: dict[str, str] = dict(UI_TEXT["jobs"]["kinds"])


def run_kind_label(kind: str | None) -> str:
    """b_app_runs.run_kind 값의 사람 말. 모르는 값은 그대로, 없으면 빈 글."""
    return RUN_KIND_LABELS.get(kind, kind or "")


def model_label(tag: str | None) -> str:
    """알려진 모델은 표시 이름으로, 모르는 모델은 태그 그대로 돌려준다."""
    return MODEL_LABELS.get(tag, tag or "")


# 문서 묶음의 사용 가능 여부는 바꾸지 않고 설명만 승인 글로 제공한다.
SET_TEXT: dict[str, str] = dict(UI_TEXT["context"]["set_reason"])


def set_label(set_id: str) -> str:
    """묶음 id의 표시 이름. data/pages 바로 아래만 따로 부른다."""
    return UI_TEXT["context"]["set"]["label_new"] if set_id == "." else set_id


# 정답지(b_app_sets.list_keys)를 고를 수 없는 이유와 정답지를 고를 때의 오류. 키는 b_app_sets와 b_app이 쓴다.
KEY_TEXT: dict[str, str] = dict(UI_TEXT["context"]["key_reason"])


def key_label(key_id: str) -> str:
    """정답지 id의 표시 이름. 예: gold/a3 → "A 정답(골드) a3". 모르는 모양은 id 그대로."""
    if key_id == "silver/claude":
        return UI_TEXT["context"]["key"]["claude"]
    if key_id == "gold":
        return UI_TEXT["context"]["key"]["gold_main"]
    kind, _, name = key_id.partition("/")
    if name and "/" not in name:
        if kind == "silver":
            return UI_TEXT["context"]["key"]["silver"].format(name=name)
        if kind == "gold":
            return UI_TEXT["context"]["key"]["gold"].format(name=name)
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
JOB_ERROR_TEXT: dict[str, dict[str, str]] = {key: dict(value) for key, value in UI_TEXT["errors"]["job"].items()}
JOB_ERROR_TEXT["no_line"]["message"] = UI_TEXT["errors"]["job"]["other"]["message"]
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
    "unknown_key": {"error": "없는 정답지입니다: {id}. 정답지 목록에서 고르세요.", "message": "없는 정답지입니다: {id}.",
                    "fix": "정답지 목록에서 다시 고르세요."},
    "unusable_key": {"error": "고를 수 없는 정답지입니다: {reason}", "message": "고를 수 없는 정답지입니다: {reason}",
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

for _problem_kind, _problem_copy in UI_TEXT["errors"]["request"].items():
    PROBLEM_TEXT[_problem_kind].update(_problem_copy)


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

for _journey_group, _journey_values in UI_TEXT["journey"]["record"].items():
    if _journey_group not in JOURNEY_TEXT:
        continue
    if _journey_group == "errors":
        for _journey_kind, _journey_copy in _journey_values.items():
            JOURNEY_TEXT["errors"][_journey_kind].update(_journey_copy)
    else:
        JOURNEY_TEXT[_journey_group] = dict(_journey_values)


def swap_problem(kind: str, **facts) -> dict:
    """자료 바꾸기의 오류 본문 {"error", "message", "fix"}."""
    copy = UI_TEXT["swap"]["problems"][kind]
    message = copy["message"].format(**facts)
    return {"error": message, "message": message, "fix": copy["fix"]}


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
            return UI_TEXT["common"]["run"]["date"].format(month=day.month, day=day.day)
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
        return UI_TEXT["common"]["run"]["document"].format(doc=f"T21-{doc[1].upper()}{doc[2]}")
    match = re.fullmatch(r"(eval|probe|diag|r)(\d+)", token)
    if match:
        prefix, number = match.groups()
        words = UI_TEXT["common"]["run"]
        return {"eval": words["eval"], "probe": words["probe"].format(round=number),
                "diag": words["diagnostic"].format(run_id=number), "r": words["repeat"].format(round=number)}[prefix]
    return token


def run_label(info: dict) -> dict:
    """summarize_run 결과(일부 키만 있어도 됨)를 제목·원래 이름·구성 글로 바꾼다."""
    name = info.get("name") or ""
    base = name.removeprefix("manual/")
    date = _date(base, info.get("started_at"))
    inferred = next((tag for tag in sorted(MODEL_LABELS, key=lambda t: (-len(t), t))
                     if re.search(rf"(?:^|_){re.escape(tag)}(?:_|$)", base)), "")
    tag = info.get("model_tag") or inferred
    model = model_label("claude") if "_silver_" in name else model_label(tag)

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
        parts.append(UI_TEXT["common"]["run"]["prompt"].format(version=prompt))
    if version:
        parts.append(UI_TEXT["common"]["run"]["input"].format(version=version))
    parts.extend(_condition(t) for t in tokens
                 if t not in ("sections", "silver", prompt) and not _prompt(t) and not _input_version(t))
    title = " · ".join(p for p in parts if p)
    if info.get("kind") == "manual":
        title = UI_TEXT["common"]["run"]["manual"].format(title=title)
    return {"title": title, "subtitle": name, "parts": title.split(" · ")}


# 처음 사용 안내: 승인 시안의 글과 고정 예시를 분리한다.
UI_TEXT["guide"] = {'navigation': '안내 이동',
 'back': '뒤로',
 'skip': '안내 건너뛰기',
 'resume': '안내를 이어서 할 수 있어요',
 'resume_action': '안내 이어하기',
 'chapter_label': '전체 안내의 다섯 장',
 'chapters': {'1': '시작', '2': '준비', '3': '직접 해 보기', '4': '자료와 기본값', '5': '완료'},
 'progress': '{chapter} {n}/{m} · 5장 중 {k}장',
 'progress_label': '{chapter}, {m}단계 중 {n}단계',
 'close': {'title': '안내를 닫을까요?',
           'resume': '다음에 멈춘 곳부터 이어서 할 수 있어요.',
           'keep': '이미 남긴 실제 성공 기록은 지우지 않아요.',
           'running': '진행 중인 시험이 있다면 계속 처리돼요.',
           'action': '안내 닫기',
           'cancel': '안내 계속하기'},
 'screens': {'G01': {'title': 'AI가 화학 안전문서에서 뽑은 값을 정답과 견주고 고치는 도구예요', 'next': '시작하기'},
             'G03': {'title': '점수에서 원문 줄까지 세 번 누르면 돼요',
                     'next': '다음',
                     'lead': '1 최근 결과에서 [문제의 원문 보기] → 2 원문 줄 확인 → 3 [이 부분 다시 시험]',
                     'terms': '알아 둘 말',
                     'draft': '정답: AI 값과 견주는 기준이에요. 사람이 확인한 정답과 AI 정답 초안이 있어요.',
                     'part': '부분: 문서의 16개 주제 중 하나예요(예: 8번 부분).',
                     'limit': '허용 농도(노출기준): 공기 속 물질의 허용량이에요.'},
             'G04': {'title': '쓸 준비가 됐는지 확인해요', 'next': '확인 시작'},
             'G06': {'title': '이제 직접 해 봐요', 'next': '직접 해 보기 시작'},
             'G09': {'title': '실제 시험 결과는 이렇게 보여요',
                     'next': '다음',
                     'lead': 'AI가 뽑은 새 값을 같은 자리에서 확인해요.',
                     'example': '왼쪽은 저장된 두 결과에서 실제로 달라진 값이에요.',
                     'no_success': '이 화면을 본 것만으로 성공을 기록하지 않아요.'},
             'G13': {'title': '원문 자료와 정답을 알아봐요', 'next': '다음'},
             'G15': {'title': '이제 써 볼 준비가 됐어요', 'next': '최근 결과로 가기'}},
 'example': {'badge': '내 컴퓨터의 실제 자료',
             'label': '내 컴퓨터의 실제 자료로 그린 화면',
             'caption': '저장된 결과를 그대로 읽어 왔어요. 최근 결과 화면과 같은 값이에요.',
             'brand': '화학 안전문서 AI 결과 검토',
             'loading': '내 컴퓨터의 결과를 읽는 중이에요.',
             'empty': '아직 저장된 결과가 없어요.',
             'empty_note': '이 문서 묶음으로 시험하면 이 자리에 실제 값이 보여요.',
             'failed': '저장된 결과를 읽지 못했어요.',
             'failed_note': '안내는 그대로 이어서 볼 수 있어요.',
             'no_value': '이 결과에서 보여 줄 틀린 값을 찾지 못했어요.',
             'no_change': '저장된 두 결과에서 달라진 값을 찾지 못했어요.',
             'no_prompt': '지시문을 읽지 못했어요.',
             'no_sample': '이 묶음에서 열 수 있는 문서를 찾지 못했어요.',
             'not_checked': '아직 확인 전이에요',
             'score_unit': '/ 100점',
             'step1': '1. 최근 결과',
             'step2': '2. 원문 줄',
             'step3': '3. 다시 시험',
             'biggest': '가장 큰 문제',
             'ready_title': '쓸 준비를 확인해요',
             'saved': '저장된 결과',
             'key': '비교할 정답',
             'ai': 'AI 상태',
             'offline': '저장된 결과는 AI 없이도 읽을 수 있어요.',
             'source_title': 'AI 값과 원문을 맞춰 봐요',
             'ai_value': 'AI가 뽑은 값',
             'answer_label': '정답',
             'read_line': 'AI 값이 정답과 다르면 점수가 깎여요. 어느 쪽이 맞는지는 AI가 댄 근거 줄로 확인해요.',
             'result_title': '저장된 두 결과에서 달라진 값이에요',
             'old_value': '이전 결과 값',
             'new_value': '이번 결과 값',
             'result_note': '같은 자리의 값이 실행마다 어떻게 달라지는지 봐요.',
             'defaults_title': '같은 기준으로 결과를 봐요',
             'set': '문서 묶음',
             'trust': '점수는 개선 방향을 보는 참고값이에요.',
             'data_title': '지금 고른 원문 자료예요',
             'data_counts': '열 수 있는 문서 {open}건 · 잠긴 평가 문서 {locked}건',
             'data_doc': '{doc} · {pages}쪽',
             'data_lines': '첫 쪽의 실제 글자예요.',
             'answers_title': '지금 고를 수 있는 정답이에요',
             'answers_count': '정답 {docs}건 · 잠긴 평가 문서 {locked}건',
             'answers_compare': 'AI 값을 지금 고른 정답과 이렇게 견줘요.',
             'line_at': '{page}쪽 {line}번째 줄',
             'tunnel_open': '열림',
             'tunnel_closed': '닫힘'}}
COPY_EXCEPTIONS.update({'guide.navigation': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.back': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.skip': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.resume': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.resume_action': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.chapter_label': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.chapters.2': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.chapters.3': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.chapters.4': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.progress': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.progress_label': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.close.title': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.close.resume': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.close.keep': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.close.running': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G01.title': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G01.next': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G03.title': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G03.next': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G03.lead': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G03.terms': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G03.draft': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G03.part': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G03.limit': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G04.title': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G04.next': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G06.title': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G06.next': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G09.title': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G09.next': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G09.lead': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G09.example': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G09.no_success': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G13.title': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G13.next': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G15.title': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.screens.G15.next': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.badge': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.label': '11/01 사용자 결정: 예시 화면을 한 이름으로 읽습니다.',
 'guide.example.step1': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.step2': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.step3': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.biggest': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.ready_title': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.saved': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.key': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.ai': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.offline': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.source_title': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.ai_value': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.read_line': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.result_title': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.old_value': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.new_value': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.result_note': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.defaults_title': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)',
 'guide.example.trust': '처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)'})

UI_TEXT["guide"]["screens"].update({
    "G05": {"title": "준비 상태를 확인해요", "next": "다음"},
    "G07": {"title": "가장 큰 문제의 원문 줄을 열어 보세요", "next": "원문 줄 열기"},
    "G08": {"title": "AI에게 보낼 내용을 확인해 보세요", "next": "AI 없이 보내 보기"},
    "G10": {"title": "실제 시험에는 AI가 필요해요", "next": "AI 켜기 화면으로"},
    "G11": {"title": "실제로 한 부분 시험해 보세요", "next": "시험 보내기"},
    "G12": {"title": "첫 결과를 얻었어요", "next": "다음"},
})
UI_TEXT["guide"].update({
    "next": "다음", "practice_skip": "건너뛰기", "before": "누르기 전에 알아 둘 것",
    "target": "{doc} · {section}번 부분",
    "ready": {
        "lead": "저장된 결과와 정답이 있으면 시작할 수 있어요. AI는 실제 시험에만 필요해요.",
        "results": "저장된 결과", "key": "비교할 정답", "ai": "AI 상태",
        "states": {"checking": "확인 중", "present": "있음", "absent": "없음", "unknown": "확인 안 됨"},
        "ai_optional": "지금은 AI가 꺼져 있어도 괜찮아요. AI는 직접 해 보기 3(실제 AI 시험)에만 필요해요.",
        "empty": "저장된 결과가 없어요", "empty_lead": "원문을 여는 직접 해 보기는 건너뛰어요. AI에게 보낼 내용을 확인하는 연습은 할 수 있어요.",
        "continue_practice": "연습으로 이어가기", "failed": "준비 상태를 확인하지 못했어요",
        "request_failed": "조회 요청이 실패했어요.", "retry_todo": "할 일: 다시 확인해요. 결과가 없는지는 아직 알 수 없어요.",
        "retry": "다시 확인", "open_ai": "AI 켜기 화면으로 가기", "choose_key": "비교할 정답 고르기",
    },
    "source": {
        "lead": "총점이 가장 많이 깎인 기준의 틀린 값을 확인해요.",
        "uses": "저장된 결과 사용 · AI를 부르지 않아요", "record": "성공하면 남는 기록: 원문 확인 성공",
        "ai_value": "AI가 뽑은 값", "key_value": "정답", "open": "원문 줄 열기",
        "waiting": "원문 줄은 아직 열지 않았어요. 아래 단추를 누르면 이 자리에 열려요.",
        "success": "근거 줄을 찾았어요", "estimated": "이 값은 AI가 댄 줄이 없어요", "another": "다른 값으로",
        "estimated_only": "원문 줄(추정)만 있어요.", "no_actual": "AI가 댄 실제 근거 줄은 없어요.",
        "not_recorded": "원문 확인 성공은 기록하지 않았어요.",
        "line": "{page}쪽 {line_no}번째 줄 · 선택됨", "actual": "AI가 댄 실제 근거 줄이에요.",
        "key_caution": "정답도 틀릴 수 있어요.", "empty": "확인할 틀린 값을 찾지 못했어요. 이 직접 해 보기는 건너뛸 수 있어요.",
        "request_failed": "원문을 불러오지 못했어요.", "retry_todo": "할 일: 같은 값을 다시 확인해요.",
    },
    "practice": {
        "lead": "같은 문제 부분으로 연습해요. AI를 켜지 않아도 할 수 있어요.",
        "uses": "연습 · AI를 부르지 않아요", "record": "성공하면 남는 기록: 연습 1회",
        "send": "AI 없이 보내 보기", "done": "보낼 내용을 확인했어요",
        "waiting": "보낼 내용을 준비해요. 지시문과 문서 요약이 이 자리에 보여요.",
        "prompt": "AI에게 시킬 일", "input": "보낼 문서 요약", "cancel": "연습 취소하기",
        "no_real": "실제 AI 시험은 아직 하지 않았어요.",
    },
    "ai": {
        "lead": "한 부분을 실제로 시험하려면 AI가 답할 수 있어야 해요.",
        "off": "지금은 AI가 꺼져 있어요.", "still_off": "아직 AI가 준비되지 않았어요.",
        "tunnel_open": "회사 서버로 가는 통로는 열려 있어요. AI 켜기 화면에서 모델을 준비해요.",
        "checked": "마지막 확인: {time}", "return_not_success": "돌아온 것만으로 준비 완료가 되지는 않아요.",
        "without": "AI 없이 끝내기", "skip_note": "실제 AI 시험을 건너뛰고 기본값으로 가요. 연습 기록은 남아요.",
        "cost_action": "이 단추는 화면만 옮겨요. 돈이 드는 일은 그 화면의 확인 창에서 금액을 보고 직접 정해요.",
        "cost": "회사 서버는 임대료가 없어요. 빌린 서버는 시간당 요금이 들어요.",
        "return": "안내로 돌아가기", "return_note": "모델 상태를 다시 확인한 뒤 안내를 이어가요.",
    },
    "trial": {
        "uses": "실제 AI 시험 · AI를 불러요", "record": "성공하면 남는 기록: 실제 시험 성공",
        "send": "시험 보내기", "retry": "다시 시험", "running": "한 부분을 시험하고 있어요",
        "busy": "시험 중이에요", "waiting": "실제 시험을 보낼 준비가 됐어요. 시험 결과는 이 카드 안에 보여요.",
        "waiting_answer": "AI의 답을 기다리고 있어요.", "elapsed": "{seconds}초 지났어요.",
        "stages": {"input": "보낼 내용 준비", "answer": "AI 응답 받기", "parse": "답을 값으로 읽기", "summary": "결과 요약 보기"},
        "complete": "완료", "progress": "진행 중", "wait": "대기",
        "not_yet": "실제 시험 성공은 아직 기록하지 않았어요.", "cannot_stop": "처리 중인 시험은 여기서 멈출 수 없어요.",
        "done": "한 부분의 실제 시험이 끝났어요", "proof": "결과 판정 근거 보기",
        "proof_text": "보낸 문서와 {section}번 부분이 일치해요. 작업은 정상 종료했어요. 결과 요청은 {status}이에요. 선택 부분을 읽는 데 성공했어요.",
        "failed": "AI가 답했지만 읽지 못했어요", "failed_fact": "답을 결과 값으로 읽지 못했어요.",
        "failed_todo": "할 일: 같은 부분을 다시 시험해요.", "not_recorded": "실제 시험 성공은 기록하지 않았어요.",
    },
    "records": {
        "not_yet": "실제 시험은 아직이에요", "lead": "이번에 확인한 결과를 따로 남겼어요.",
        "source_only": "원문 근거 확인은 마쳤어요. AI를 준비한 뒤 실제 시험을 할 수 있어요.",
        "practice_only": "아직 실제 시험 성공 기록은 없어요.",
        "source": "원문 근거 확인", "practice": "AI 없이 연습", "trial": "한 부분 실제 시험",
        "none": "아직이에요", "count": "{count}회", "separate": "연습은 실제 시험 성공과 따로 남겨요.",
    },
    "recovery": {
        "timeout": "확인 시간이 지났어요. 작업 기록에서 진행 상태를 확인할 수 있어요.",
        "fact": "시험 결과를 아직 확인하지 못했어요.", "todo": "할 일: 결과를 다시 확인해요. 전송은 자동으로 반복하지 않아요.",
        "no_target": "시험할 문서와 모델을 확인하지 못했어요.", "target_todo": "할 일: 문서 묶음을 확인한 뒤 다시 확인해요.",
        "cancelled": "이 시도의 결과 확인을 취소했어요. 늦게 도착한 답은 성공으로 세지 않아요.",
    },
})
# 신규 문구도 같은 예외 표에 두며 BUILD의 승인 대기 표에서 구분한다.
for _guide_group in ("ready", "source", "practice", "ai", "trial", "records", "recovery"):
    for _guide_key, _guide_value in UI_TEXT["guide"][_guide_group].items():
        for _guide_leaf in ([_guide_key] if isinstance(_guide_value, str) else [f"{_guide_key}.{k}" for k in _guide_value]):
            COPY_EXCEPTIONS[f"guide.{_guide_group}.{_guide_leaf}"] = "처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)"
for _guide_key in ("next", "practice_skip", "before", "target"):
    COPY_EXCEPTIONS[f"guide.{_guide_key}"] = "처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)"
for _guide_screen in ("G05", "G07", "G08", "G10", "G11", "G12"):
    for _guide_key in UI_TEXT["guide"]["screens"][_guide_screen]:
        COPY_EXCEPTIONS[f"guide.screens.{_guide_screen}.{_guide_key}"] = "처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)"
for _guide_key in (
    "practice_skip", "target", "ready.states.present", "ready.states.absent", "ready.states.unknown",
    "source.key_value", "practice.prompt", "ai.return", "trial.retry", "trial.complete", "trial.progress",
):
    COPY_EXCEPTIONS.pop(f"guide.{_guide_key}", None)

UI_TEXT["guide"]["example"].update({
    "practice_title": "보낼 내용을 먼저 읽어요", "document": "문서", "part": "부분",
    "instruction_title": "AI에게 시킬 일",
    "practice_offline": "이 연습에서는 AI를 부르지 않아요.",
    "ai_title": "AI 켜기와 비용", "tunnel": "회사 서버로 가는 통로",
    "model": "AI 모델", "model_time": "모델 준비 시간", "model_duration": "15~25분",
    "guide_return": "안내로 돌아가기",
})
UI_TEXT["guide"]["practice"]["prompt_open"] = "지시문 원문 보기"
for _guide_key in ("practice_title", "practice_offline", "tunnel", "model_time"):
    COPY_EXCEPTIONS[f"guide.example.{_guide_key}"] = "처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)"
COPY_EXCEPTIONS["guide.practice.prompt_open"] = "처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)"
UI_TEXT["guide"]["skipped"] = "건너뜀"

# 처음 사용 안내 실제 확인 고침: 승인된 용어 풀이를 실제 기준 카드에 재사용한다.
for _guide_key, _glossary_key in (("exposure_meaning", "exposure"), ("criterion_meaning", "item")):
    UI_TEXT["guide"]["source"][_guide_key] = UI_TEXT["glossary"][_glossary_key]["meaning"].partition(" 예: ")[0]
    COPY_EXCEPTIONS[f"guide.source.{_guide_key}"] = "COPY.md 용어 풀이 재사용 (onboard fix step 0)"
UI_TEXT["jobs"]["focus"]["model_difference"] = "저장된 결과는 {model}로 만들었습니다. 다시 시험에 쓸 모델은 따로 고릅니다."
COPY_EXCEPTIONS["jobs.focus.model_difference"] = "onboard fix step 0: ⑤ 승인 대기"

# 처음 사용 안내 step 2: 승인 선택 화면. 자료 이름과 점수는 API에서 읽는다.
UI_TEXT["guide"]["screens"].update({
    "G02": {"title": "무엇을 먼저 해 보고 싶으세요?", "next": "다음"},
    "G14": {"title": "앞으로 볼 정답과 문서 묶음을 골라요", "next": "이걸로 정하기"},
})
UI_TEXT["guide"]["choices"] = {
    "lead": "여러 개를 고를 수 있어요.", "skip": "고르지 않은 '직접 해 보기'는 건너뛰어요.",
    "legend": "해 보고 싶은 내용을 골라요.", "disabled": "하나 이상 고르면 켜져요", "selected": "선택됨",
    "score": {"title": "점수와 문제 읽기", "note": "가장 큰 문제부터 살펴봐요."},
    "source": {"title": "원문에서 근거 확인", "note": "AI 값이 나온 줄을 열어 봐요."},
    "retest": {"title": "한 부분 다시 시험", "note": "보낼 내용을 읽고 실제 시험으로 이어가요."},
    "ai": {"title": "AI 켜기와 비용 알기", "note": "필요할 때 AI를 준비해요."},
    "example_part": "부분은 문서를 나눈 16개 주제 중 하나예요. 8번 부분은 작업장 공기의 기준(노출기준)을 다뤄요.",
}
UI_TEXT["guide"]["defaults"] = {
    "lead": "고른 기준으로 최근 결과를 보여 줘요. 고르지 않으면 지금 값을 유지해요.",
    "definition": "문서 묶음은 함께 비교할 문서들이에요. 정답은 AI 값과 견주는 기준이에요.",
    "legend": "하나를 고르면 점수 미리보기가 펼쳐져요.", "disabled": "하나를 고르면 켜져요",
    "current": "지금 쓰는 문서와 정답", "preview": "이걸로 보면 점수가 이렇게 보여요.",
    "empty": "저장된 결과가 없어요.", "empty_note": "이 묶음으로 시험한 뒤 점수를 볼 수 있어요.",
    "keep": "지금 값 그대로",
    "failed": "점수 미리보기를 불러오지 못했어요.",
    "failed_todo": "할 일: 미리보기 없이 이 기준으로 정하거나 지금 값을 유지해요.",
    "mismatch": "조회한 점수의 기준이 고른 기준과 달라요.",
    "load_failed": "고를 문서 묶음과 정답을 불러오지 못했어요.",
    "load_todo": "할 일: 다시 확인하거나 지금 값을 유지해요.",
}
# 11/2 사용자 요청: 원문 자료와 정답의 뜻, 바꾸고 더하는 법 (G16·G17, 도움말 data 장)
UI_TEXT["guide"]["screens"].update({
    "G16": {"title": "원문 자료는 AI가 읽는 문서 글이에요", "next": "다음"},
    "G17": {"title": "정답은 AI 값과 견주는 기준이에요", "next": "다음"},
})
UI_TEXT["guide"]["data"] = {
    "source": {
        "lead": "PDF를 쪽마다 글자와 그림으로 바꿔 둔 파일이에요. AI는 이 글자를 읽고, 근거도 이 글자의 줄 번호로 대요.",
        "example": "예: p5:L22는 5쪽 22번째 줄이에요.",
        "set": "문서 여러 개를 모은 폴더 하나를 문서 묶음이라고 불러요.",
        "change_title": "바꾸는 법",
        "change": "두 화면 뒤에서 바로 고를 수 있어요. 안내를 닫은 뒤에는 화면 맨 위 [필요할 때 문서 바꾸기]를 눌러요. 그 묶음으로 돌린 저장 결과만 보여요.",
        "add_title": "새로 더하는 법",
        "add1": "data/pages/<묶음 이름>/<문서 번호>/ 폴더를 만들어요.",
        "add2": "쪽마다 p001.txt(글자)와 p001.png(그림)를 넣어요. 글자 줄 앞에 L001 같은 줄 번호가 있어야 새 시험에 쓸 수 있어요.",
        "add3": "data/manifest.csv에 없는 문서 번호라면 meta.json도 넣어요. 안의 doc_id가 폴더 이름과 같아야 열려요.",
        "add4": "화면을 새로고침하면 목록에 나타나요. 앱을 다시 켤 필요는 없어요.",
        "caution": "평가용 문서는 점수가 부풀려지지 않도록 개발 중에는 열지 않아요. 목록에 잠김으로 보여요. data/pages는 git에 올리지 않아요.",
    },
    "answers": {
        "lead": "점수는 AI가 뽑은 값이 정답과 얼마나 같은지로 계산해요. 정답을 바꾸면 같은 결과의 점수도 달라져요.",
        "kinds_title": "정답은 두 가지예요",
        "gold": "사람이 확인한 정답(골드): 사람이 검토해 확정한 답이에요. data/gold에 있어요.",
        "silver": "AI 정답 초안(실버): AI가 먼저 만든 비교용 답이에요. data/silver 아래 폴더에 있고, 틀릴 수 있어요.",
        "change_title": "바꾸는 법",
        "change": "다음 화면에서 바로 고를 수 있어요. 안내를 닫은 뒤에는 화면 맨 위 [필요할 때 정답 바꾸기]를 눌러요. 저장된 결과를 AI 없이 다시 채점해요.",
        "add_title": "새로 더하는 법",
        "add1": "data/silver/<이름>/ 또는 data/gold/<이름>/ 폴더를 만들어요.",
        "add2": "문서마다 <문서 번호>.json을 넣어요. 예: T21-S001.json. 정해진 결과 형식(TO21 JSON)이어야 해요.",
        "add3": "화면을 새로고침하면 목록에 나타나요. 앱을 다시 켤 필요는 없어요.",
        "caution": "골드는 A 담당이 검수해 올려요. 고칠 곳을 찾으면 파일을 직접 바꾸지 말고 A 담당에게 알려요. 평가용 문서의 정답은 열지 않고 개수만 세요.",
    },
}
_LIVE_REASON = "11/2 사용자 요청: 왼쪽 칸을 실제 저장 결과로 채우고 원문 자료·정답 안내를 더한다"
for _live_key in ("caption", "loading", "empty", "empty_note", "failed", "failed_note", "no_value", "no_change", "no_prompt",
                  "no_sample", "not_checked", "data_title", "data_counts", "data_doc", "data_lines", "answers_title",
                  "answers_count", "answers_compare", "line_at", "tunnel_open", "tunnel_closed", "badge", "label",
                  "result_title", "old_value", "new_value", "result_note", "trust", "read_line"):
    COPY_EXCEPTIONS[f"guide.example.{_live_key}"] = _LIVE_REASON
for _live_key in ("G16.title", "G16.next", "G17.title", "G17.next", "G13.title", "G03.draft", "G09.example", "G09.no_success"):
    COPY_EXCEPTIONS[f"guide.screens.{_live_key}"] = _LIVE_REASON
for _live_group, _live_words in UI_TEXT["guide"]["data"].items():
    for _live_key in _live_words:
        COPY_EXCEPTIONS[f"guide.data.{_live_group}.{_live_key}"] = _LIVE_REASON
COPY_EXCEPTIONS["guide.chapters.4"] = _LIVE_REASON
COPY_EXCEPTIONS["guide.source.key_caution"] = _LIVE_REASON
COPY_EXCEPTIONS.pop("guide.source.key_value", None)  # 표 행 수의 '정답'과 같은 승인 글
COPY_EXCEPTIONS.pop("guide.example.answer_label", None)

for _guide_group in ("choices", "defaults"):
    for _guide_leaf, _guide_value in UI_TEXT["guide"][_guide_group].items():
        for _guide_path in ([f"{_guide_leaf}.{key}" for key in _guide_value] if isinstance(_guide_value, dict) else [_guide_leaf]):
            COPY_EXCEPTIONS[f"guide.{_guide_group}.{_guide_path}"] = "처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)"
for _guide_screen in ("G02", "G14"):
    for _guide_key in UI_TEXT["guide"]["screens"][_guide_screen]:
        COPY_EXCEPTIONS[f"guide.screens.{_guide_screen}.{_guide_key}"] = "처음 사용 안내 시안 승인 10/31 (design/onboard/mockup.html)"
for _guide_key in ("failed", "failed_todo", "mismatch", "load_failed", "load_todo"):
    COPY_EXCEPTIONS[f"guide.defaults.{_guide_key}"] = "처음 사용 안내 step 2: ⑤ 승인 대기"
COPY_EXCEPTIONS.pop("guide.choices.selected", None)  # COPY.md의 기존 승인 글

# S6 고침: 후보 선택의 결과와 접힌 정보의 이름. ⑤ 승인 대기.
UI_TEXT["guide"]["defaults"].update({
    "unavailable": "쓸 수 없는 조합 {count}개",
    "no_answers": "이 문서 묶음에 맞는 정답 파일이 없어요.",
})
UI_TEXT["guide"]["practice"]["sent_details"] = "보낸 내용 자세히 보기"
UI_TEXT["context"]["picker"].update({
    "results_found": "적용하면 이 문서 묶음의 저장 결과 {count}개를 고른 정답으로 볼 수 있어요.",
    "results_empty": "적용하면 최근 결과가 '결과 없음'으로 바뀌어요.",
    "results_failed": "적용한 뒤 볼 저장 결과를 확인하지 못했어요.",
    "results_failed_todo": "할 일: 후보를 다시 고르거나 미리보기 없이 적용해요.",
})
for _fix_key in ("guide.defaults.unavailable", "guide.defaults.no_answers", "guide.practice.sent_details",
                 "context.picker.results_found", "context.picker.results_empty",
                 "context.picker.results_failed", "context.picker.results_failed_todo"):
    COPY_EXCEPTIONS[_fix_key] = "onboard fix step 1: ⑤ 승인 대기"
