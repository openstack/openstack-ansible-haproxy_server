#!/usr/bin/env bash
# Copyright 2015, Rackspace US, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -o pipefail
set -euov

FUNCTIONAL_TEST=${FUNCTIONAL_TEST:-true}

# Start fresh
rm -rf .tox

# Install python2 for Ubuntu 16.04,CentOS 7 and openSUSE Leap 42.1
if which apt-get &>/dev/null && ! which zypper &>/dev/null; then
     sudo apt-get update && sudo apt-get install -y python-dev
elif which yum &>/dev/null; then
     sudo yum install -y python-devel
elif which zypper &>/dev/null; then
    # Need to pull libffi and python-pyOpenSSL early
    # because we install ndg-httpsclient from pip
    sudo zypper -n in python-devel libffi-devel python-pyOpenSSL
fi

# Install pip
if ! which pip &>/dev/null; then
    curl --silent --show-error --retry 5 \
        https://bootstrap.pypa.io/get-pip.py | sudo python2.7
fi

# Install bindep and tox
sudo pip install bindep tox

# CentOS 7 requires two additional packages:
#   redhat-lsb-core - for bindep profile support
#   epel-release    - required to install python-ndg_httpsclient/python2-pyasn1
if which yum &>/dev/null; then
    sudo yum -y install redhat-lsb-core epel-release
# openSUSE 42.1 does not have python-ndg-httpsclient
elif which zypper &>/dev/null; then
    pip install ndg-httpsclient
fi

# Get a list of packages to install with bindep. If packages need to be
# installed, bindep exits with an exit code of 1.
BINDEP_PKGS=$(bindep -b -f bindep.txt test || true)
echo "Packages to install: ${BINDEP_PKGS}"

# Install OS packages using bindep
if [[ ${#BINDEP_PKGS} > 0 ]]; then
    if which apt-get &>/dev/null && ! which zypper &>/dev/null ; then
        sudo apt-get update
        DEBIAN_FRONTEND=noninteractive \
            sudo apt-get -q --option "Dpkg::Options::=--force-confold" \
            --assume-yes install `bindep -b -f bindep.txt test`
    elif which yum &>/dev/null; then
        sudo yum install -y $BINDEP_PKGS
    elif which zypper &>/dev/null; then
        sudo zypper -n in $BINDEP_PKGS
    fi
fi

# run through each tox env and execute the test
for tox_env in $(awk -F= '/envlist/ {print $2}' tox.ini | sed 's/,/ /g'); do
    if [ "${tox_env}" != "ansible-functional" ]; then
        tox -e ${tox_env}
    elif [ "${tox_env}" == "ansible-functional" ]; then
        if ${FUNCTIONAL_TEST}; then
            tox -e ${tox_env}
        fi
    fi
done

# vim: set ts=4 sw=4 expandtab:
