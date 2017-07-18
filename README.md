# WebCrawler

Crawl sites and search for security issues.

## Installation

- clone git
- `python3 -m virtualenv -p python3.6 --system-site-packages .venv && . ./.venv/bin/activat`
- `pip3 install -r ./requirements.txt`
- `./webcrawler.py -vvv ./config-example.yml -`

## Usage

```
usage: webcrawler.py [-h] [-v] config_file out_file

Crawl all configured sites and search for security issues.

positional arguments:
  config_file    The yaml config file
  out_file       The yaml file to write the output

optional arguments:
  -h, --help     show this help message and exit
  -v, --verbose  More output
```

## Idea

- https://www.golem.de/news/https-private-schluessel-auf-dem-webserver-1707-128860.html
- https://www.golem.de/news/kundendaten-datenleck-bei-der-deutschen-post-1707-128751.html
- https://www.golem.de/news/sicherheitsluecke-fehlerhaft-konfiguriertes-git-verzeichnis-bei-redcoon-1705-127777.html

## License

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
