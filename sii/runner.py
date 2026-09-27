import os
def main():
 mode=os.getenv('SII_JOB','daily')
 if mode=='bootstrap':
  from .bootstrap import run_bootstrap;print(run_bootstrap())
 elif mode=='historical':
  from .historical import run_historical_falsification;print(run_historical_falsification(int(os.getenv('SII_START_YEAR','2019')),int(os.getenv('SII_END_YEAR','2026'))))
 elif mode=='weekly':
  from .pipeline import run_universe
  from .blind_scan import run_blind_scan
  u=run_universe();r=run_blind_scan();print({'universe':u,'scored_rows':len(r)})
 else:
  from .pipeline import run_universe;print(run_universe())
if __name__=='__main__':main()
