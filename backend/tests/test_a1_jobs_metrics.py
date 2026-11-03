from msds.service.jobs import _duration_estimate


def attempt(start, finish, status='done'):
    return {'status': status, 'started_at': f'2026-11-03T00:00:{start:02d}+00:00',
            'finished_at': f'2026-11-03T00:00:{finish:02d}+00:00'}


def test_estimate_requires_three_actual_successful_job_durations():
    assert _duration_estimate([[attempt(0, 5)], [attempt(0, 10)]]) is None
    assert _duration_estimate([[attempt(0, 5)], [attempt(0, 10)], [attempt(0, 20)]]) == 20


def test_estimate_skips_failed_and_invalid_samples_and_counts_one_per_job():
    assert _duration_estimate([[attempt(0, 3), attempt(0, 15)], [attempt(0, 7, 'failed')],
                               [{'status': 'done'}], [attempt(0, 10)]]) is None
