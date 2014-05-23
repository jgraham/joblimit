# Mozilla Try Parser
# Contributor(s):
#   Lukas Blakk <lsblakk@mozilla.com>

import argparse
import re

#Note "leak test" vs "debug"

build_platforms = {
    "linux":{"require": ["Linux", "build"],
             "exclude": ["x86-64", "asan"]},
    "linux64":{"require": ["Linux", "x86-64", "build"],
               "exclude": ["asan"]},
    "linux64-asan":{"default":False,
                    "require": ["Linux" "x86-64", "asan", "build"]},
    "macosx64": {"require": ["OS", "X", "build"]},
    "win32": {"require":["WINNT", "5.2", "build"]},
    #"win64": {"WINNT", "5.2"},
    "android": {"require": ["Android", "2.2", "build"],
                "exclude": ["Armv6"]},
    "android-armv6":{"require": ["Android", "2.2", "Armv6", "build"]},
    "android-x86":{"require": ["Android", "4.2", "x86", "build"]},
    "emulator":{"require": ["b2g_%(branch)s_emulator_dep"],
                "debug": {"require": ["b2g_%(branch)s_emulator-debug_dep"]}},
}

testsuite_platforms = {
    "Ubuntu": {"require": ["Ubuntu", "VM"],
               "exclude": ["x64"]},
    "Fedora": {"require": ["Fedora", "Rev3"],
               "exclude": ["12x64"]},
    "Ubuntu-64": {"require": ["Ubuntu", "VM", "x64"]},
    "Fedora-64": {"require": ["Fedora", "Rev3", "12x64"]},
    "10.6": {"require": ["MacOSX", "10.6"]},
    "10.8": {"require": ["MacOSX", "10.8"]},
    "10.9": {"require": ["MacOSX", "10.9"]},
}

testsuites = {
    "web-platform-tests":{"require": ["web-platform-tests"]}
}

testsuite_groups = {
    "all":testsuites.keys(),
    "mochitest":["mochitest-%s" % item for item in [str(chunk) for chunk in range(1,6)] + ["bc", "o", "metro-chrome"]]}

def match(branch, job, require, exclude, extras=None):
    if (all(item % {"branch":branch} in job.props for item in require) and
        (not any(item % {"branch":branch} in job.props for item in exclude))):
        return not extras or any(all(item in job.props for item in group) for group in extras)

    return False

def match_builds(build_types, platform_names, branch, job):
    matches = []
    for build_type in build_types:
        for platform_name in platform_names:
            build_props = build_platforms[platform_name]
            if build_type == "debug":
                if "debug" in build_props:
                    build_props = build_props["debug"]

            build_props = build_props.copy()

            require = build_props["require"]
            exclude = build_props.get("exclude", [])

            if build_type == "debug":
                extras = [["leak", "test"], ["debug"]]
            else:
                extras = []
                exclude.extend(["leak", "test", "debug"])

            if match(branch, job, require, exclude, extras):
                matches.append(platform_name)

    assert len(matches) <= 1, "%r, %r" % (matches, job)
    return bool(matches)


def match_testsuites(testsuite_map, branch, job):
    matches = []

    for testsuite_name, platforms in testsuite_map.iteritems():
        testsuite_props = testsuites[testsuite_name]

        if not platforms:
            platforms = ["all"]

        for platform_name in platforms:
            testsuite_props = testsuite_props.copy()
            platform_props = testsuite_platforms[platform_name] if platform_name != "all" else {}

            require = testsuite_props["require"][:]
            exclude = testsuite_props.get("exclude", [])[:]

            require.extend(platform_props.get("require", []))
            exclude.extend(platform_props.get("exclude", []))

            print testsuite_name, platform_name, require, exclude, "web-platform-tests" in job.props

            if match(branch, job, require, exclude):
                matches.append((testsuite_name, platform_name))

    assert len(matches) <= 1
    return bool(matches)


def match_talos(talos_suites, branch, job):
    return False

def expand_testsuite_groups(testsuites_map):
    rv = {}
    for testsuite_name, platforms in testsuites_map.iteritems():
        if testsuite_name in testsuite_groups:
            for item in testsuite_groups[testsuite_name]:
                rv[item] = platforms
        else:
            rv[testsuite_name] = platforms
    return rv

def expand_platforms(platforms):
    platforms = set(platforms)
    if "x64" in platforms:
        platforms.remove("x64")
        platforms.add("Fedora-64")
        platforms.add("Ubuntu-64")

    if "-x64" in platforms:
        platforms.remove("-x64")
    else:
        if "Fedora" in platforms:
            platforms.add("Fedora-64")
        if "Ubuntu" in platforms:
            platforms.add("Ubuntu-64")

    return list(platforms)

def expand_testsuite_platforms(testsuite_map):
    for testsuite, platforms in testsuite_map.iteritems():
        testsuite_map[testsuite] = expand_platforms(platforms)

    return testsuite_map

def parse_testsuites(testsuites):
    print testsuites
    testsuite_map = {}
    state = "name"
    current_name = ["", ""]
    def emit():
        if state == "name":
            name = current_name[1].strip()
            if not name:
                return
            testsuite_map[name] = []
            current_name[0] = current_name[1]
        elif state == "index":
            testsuite_map[current_name[0]].append(current_name[1])
        current_name[1] = ""

    for char in testsuites:
        if state == "name":
            if char == ",":
                emit()
            elif char == "[":
                emit()
                state = "index"
            else:
                current_name[1] += char
        elif state == "index":
            if char == ",":
                emit()
            elif char == "]":
                emit()
                state = "after_index"
            else:
                current_name[1] += char
        elif state == "after_index":
            if char == " ":
                pass
            elif char == ",":
                self.state = "name"
            else:
                assert False
    emit()
    print testsuite_map
    return testsuite_map


def add_parser_opts(parser):
    group = parser.add_argument_group("trychooser options",
                                      description='Options to limit the jobs that get run')

    group.add_argument('--build', '-b',
                        default='do',
                        dest='build',
                        help='accepts the build types requested')
    group.add_argument('--platform', '-p',
                        default='all',
                        dest='user_platforms',
                        help='provide a list of platforms desired, or specify none (default is all)')
    group.add_argument('--unittests', '-u',
                        default='all',
                        dest='test',
                        help='provide a list of unit tests, or specify all (default is None)')
    group.add_argument('--talos', '-t',
                        default='none',
                        dest='talos',
                        help='provide a list of talos tests, or specify all (default is None)')


def get_jobs(options):
    # Build options include a possible override of 'all' to get a buildset
    # that matches m-c
    if options.build == 'do' or options.build == 'od':
        options.build = ['opt', 'debug']
    elif options.build == 'd':
        options.build = ['debug']
    elif options.build == 'o':
        options.build = ['opt']
    else:
        # for any input other than do/od, d, o, all set to default
        options.build = ['opt', 'debug']

    print vars(options)

    build_types = options.build
    platforms = options.user_platforms.split(",") if options.user_platforms != "all" else [key for key, value in build_platforms.iteritems() if not ("default" in value and value["default"] is False)]

    if options.test != "none":
        testsuites = expand_testsuite_platforms(expand_testsuite_groups(parse_testsuites(options.test)))
    else:
        testsuites = {}

    if options.talos != "none":
        talos = options.talos.split(",")
    else:
        talos = []

    return {"build_types": build_types,
            "build_platforms": platforms,
            "testsuites": testsuites,
            "talos": talos}
