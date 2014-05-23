import getpass
import argparse
import requests
import time
import try_parser

class Job(object):
    def __init__(self, job_type, id, props):
        self.id = id
        self.type = job_type
        self.props = props

    @classmethod
    def from_json(cls, data):
        if "buildername" in data and "Android" in data["buildername"]:
            print data
        if "request_id" in data:
            job_type = "request"
            id = data["request_id"]
        else:
            job_type = "build"
            id = data["build_id"]

        props = set(data["buildername"].split(" "))
        return cls(job_type, id, props)

    def __repr__(self):
        return "<Job %i %s %s>" % (self.id, self.type, " ".join(self.props))

def load_build_data(branch, rev, auth):
    import json
    resp = requests.get("https://secure.pub.build.mozilla.org/buildapi/self-serve/%s/rev/%s?format=json" % (branch, rev), auth=auth)
    if resp.status_code != 200:
        raise Exception("HTTP Error code %i " % resp.status_code)
    else:
        rv = resp.json()
        with open("test.json", "w") as f:
            json.dump(rv, f)
        return rv

def get_job_list(json_data):
    return [Job.from_json(item) for item in json_data if not "endtime" in item or not item["endtime"]]

def unwanted_jobs(branch, allowed_jobs, job_list):
    rv = []
    for job in job_list:
        if not any([try_parser.match_builds(allowed_jobs["build_types"],
                                            allowed_jobs["build_platforms"],
                                            branch,
                                            job),
                    try_parser.match_testsuites(allowed_jobs["testsuites"],
                                                branch,
                                                job),
                    try_parser.match_talos(allowed_jobs["talos"],
                                           branch,
                                           job)]):
            rv.append(job)

    return rv

def cancel_jobs(branch, jobs, auth):
    for job in jobs:
        cancel_job(branch, job, auth)

def cancel_job(branch, job, auth):
    url = "https://secure.pub.build.mozilla.org/buildapi/self-serve/%s/%s/%i" % (branch, job.type, job.id)
    print "DELETE", url
    requests.delete(url, auth=auth)

def is_complete(branch, rev, auth):
    resp = requests.get("https://secure.pub.build.mozilla.org/buildapi/self-serve/%s/rev/%s/is_done?format=json" %
                        (branch, rev), auth=auth)
    if resp.status_code == 200:
        return resp.json()["job_complete"]
    else:
        raise Exception("HTTP Error code %i " % resp.status_code)

def monitor_build(branch, rev, allowed_jobs, auth):
    while True:
        json_data = load_build_data(branch, rev, auth)
        job_list = get_job_list(json_data)
        unwanted = unwanted_jobs(branch, allowed_jobs, job_list)
        wanted = [item for item in job_list if not item in set(unwanted)]
        cancel_jobs(branch, unwanted, auth)
        for item in wanted:
            print "Keeping job " + str(item)
        if is_complete(branch, rev, auth):
            break
        time.sleep(120)

def get_auth():
    default_user = getpass.getuser() + "@mozilla.com"
    username = raw_input("Username [%s]: " % default_user).strip()
    if not username:
        username = default_user

    password = getpass.getpass()
    return username, password

def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", default="cedar", help="Branch to use")
    parser.add_argument("rev", help="Revision to use")
    try_parser.add_parser_opts(parser)
    return parser

def main():
    parser = get_parser()
    args = parser.parse_args()

    jobs_data = try_parser.get_jobs(args)
    print jobs_data
    auth = get_auth()

    monitor_build(args.branch, args.rev, jobs_data, auth)

if __name__ == "__main__":
    main()
