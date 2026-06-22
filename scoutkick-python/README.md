# ScoutKick API Client

Zero-dependency Python client for the [ScoutKick](https://scoutkick.onrender.com) EPA rating system for FIRST Tech Challenge.

```python
from scoutkick_api import ScoutKick

sk = ScoutKick()  # defaults to https://scoutkick.onrender.com

sk.get_team(26914)
sk.predict(red=[26914, 32736], blue=[23400, 24599])
sk.get_teams(season="2025", limit=10)
sk.compare(teams=[26914, 32736])
```
