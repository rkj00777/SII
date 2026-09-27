from collections import Counter

def drift_metrics(candidates, universe_count):
    n=len(candidates); tracks=Counter(x.get('track') for x in candidates); sectors=Counter(x.get('sector','UNKNOWN') for x in candidates)
    top_sector=(max(sectors.values())/n) if n and sectors else 0.0
    return {'candidate_count':n,'candidate_rate':n/universe_count if universe_count else 0.0,'track_mix':dict(tracks),'top_sector_concentration':top_sector}

def status(value, threshold, higher_is_bad=True):
    bad=value>threshold if higher_is_bad else value<threshold
    return 'BREACH' if bad else 'OK'
