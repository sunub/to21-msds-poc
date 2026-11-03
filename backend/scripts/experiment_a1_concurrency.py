"""A1의 문서 동시 처리 실험. 실제 API와 모델을 호출하므로 격리된 개발 환경에서만 실행한다.

입력과 출력은 사외비일 수 있다. 결과는 사용자가 지정한 새 디렉터리에만 저장한다.
실험 계획과 판정의 한계는 docs/adr/0006-a1-동시-추출-실험.md를 참고한다.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import _common  # noqa: F401  # src 경로 등록
from msds.checks.validator import load_to21_module


def request_json(base: str, path: str, *, body: bytes | None = None) -> dict:
    req = Request(base.rstrip('/') + path, data=body,
                  headers={'Content-Type': 'application/pdf'} if body is not None else {})
    try:
        with urlopen(req, timeout=60) as response:
            value = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f'API 요청 실패 ({path.split("?")[0]}): {type(exc).__name__}') from exc
    if not isinstance(value, dict):
        raise ValueError(f'API 응답이 객체가 아닙니다: {path}')
    return value


def score_items(scorer, baseline: dict, other: dict) -> dict[str, float]:
    """TO21 채점기 점수를 이용한다. 점수만으로 전체 칸 일치가 보장되지는 않는다."""
    rows = scorer.score(baseline, other)
    items: dict[str, float] = {}
    for _, name, _, score, _, _ in rows:
        if name in items:
            raise ValueError(f'채점 항목 이름이 중복됩니다: {name}')
        items[name] = float(score)
    if not items:
        raise ValueError('채점 결과가 비어 있습니다')
    return items


def compare_items(baseline: dict[str, float], concurrent: dict[str, float]) -> list[str]:
    if baseline.keys() != concurrent.keys():
        raise ValueError('채점 항목이 달라 비교할 수 없습니다')
    return [key for key in baseline if concurrent[key] + 1e-9 < baseline[key]]


def make_output_dir(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(path, 0o700)
    return path


def write_json(path: Path, data: object) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
        out.write('\n')


def submit(base: str, pdf: Path, as_of: str | None) -> str:
    query = {'filename': pdf.name}
    if as_of:
        query['as_of'] = as_of
    result = request_json(base, '/api/documents?' + urlencode(query), body=pdf.read_bytes())
    doc_id = result.get('id')
    if not isinstance(doc_id, str) or not doc_id:
        raise ValueError('업로드 응답에 작업 ID가 없습니다')
    return doc_id


def run_group(base: str, pdfs: list[Path], as_of: str | None, poll: float, timeout: float) -> list[dict]:
    """동시에 제출하고 종료 상태를 관측한다. 서버가 실제로 병렬 실행했는지는 별도 확인한다."""
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(pdfs)) as pool:
        ids = list(pool.map(lambda pdf: submit(base, pdf, as_of), pdfs))
    if len(set(ids)) != len(ids):
        raise ValueError('서버가 중복 작업 ID를 반환했습니다')
    runs = {doc_id: {'id': doc_id, 'status': 'queued', 'stages_observed_seconds': {},
                     'previous_stage': None, 'last_poll': started, 'peak_running': 0}
            for doc_id in ids}
    peak = 0
    while True:
        if time.monotonic() - started > timeout:
            raise TimeoutError(f'작업 제한 시간 초과. 작업 ID: {ids}')
        for doc_id in ids:
            run = runs[doc_id]
            if run['status'] in ('done', 'failed', 'interrupted'):
                continue
            state = request_json(base, '/api/documents/' + quote(doc_id, safe=''))
            now = time.monotonic()
            previous = run['previous_stage']
            if previous:
                stages = run['stages_observed_seconds']
                stages[previous] = stages.get(previous, 0) + now - run['last_poll']
            run.update(status=state['status'], previous_stage=state.get('stage'), last_poll=now)
        peak = max(peak, sum(run['status'] == 'running' for run in runs.values()))
        if all(run['status'] in ('done', 'failed', 'interrupted') for run in runs.values()):
            break
        time.sleep(poll)
    duration = time.monotonic() - started
    result = []
    for doc_id in ids:
        run = runs[doc_id]
        run['batch_wall_seconds'] = round(duration, 3)
        run['peak_running'] = peak
        run.pop('previous_stage')
        run.pop('last_poll')
        if run['status'] == 'done':
            response = request_json(base, '/api/documents/' + quote(doc_id, safe='') + '/result')
            if not isinstance(response.get('to21'), dict):
                raise ValueError(f'{doc_id}: 결과에 TO21 객체가 없습니다')
            run['result'] = response['to21']
        result.append(run)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--url', default='http://127.0.0.1:8020', help='격리된 테스트용 추출 API 주소')
    ap.add_argument('--target', type=Path, action='append', required=True,
                    help='기준 문서 PDF; 서로 다른 양식 3개 이상, 이 중 스캔본 1개 포함하여 반복 지정')
    ap.add_argument('--companion', type=Path, action='append', required=True,
                    help='동시 요청에 사용할 PDF; 서로 다른 4개 이상 반복 지정')
    ap.add_argument('--scanned-target', type=int, required=True, help='스캔본 target 순번 (1부터)')
    ap.add_argument('--out', type=Path, required=True, help='결과를 저장할 아직 없는 디렉터리')
    ap.add_argument('--as-of', help='모든 요청에 적용할 기준일 (YYYY-MM-DD)')
    ap.add_argument('--poll', type=float, default=2.0, help='상태 조회 간격(초)')
    ap.add_argument('--timeout', type=float, default=3600.0, help='각 묶음의 최대 대기 시간(초)')
    ap.add_argument('--confirm-real-calls', action='store_true', help='실제 API 작업과 모델 호출을 실행')
    args = ap.parse_args()
    if not args.confirm_real_calls:
        ap.error('실제 작업과 모델 호출을 확인하려면 --confirm-real-calls를 지정하세요')
    if len(args.target) < 3 or len(args.companion) < 4:
        ap.error('target 3개 이상과 companion 4개 이상이 필요합니다')
    if not 1 <= args.scanned_target <= len(args.target):
        ap.error('scanned-target 순번이 범위를 벗어났습니다')
    if args.poll <= 0 or args.timeout <= 0:
        ap.error('poll과 timeout은 양수여야 합니다')
    files = [p.resolve() for p in args.target + args.companion]
    if len(set(files)) != len(files) or any(not p.is_file() or p.suffix.lower() != '.pdf' for p in files):
        ap.error('서로 다른 기존 PDF 파일을 지정하세요')
    digests = [hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
    if len(set(digests)) != len(digests):
        ap.error('경로가 달라도 파일 내용이 같으면 다른 문서가 아닙니다')
    scorer = load_to21_module('scorer')  # 시작 전에 채점기 존재 확인
    out = make_output_dir(args.out)
    report = {'target_count': len(args.target), 'scanned_target_index': args.scanned_target,
              'as_of': args.as_of, 'poll_seconds': args.poll,
              'warning': '관찰된 running 수는 폴링 하한이며, 단계 시간은 모델 호출 시간과 다릅니다.',
              'targets': []}
    for index, target in enumerate(args.target, 1):
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        print(f'기준 문서 {index}: 단독 2회', flush=True)
        baseline_runs = [run_group(args.url, [target], args.as_of, args.poll, args.timeout)[0] for _ in range(2)]
        if any(r['status'] != 'done' for r in baseline_runs):
            raise RuntimeError(f'단독 실행 실패: {[r["id"] for r in baseline_runs]}')
        base1, base2 = (r.pop('result') for r in baseline_runs)
        write_json(out / f'target-{index}-baseline-1.json', base1)
        write_json(out / f'target-{index}-baseline-2.json', base2)
        natural = score_items(scorer, base1, base2)
        entry = {'target_sha256': digest, 'baseline_runs': baseline_runs,
                 'natural_variation_items': natural, 'batches': []}
        for companions in (1, 2, 4):
            print(f'기준 문서 {index}: 다른 문서 {companions}개와 함께', flush=True)
            runs = run_group(args.url, [target, *args.companion[:companions]], args.as_of, args.poll, args.timeout)
            if any(r['status'] != 'done' for r in runs):
                entry['batches'].append({'companions': companions, 'runs': runs, 'comparison': '실패'})
                continue
            target_result = runs[0]['result']
            write_json(out / f'target-{index}-companions-{companions}.json', target_result)
            current = score_items(scorer, base1, target_result)
            overlap = runs[0]['peak_running'] >= 2
            entry['batches'].append({'companions': companions, 'runs': [
                {k: v for k, v in run.items() if k != 'result'} for run in runs],
                'scores': current, 'below_natural_baseline_items': compare_items(natural, current),
                'overlap_observed': overlap,
                'comparison': '미검증: 병렬 처리 관찰 안 됨' if not overlap else '비교 완료'})
        report['targets'].append(entry)
        write_json(out / f'target-{index}-summary.json', entry)
    write_json(out / 'report.json', report)
    print(f'결과 저장: {out} (원본 결과가 포함되므로 접근을 제한하세요)')


if __name__ == '__main__':
    main()
