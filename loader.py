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
    def __init__(self, timestamp, defaults, checkName, site, forEach):

        self.timestamp = timestamp
        self.site = site
        self.defaults = defaults
        self.checkName = checkName

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
                self.subParts = ForEachHandler(timestamp,defaults,checkName,site,directive)
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

                    c = CheckConfig(self.timestamp, self.defaults, self.checkName, \
                        self.site, self.getCheckConf(path), path)
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
    def __init__(self, timestamp, defaults, checkName, site, data, pathPart):
        self.timestamp = timestamp
        self.path = None
        self.checkName = checkName
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
        self.tags.append(self.timestamp)
        self.tags.append(self.checkName)
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


def generateChecks(args,timestamp):

    logging.debug("generateChecks() initiating run w/ id: {}".format(timestamp))

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
            if args.check_names and checkName not in args.check_names.split(','):
                logging.debug("Skipping check: {}. Not in --check-names: {}".format(checkName,args.check_names))
                continue

            logging.debug("Reading sites[{}].checks[{}]".format(siteName,checkName))

            # Each check starts with a check directive that 
            # directs the flow of how checks will be generated
            for checkDirective,directiveBody in check.items():

                # currently only support forEach
                if checkDirective == 'forEach':
                    handler = ForEachHandler(timestamp,defaults,checkName,site,directiveBody)
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
        'notifyagainevery': check.notifyAgainEvery,
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


def getApiToken(args):
    
    try:
        with open(args.pingdom_api_token_file, 'r') as file:
            return file.read().strip()
    except Exception as e:
        logging.exception("getApiToken() Error loading token [{}] = {}".format(args.pingdom_api_token_file,str(sys.exc_info()[:2])))
        raise e


def getChecks(args,checkNames,tagQualifiers):

    toReturn = []
    try:
        url = "{}/checks".format(args.pingdom_api_base_url)

        querystring = {"include_tags":True}

        # tags are an OR qualifier, but our args.delete_tag_qualifiers is an AND
        # this just pre-limits the results, we still have to cross check them below
        if tagQualifiers and len(tagQualifiers) > 0:
            if 'tags' not in querystring:
                querystring['tags'] = ""

            querystring["tags"] = ",".join(tagQualifiers)

        # we also pre-limit for checkNames, which are also tags
        if checkNames and len(checkNames) > 0:
            if 'tags' not in querystring:
                querystring['tags'] = ""
            else:
                querystring["tags"] += ","
                
            querystring["tags"] += (",".join(checkNames))

        headers = {
            'Authorization': "Bearer {}".format(getApiToken(args)),
            'User-Agent': "github.com/bitsofinfo/pingdom-check-loader/1.0.0",
            'Accept': "*/*",
            'Accept-Encoding': "gzip, deflate",
            'Cache-Control': "no-cache"
        }

        response = requests.request("GET", url, params=querystring, headers=headers)

        if response.status_code == 200:

            checks = response.json() # this is a dict!

            if len(checks['checks']) == 0:
                logging.debug("GET checks OK: {} but found zero {} checks, nothing to do... CRITERIA={}" \
                    .format(response.status_code,len(checks['checks']),querystring))
                return toReturn # zero
            
            logging.debug("GET checks OK: {} found {} pre-qualified (tags ANY match) checks, CRITERIA={}" \
                .format(response.status_code,len(checks['checks']),querystring))


            # ok, tag_qualifiers is an AND, so we need to make sure
            # qualify that each check has EVERY tag in the qualifier
            # This does NOT apply to the checkName tags
            if tagQualifiers:
                for check in checks['checks']:
                    canRetain = True
                    tags = list(map(lambda t : t['name'],check['tags']))
                    for qualifier in tagQualifiers: # Tags are returned lcased...
                        if qualifier.lower() not in tags:
                            canRetain = False

                    if canRetain:
                        toReturn.append(check)
            
            # no qualifiers, return all
            else:
                toReturn = checks['checks']

            return toReturn

        else:
            msg = "GET checks FAILED: {} RESPONSE={} for CRITERIA={}".format(response.status_code,response.content,querystring)
            logging.error(msg)
            raise Exception(msg)

    except Exception as e:
        logging.exception("getChecks() error GETing checks: ERROR={}" \
            .format(str(sys.exc_info()[:2])))
        raise e


def deleteChecks(args,timestamp):

    checkIdsToDelete = []

    # get all qualifiying checks
    try:
        checkNames = None
        tagQualifiers = None

        if args.check_names:
            checkNames = args.check_names.split(",")

        if args.delete_tag_qualifiers:
            tagQualifiers = args.delete_tag_qualifiers.split(",")

        pingdomChecks = getChecks(args,checkNames,tagQualifiers)

    except Exception as e:
        logging.exception("deleteChecks() error DELETing checks: ERROR={} CHECK_IDS={}" \
            .format(str(sys.exc_info()[:2]),checkIdsToDelete))
        raise e

    # fail fast if none
    if len(pingdomChecks) == 0:
        logging.info("deleteChecks() no matching pingdom checks found for --check-names (ANY tag match) {} + --delete-tag-qualifiers (all tags MUST MATCH) {}" \
            .format(args.check_names,args.delete_tag_qualifiers)) 
        return

    # lets log them all + collect ids
    for check in pingdomChecks:
        logging.debug("deleteChecks() found: {} {} {} {}" \
            .format(check['id'],check['hostname'],check['name'],list(map(lambda t : t['name'],check['tags']))))
        checkIdsToDelete.append(str(check['id']))

    # warn the user
    proceed = input("\n\nYou are about to DELETE the above checks in Pingdom: do you want to proceed?: (y|n):").strip()
    if proceed.lower() != 'y':
        logging.debug("Exiting, confirmation prompt input was: " + proceed)
        sys.exit(1)

    # ok lets do the actual delete
    try:
        url = "{}/checks".format(args.pingdom_api_base_url)
        querystring = {"delcheckids":",".join(checkIdsToDelete)}

        headers = {
            'Authorization': "Bearer {}".format(getApiToken(args)),
            'User-Agent': "github.com/bitsofinfo/pingdom-check-loader/1.0.0",
            'Accept': "*/*",
            'Accept-Encoding': "gzip, deflate",
            'Cache-Control': "no-cache"
        }

        response = requests.request("DELETE", url, params=querystring, headers=headers)

        if response.status_code == 200:
            logging.debug("DELETE checks OK: {} {} checks, CRITERIA={}" \
                .format(response.status_code,len(checkIdsToDelete),querystring))

        else:
            msg = "DELETE checks FAILED: {} RESPONSE={} for CRITERIA={}".format(response.status_code,response.content,querystring)
            logging.error(msg)
            raise Exception(msg)

    except Exception as e:
        logging.exception("deleteChecks() error DELETEing checks {}: ERROR={}" \
            .format(checkIdsToDelete,str(sys.exc_info()[:2])))
        raise e
    



def createChecks(args,timestamp,generatedChecks):

    proceed = input("\n\nYou are about to CREATE the above checks in Pingdom. --dump-generated-checks for more details: do you want to proceed?: (y|n):").strip()
    if proceed.lower() != 'y':
        logging.debug("Exiting, confirmation prompt input was: " + proceed)
        sys.exit(1)

    apiToken = getApiToken(args)
    created = 0
    failed = 0

    for siteName,checkNames in generatedChecks.items():
        for checkName,checks in checkNames.items():
            logging.debug("Transmitting new pingdom checks ({}) for: {}.{}".format(len(checks),siteName,checkName))

            for check in checks:

                postData = None

                try:
                    url = "{}/checks".format(args.pingdom_api_base_url)

                    headers = {
                        'Content-Type': "application/x-www-form-urlencoded",
                        'Authorization': "Bearer {}".format(apiToken),
                        'User-Agent': "github.com/bitsofinfo/pingdom-check-loader/1.0.0",
                        'Accept': "*/*",
                        'Cache-Control': "no-cache"
                    }
                    postData = toPOSTData(check)
                    response = requests.request("POST", url, data=postData, headers=headers)
                    
                    if response.status_code == 200:
                        created += 1
                        logging.debug("Check created OK: {} RESPONSE={} for CHECK={}".format(response.status_code,response.content,check.summary()))
                    else:
                        failed != 1
                        logging.error("Check create FAILED: {} RESPONSE={} for CHECK={}".format(response.status_code,response.content,response,check.summary()))

                except Exception as e:
                    failed += 1
                    logging.exception("createChecks() error POSTing check: POST-DATA={} ERROR={} CHECK={}" \
                        .format(postData,str(sys.exc_info()[:2]),check.summary()))

    logging.debug("createChecks() completed, {} checks created, {} failed at Pingdom w/ tag: {}".format(created,failed,timestamp))


def exec(args):

    # the timestamp
    timestamp = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S%f')[:-4]

    try:
        # are we deleting?
        if args.delete_in_pingdom:
            deleteChecks(args,timestamp)
        
        # we are just creating/generating
        else:
            # pre-compute generated checks to potentially
            # be created...
            generatedChecks = generateChecks(args,timestamp)

            # optionally create
            if args.create_in_pingdom:
                createChecks(args,timestamp,generatedChecks)

    except Exception as e:
        logging.exception("Unexpected general error = " + str(sys.exc_info()[:2]))

    finally:
        logging.debug("Finished: run identifier: {}".format(timestamp))
        

def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-f', '--checks-config-file', dest='checks_config_file', default="checkconfigs.yaml", \
        help="Path to a YAML containing the check configs to process")
    parser.add_argument('-s', '--sites', dest='sites', default=None, \
        help="Optional comma delimited list of 'sites' to process. Default None (all sites)")
    parser.add_argument('-c', '--check-names', dest='check_names', default=None, \
        help="Optional comma delimited list of 'checks.[name]' names to process. Default None (all checks)")
    parser.add_argument('-u', '--pingdom-api-base-url', dest='pingdom_api_base_url', \
        help="The Pingdom API base URL (inclusive of version)", default="https://api.pingdom.com/api/3.1")
    parser.add_argument('-t', '--pingdom-api-token-file', dest='pingdom_api_token_file', \
        help="Path to a file that contains an valid pingdom API token", default=None)
    parser.add_argument('-d', '--dump-generated-checks', action='store_true', default=False, \
        help="Dumps all generated checks to STDOUT")
    parser.add_argument('-x', '--create-in-pingdom', action='store_true', default=False, \
        help="Create all checks in Pingdom for the designated --check-names argument")
    parser.add_argument('-D', '--delete-in-pingdom', action='store_true', default=False, \
        help="DELETE all checks in Pingdom who's 'tags' contains any of the check names in the --checks argument")
    parser.add_argument('-q', '--delete-tag-qualifiers', dest='delete_tag_qualifiers', default=None, \
        help="Comma delimited list of one or more tags. To be used in conjunction w/ --delete-in-pingdom. " + \
        " Will only delete matching --check-names " + \
        " that also contain ALL of the specified tags in this comma delimited list of tag names")
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