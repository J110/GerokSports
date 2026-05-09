"""Probe ESPNcricinfo ball-by-ball commentary page."""
import requests
import re
import json
from bs4 import BeautifulSoup

headers = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                   'AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'en-US,en;q=0.9',
}

series_id = '1502138'
match_id = '1512773'

# Try the page and API
urls = [
    ('Ball-by-ball page',
     f'https://www.espncricinfo.com/series/icc-men-s-t20-world-cup-2025-26-{series_id}'
     f'/india-vs-new-zealand-final-{match_id}/ball-by-ball-commentary'),
    ('Consumer API commentary',
     f'https://hs-consumer-api.espncricinfo.com/v1/pages/match/commentary'
     f'?lang=en&seriesId={series_id}&matchId={match_id}'
     f'&inningNumber=1&commentaryType=ALL&fromInningOver=-1'),
    ('Consumer API match home',
     f'https://hs-consumer-api.espncricinfo.com/v1/pages/match/home'
     f'?lang=en&seriesId={series_id}&matchId={match_id}'),
]

for name, url in urls:
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        print(f'{name}: {resp.status_code} len={len(resp.text)}')
        if resp.status_code == 200:
            text = resp.text
            # Check for __NEXT_DATA__
            if '__NEXT_DATA__' in text:
                start = text.find('__NEXT_DATA__')
                tag_start = text.rfind('<script', max(0, start - 100), start)
                tag_end = text.find('</script>', start)
                json_start = text.find('>', tag_start) + 1
                json_str = text[json_start:tag_end]
                try:
                    data = json.loads(json_str)
                    props = data.get('props', {}).get('pageProps', {})
                    print(f'  __NEXT_DATA__ pageProps keys: {list(props.keys())[:15]}')
                    # Look for commentary data
                    for key in props:
                        val = props[key]
                        if isinstance(val, dict) and ('comments' in val or 'commentary' in val or 'innings' in val):
                            print(f'  {key} has: {list(val.keys())[:10]}')
                        elif isinstance(val, list) and len(val) > 0:
                            print(f'  {key}: list[{len(val)}]')
                except json.JSONDecodeError as e:
                    print(f'  JSON parse error: {e}')
            
            # Check for JSON response
            try:
                data = resp.json()
                if isinstance(data, dict):
                    print(f'  JSON keys: {list(data.keys())[:15]}')
                    # Look for comments/commentary
                    for k in data:
                        v = data[k]
                        if isinstance(v, dict):
                            print(f'    {k}: dict keys={list(v.keys())[:10]}')
                        elif isinstance(v, list):
                            print(f'    {k}: list[{len(v)}]')
                            if v and isinstance(v[0], dict):
                                print(f'      [0] keys: {list(v[0].keys())[:10]}')
            except:
                pass
            
            # Count over.ball patterns
            overs = re.findall(r'\d+\.\d+\s+\w+\s+to\s+\w+', text)
            if overs:
                print(f'  Over.ball patterns: {len(overs)}')
                for o in overs[:3]:
                    print(f'    {o}')
        else:
            print(f'  Body: {resp.text[:200]}')
        print()
    except Exception as e:
        print(f'{name}: ERR {str(e)[:100]}')
        print()
