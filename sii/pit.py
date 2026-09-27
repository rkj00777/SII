from datetime import datetime

def pit_rows(rows, as_of): return [r for r in rows if getattr(r,'available_at',None) is not None and r.available_at<=as_of]
def assert_no_lookahead(rows, as_of):
    bad=[r for r in rows if getattr(r,'available_at',None) is None or r.available_at>as_of]
    if bad: raise AssertionError(f'PIT violation: {len(bad)} records unavailable by as_of')
def pit_coverage(rows): return 0.0 if not rows else sum(1 for r in rows if getattr(r,'available_at',None) is not None)/len(rows)

def availability_timestamp(published_at, received_at=None):
    return received_at or published_at
