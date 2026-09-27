import os
from dataclasses import dataclass
@dataclass(frozen=True)
class Config:
 database_url:str=os.getenv('DATABASE_URL','sqlite:///./sii.db'); admin_token:str=os.getenv('SII_ADMIN_TOKEN','change-me'); timeout:int=int(os.getenv('REQUEST_TIMEOUT_SECONDS','20')); user_agent:str=os.getenv('SII_USER_AGENT','SII-v4-free-only/4.0 research')
 universe_gate:float=.99; market_gate:float=.98; fundamental_gate:float=.90; evidence_gate:float=.80; pit_gate:float=.99
SII_VERSION='4.0.0-FREE-ONLY'; CONFIG=Config()
