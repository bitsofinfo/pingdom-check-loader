# pingdom-check-loader

This provides a simple CLI utility for managing "checks" in [Pingdom](https://pingdom.com) using the [3.1 API](https://docs.pingdom.com/api/)

The CLI lets you declare your desired check configuration state in YAML files; the CLI consumes that configuration, then generates one or more checks driven by the configuration. See the sample [checkconfigs.yaml](checkconfigs.yaml) for more docs and details on the configuration format.

Once checks are generated they can be created against a target Pingdom account. This CLI does not support mutating previously
defined checks. Checks changes are additive in nature. You can generate and produce new checks and delete old ones only. Existing checks (while editable in the Pingdom GUI) are not mutable via this CLI by design.

The checks generated and created by this utility are intended to be immutable; generated checks are tagged appropriately to be easy to find via Pingdom's GUI and APIs. Tags are automatically created based on a CLI invocation `timestamp` and `pathParts` (see YAML) so that all generated checks can be managed as a single set. You can then use these tags to delete checks (via this CLI) which can then be replaced by newer generated iterations of them as your requirements change. You can do things in any order you desire; for example create one version of checks, then interate and generate the 2nd iteration; after your 2nd iteration is functioning as desired you can cleanup the 1st iteration using the `--delete-tag-qualifers` flag passing the 1st iterations `timestamp` identifier.

## Requirements, install, setup

1. You need an account at Pingdom to actually create checks there (free trial or paid)
2. You need a [Pingdom API token](https://my.pingdom.com/3/api-tokens) w/ read-write access to your account
3. This was coded against the [Pingdom 3.1 API](https://docs.pingdom.com/api/)

Run via Docker:
https://hub.docker.com/r/bitsofinfo/pingdom-check-loader

Otherwise you can run on the command line, but you will need **Python 3.7+** on your local, plus some dependencies: See [Dockerfile](Dockerfile) for `pip` installable dependencies.

## Configuration

See the sample [checkconfigs.yaml](checkconfigs.yaml) for more docs and details on the configuration format.

## How it works

Before even using this, you need an account at Pingdom (paid or free trial) and have your account configured w/ an read-write API token as stated above.

Once that is setup, the functionality is basically as follows:

* `loader.py` consumes your arguments and reads the `--checks-config-file`
  
* For each declared check in the `sites.[yoursite].checks.[check]` it dynamically generates one or more check definitions using the `forEach` directives over declared `pathParts` to generate varying amounts of checks

* The characteristics of generated checks is controlled by an inheritence based model, whereby your `defaults` can be overriden by `pathParts` and/or individual check blocks within `forEach` directives.

* Once checks are generated, you are prompted for review, and can then apply them to Pingdom.

* Each run of the CLI generates a `run identifier` in the format of `YYYmmDD_HHmmSSms` which is tagged on all created checks. This tag can be used to subsequently find and delete the checks should you wish to load a new-iteration w/ changes.

* The CLI also supports deleting checks by check names and/or tag combinations

## Some examples

Setup a python virtual env:
```bash
cd pingdom-check-loader
python3 -m venv venv
source venv/bin/activate
pip install --requirement requirements.txt
```

Lets just see what would be generated for this [checkconfigs.yaml](checkconfigs.yaml) example: (you should get 17 checks)
```bash
 ./loader.py     \
    --checks-config-file checkconfigs.yaml     \
    --dump-generated-checks 
```

Great, but lets only generate the `highPriority109Only` checks: (you should get 1 check)
```bash
 ./loader.py     \
    --checks-config-file checkconfigs.yaml     \
    --check-names highPriority109Only \
    --dump-generated-checks 
```

Ok, but lets generate multiple checks: (you should get 3 checks)
```bash
 ./loader.py     \
    --checks-config-file checkconfigs.yaml     \
    --check-names highPriority109Only,highPriorityAllTags \
    --dump-generated-checks 
```

How about we generate multiple the `highPriorityExamplesDirs` checks: (you should get 2 checks)
```bash
 ./loader.py     \
    --checks-config-file checkconfigs.yaml     \
    --check-names highPriorityExamplesDirs \
    --dump-generated-checks 
```

Ok great, lets publish all these to Pingdom: (3 checks). Important: for this part of the example to work *you need to provide a api token file below in a file named trial.token*
```bash
 ./loader.py     \
    --checks-config-file checkconfigs.yaml     \
    --check-names highPriority109Only,highPriorityAllTags \
    --dump-generated-checks \
    --create-in-pingdom \
    --pingdom-api-token-file trial.token
```

After they are created you will notice something like this in the logs:
```
...
2019-10-03 22:13:40,529 - root - DEBUG - Finished: run identifier: 20191003_22285191
...
```

We can then use that identifier to cleanup the entire set of checks we just generated and created. *Note you need to use the `identifier` output form your example run, the below is a sample...*
```bash
 ./loader.py     \
    --checks-config-file checkconfigs.yaml     \
    --delete-tag-qualifiers 20191003_22285191 \
    --delete-in-pingdom \
    --pingdom-api-token-file trial.token
```

In addition the above examples there are other combinations of arguments you can use to more selectively select the checks you want to generate and or delete with the `--check-names` and `--delete-tag-qualifiers` arguments. 

## Running via Docker

Running via Docker is not much different than the command line directly, with the exception of you are using `docker run` in interactive mode. Below is simply a basic example.


Generate and dump only:
```bash
docker run -i -v `pwd`:/configs \
    bitsofinfo/pingdom-check-loader:latest loader.py \
    --checks-config-file /configs/checkconfigs.yaml     \
    --dump-generated-checks     
```

Generate and publish:
```bash
docker run -i -v `pwd`:/configs \
    bitsofinfo/pingdom-check-loader:latest loader.py \
    --checks-config-file /configs/checkconfigs.yaml     \
    --dump-generated-checks     \
    --check-names test1     \
    --create-in-pingdom     \
    --pingdom-api-token-file /configs/my.token
```

## Pingdom API issues

https://thwack.solarwinds.com/message/426746

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
                        Path to a YAML file containing the check configuration
                        declarations to process (default: checkconfigs.yaml)
  -s SITES, --sites SITES
                        Optional comma delimited list of 'sites' to process.
                        Default None (all sites) (default: None)
  -c CHECK_NAMES, --check-names CHECK_NAMES
                        Optional comma delimited list of 'checks.[name]' names
                        to generate checks from. Default None (all checks)
                        (default: None)
  -u PINGDOM_API_BASE_URL, --pingdom-api-base-url PINGDOM_API_BASE_URL
                        The Pingdom API base URL (inclusive of version)
                        (default: https://api.pingdom.com/api/3.1)
  -t PINGDOM_API_TOKEN_FILE, --pingdom-api-token-file PINGDOM_API_TOKEN_FILE
                        Path to a file that contains an valid pingdom API
                        token (default: None)
  -d, --dump-generated-checks
                        Dumps all generated checks to STDOUT (default: False)
  -x, --create-in-pingdom
                        CREATE all checks in Pingdom for the designated
                        --check-names argument (default: False)
  -D, --delete-in-pingdom
                        DELETE all checks in Pingdom who's 'tags' contains any
                        of the check names in the --check-names argument
                        (default: False)
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