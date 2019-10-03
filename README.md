# pingdom-check-loader

## Install/Setup

Run via Docker:
https://hub.docker.com/r/bitsofinfo/pingdom-check-loader

Otherwise:

**Python 3.7+**

Dependencies: See [Dockerfile](Dockerfile)

## How it works

## Usage

```
./loader.py --help

usage: loader.py [-h] [-f CHECKS_CONFIG_FILE] [-s SITES] [-c CHECK_NAMES]
                 [-u PINGDOM_API_BASE_URL] [-t PINGDOM_API_TOKEN_FILE] [-d]
                 [-x] [-D] [-q DELETE_TAG_QUALIFIERS] [-l LOG_LEVEL]
                 [-b LOG_FILE]

optional arguments:
  -h, --help            show this help message and exit
  -f CHECKS_CONFIG_FILE, --checks-config-file CHECKS_CONFIG_FILE
                        Path to a YAML containing the check configs to process
                        (default: checkconfigs.yaml)
  -s SITES, --sites SITES
                        Optional comma delimited list of 'sites' to process.
                        Default None (all sites) (default: None)
  -c CHECK_NAMES, --check-names CHECK_NAMES
                        Optional comma delimited list of 'checks.[name]' names
                        to process. Default None (all checks) (default: None)
  -u PINGDOM_API_BASE_URL, --pingdom-api-base-url PINGDOM_API_BASE_URL
                        The Pingdom API base URL (inclusive of version)
                        (default: https://api.pingdom.com/api/3.1)
  -t PINGDOM_API_TOKEN_FILE, --pingdom-api-token-file PINGDOM_API_TOKEN_FILE
                        Path to a file that contains an valid pingdom API
                        token (default: None)
  -d, --dump-generated-checks
                        Dumps all generated checks to STDOUT (default: False)
  -x, --create-in-pingdom
                        Create all checks in Pingdom for the designated
                        --check-names argument (default: False)
  -D, --delete-in-pingdom
                        DELETE all checks in Pingdom who's 'tags' contains any
                        of the check names in the --checks argument (default:
                        False)
  -q DELETE_TAG_QUALIFIERS, --delete-tag-qualifiers DELETE_TAG_QUALIFIERS
                        Comma delimited list of one or more tags. To be used
                        in conjunction w/ --delete-in-pingdom. Will only
                        delete matching --check-names that also contain ALL of
                        the specified tags in this comma delimited list of tag
                        names (default: None)
  -l LOG_LEVEL, --log-level LOG_LEVEL
                        log level, DEBUG, INFO, etc (default: DEBUG)
  -b LOG_FILE, --log-file LOG_FILE
                        Path to log file; default None = STDOUT (default:
                        None)
```