#!/usr/bin/env python3

__author__ = "bitsofinfo"

import datetime
import logging
import socket
import base64
import time
import random
import copy
import json
import requests
import re
import pprint
import argparse
import sys
import yaml
from multiprocessing import Pool
from jinja2 import Template, Environment

class DumbEncoder(json.JSONEncoder):
    def default(self, o):
        return o.__dict__ 

class ForEachHandler:
    def __init__(self, defaults, site, forEach):

        self.site = site
        self.defaults = defaults

        # a forEach can only have one key
        # and that key represents the pathPart
        # type to iterate over
        pathPartType = list(forEach.keys())[0]
        self.pathParts = PathParts.types[pathPartType]

        self.subParts = None
        self.data = None

        # if the forEach's pathPart key also has a 
        # nested forEach itself, lets recurse
        for checkDirective,directive in forEach[pathPartType].items():
            if checkDirective == 'forEach':
                self.subParts = ForEachHandler(defaults,site,directive)
            else:
                if not self.data:
                    self.data = {}
                self.data.update(forEach[pathPartType])

         
    def getCheckConf(self,path):
        checkConf = {}
        if self.defaults: 
            checkConf.update(self.defaults)
        if path.metadata:
            checkConf.update(path.metadata)
        if self.data:
            checkConf.update(self.data)

        return checkConf
    
    def pathPartIsPermitted(self,pathPartName):
        if self.data and 'except' in self.data:
            if pathPartName in self.data['except']:
                return False
        if self.data and 'only' in self.data:
            if pathPartName not in self.data['only']:
                return False
        return True
    
    def enforceLimit(self,items):
        if self.data and 'limit' in self.data:
            return items[:self.data['limit']]
        return items

    def build(self,checks):

        if checks:
            newChecks = []
            for c in checks:
                for pathName in self.enforceLimit(self.pathParts.getPathNames()):
                    if self.pathPartIsPermitted(pathName):
                        path = self.pathParts.getPath(pathName)
                        x = copy.deepcopy(c)
                        if path.metadata:
                            x.update(path.metadata)
                        if self.data:
                            x.update(self.data)
                        
                        pathToSet = copy.deepcopy(path)
                        x.applyPathPart(pathToSet)
                        newChecks.append(x)

            checks = newChecks

        else:
            checks = []
            for p in self.enforceLimit(self.pathParts.getPathNames()):
                if self.pathPartIsPermitted(p):
                    path = self.pathParts.getPath(p)

                    c = CheckConfig(self.defaults, self.site, self.getCheckConf(path), path)
                    checks.append(c)

        
        if self.subParts: 
            checks = self.subParts.build(checks)

        return checks
                

    def getItems(self):
        return self.pathParts

class PathPart:
    def __init__(self, pathName, metadata):
        self.name = pathName 
        self.metadata = metadata

    def getMetadata(self,prop):
        return self.metadata[prop]


class PathParts:

    types = {}

    def __init__(self, type, parts):
        PathParts.types[type] = self
        self.type = type 
        self.paths = {}

        for pathName,data in parts.items():
            self.paths[pathName] = PathPart(pathName,data)

    def getType(self):
        return self.type

    def getPathNames(self):
        return list(self.paths.keys())

    def getPath(self,pathName):
        return self.paths[pathName]

class CheckConfig:
    def __init__(self, defaults, site, data, pathPart):
        self.path = None
        self.baseUrl = site['rootUrl']
        self.intervalMinutes = data['intervalMinutes']
        self.timeoutMs = data['timeoutMs']   
        self.notifyAfterFailures = data['notifyAfterFailures']   
        self.notifyAgainEvery = data['notifyAgainEvery']       
        self.notifyWhenBackUp = data['notifyWhenBackUp']    
        self.regions =  data['regions']
        self.teamIds =  data['teamIds']
        self.userIds =  data['userIds']
        self.integrationIds = data['integrationIds']
        self.priority = data['priority']
        self.tags = []

        self.applyPathPart(pathPart)

        if 'https' in self.baseUrl.lower():
            self.encrypted = True

        self.update(None)

    def update(self,data):

        if data:
            self.__dict__.update(data)
            
        self.tags = []
        self.tags.append(re.sub(r'https*://','',self.baseUrl.replace(".","_")))
        self.tags.append("priority-{}".format(self.priority))
        for p in self.path.split("/"):
            if p.strip() != '':
                self.tags.append(p)


    def applyPathPart(self,pathPart):
        if not self.path:
            self.path = ""

        self.path += "/" + pathPart.name
        self.name = self.path
        self.tags.append(pathPart.name)

    def json(self):
        return json.dumps(self,cls=DumbEncoder)
    
    def summary(self):
        return "{} -> {}{} every:{}m timeout:{}ms notifyAfter:{} fails, priority:{} users:{} teams:{} integrations:{} again:{} intervals, whenBackUp:{} tags:{}" \
        .format(self.regions,self.baseUrl,self.path,self.intervalMinutes,self.timeoutMs,self.notifyAfterFailures,self.priority,self.userIds,self.teamIds,self.integrationIds,self.notifyAgainEvery,self.notifyWhenBackUp,self.tags)


def generateChecks(args):
    config = None

    with open(args.checks_config_file, 'r') as stream:
        try:
            # load our check configs yaml data
            config = yaml.safe_load(stream)

        except yaml.YAMLError as exc:
            logging.exception("Error loading --checks-config-file from: " + 
                environmentsDir + \
                " error=" + str(sys.exc_info()[:2]))
            sys.exit(1)
            
    # generated checks (keyed by site->checkname)
    generatedChecks = {}

    # defaults
    defaults = config['defaults']

    # For every "site" in the yaml data
    for siteName,site in config['sites'].items():

        # skip it?
        if args.sites and siteName not in args.sites.split(','):
            logging.debug("Skipping site: {}. Not in --sites: {}".format(siteName,args.sites))
            continue

        logging.debug("Reading sites[{}]".format(siteName))

        # lets collect every defined pathPart into a 
        # into PathParts objects
        for partType,parts in site['pathParts'].items():
            PathParts(partType,parts)

        # checkTypes are "for" and "forEach"
        for checkName,check in site['checks'].items():

            # skip it?
            if args.checks and checkName not in args.checks.split(','):
                logging.debug("Skipping check: {}. Not in --checks: {}".format(checkName,args.checks))
                continue

            logging.debug("Reading sites[{}].checks[{}]".format(siteName,checkName))

            # Each check starts with a check directive that 
            # directs the flow of how checks will be generated
            for checkDirective,directiveBody in check.items():

                # currently only support forEach
                if checkDirective == 'forEach':
                    handler = ForEachHandler(defaults,site,directiveBody)
                    checkConfigs = handler.build([])
                    logging.debug("sites[{}].checks[{}] generated {} checks.".format(siteName,checkName,len(checkConfigs)))
                    
                    if args.dump_generated_checks:
                        print()
                        print("------------------------------\n{}\n------------------------------".format(checkName))
                        for check in checkConfigs:
                            print("\t{}".format(check.summary()))
                        print()

                    if siteName not in generatedChecks:
                        generatedChecks[siteName] = {}

                    generatedChecks[siteName][checkName] = checkConfigs

                else:
                    logging.error("Unknown check directive: {}".format(checkDirective))

    if not args.dump_generated_checks:
        logging.debug("NOTE! To see generated checks pass --dump-generated-checks")
                    
    return generatedChecks

def toPOSTData(check):

    data = { 
        'name': check.name,
        'host': re.sub(r'https*://','',check.baseUrl),
        'url': check.path,
        'encryption': check.encrypted,
        'type': "http",
        'resolution': check.intervalMinutes,
        'sendnotificationwhendown': check.notifyAfterFailures,
        'notifyagainevery': check.notifyAfterFailures,
        'responsetime_threshold': check.timeoutMs,
        'teamids': check.teamIds,
        'userids': check.userIds,
        'integrationids': check.integrationIds,
        'notifywhenbackup': check.notifyWhenBackUp,
        'probe_filters': [],
        'tags':[]
    }

    for region in check.regions:
        data['probe_filters'].append("region:{}".format(region))

    data['probe_filters'] = ",".join(data['probe_filters'])
    data['tags'] = ",".join(check.tags)



    return data


def createChecks(args,generatedChecks):

    apiToken = None
    with open(args.pingdom_api_token_file, 'r') as file:
        apiToken = file.read().strip()

    for siteName,checkNames in generatedChecks.items():
        for checkName,checks in checkNames.items():
            logging.debug("Transmitting new pingdom checks ({}) for: {}.{}".format(len(checks),siteName,checkName))

            for check in checks:
                url = "{}/checks".format(args.pingdom_api_base_url)

                headers = {
                    'Content-Type': "application/x-www-form-urlencoded",
                    'Authorization': "Bearer {}".format(apiToken),
                    'User-Agent': "github.com/bitsofinfo/pingdom-check-loader/1.0.0",
                    'Accept': "*/*",
                    'Cache-Control': "no-cache"
                }

                response = requests.request("POST", url, data=toPOSTData(check), headers=headers)
                print(response.text)



def exec(args):

    generatedChecks = generateChecks(args)

    if args.create_checks:
        createChecks(args,generatedChecks)
   




def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-f', '--checks-config-file', dest='checks_config_file', default="checkconfigs.yaml", \
        help="Path to a YAML containing the check configs to process")
    parser.add_argument('-s', '--sites', dest='sites', default=None, \
        help="Optional comma delimited list of 'sites' to process. Default None (all sites)")
    parser.add_argument('-c', '--checks', dest='checks', default=None, \
        help="Optional comma delimited list of 'checks.[name]' names to process. Default None (all checks)")
    parser.add_argument('-u', '--pingdom-api-base-url', dest='pingdom_api_base_url', \
        help="The Pingdom API base URL (inclusive of version)", default="https://api.pingdom.com/api/3.1")
    parser.add_argument('-t', '--pingdom-api-token-file', dest='pingdom_api_token_file', \
        help="Path to a file that contains an valid pingdom API token", default=None)
    parser.add_argument('-d', '--dump-generated-checks', action='store_true', default=False, \
        help="Dumps all generated checks to STDOUT")
    parser.add_argument('-x', '--create-checks', action='store_true', default=False, \
        help="Transmit checks to pingdom for creation")
    parser.add_argument('-l', '--log-level', dest='log_level', default="DEBUG", \
        help="log level, DEBUG, INFO, etc")
    parser.add_argument('-b', '--log-file', dest='log_file', default=None, \
        help="Path to log file; default None = STDOUT")
    


    args = parser.parse_args()


    dump_help = False
   
    if dump_help:
        parser.print_help()
        sys.exit(1)

    logging.basicConfig(level=logging.getLevelName(args.log_level),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        filename=args.log_file,filemode='w')
    logging.Formatter.converter = time.gmtime

    exec(args)


###########################
# Main program
##########################
if __name__ == '__main__':
    main()