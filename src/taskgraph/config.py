# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import os
import logging
import sys
import attr
from six import string_types, text_type
from .util import path

from .util.python_path import find_object
from .util.schema import validate_schema, Schema, optionally_keyed_by
from voluptuous import Required, Extra, Any, Optional, Length, All
from .util.yaml import load_yaml

logger = logging.getLogger(__name__)

graph_config_schema = Schema({
    # The trust-domain for this graph.
    # (See https://firefox-source-docs.mozilla.org/taskcluster/taskcluster/taskgraph.html#taskgraph-trust-domain)  # noqa
    Required('trust-domain'): Any(*string_types),
    Required('task-priority'): optionally_keyed_by('project', Any(
        'highest',
        'very-high',
        'high',
        'medium',
        'low',
        'very-low',
        'lowest',
    )),
    Required('workers'): {
        Required('aliases'): {
            text_type: {
                Required('provisioner'): optionally_keyed_by('level', text_type),
                Required('implementation'): text_type,
                Required('os'): text_type,
                Required('worker-type'): optionally_keyed_by('level', text_type),
            }
        },
    },
    Required("taskgraph"): {
        Optional(
            "register",
            description="Python function to call to register extensions.",
        ): text_type,
        Optional('decision-parameters'): text_type,
        Optional(
            'cached-task-prefix',
            description="The taskcluster index prefix to use for caching tasks. "
            "Defaults to `trust-domain`."
        ): text_type,
        Required("repositories"): All(
            {
                text_type: {
                    Required("name"): text_type,
                    Optional("project-regex"): text_type,
                    Optional("ssh-secret-name"): text_type,
                    # FIXME
                    Extra: text_type,
                }
            },
            Length(min=1),
        ),
    },
    Extra: object,
})


@attr.s(frozen=True, cmp=False)
class GraphConfig(object):
    _config = attr.ib()
    root_dir = attr.ib()

    _PATH_MODIFIED = False

    def __getitem__(self, name):
        return self._config[name]

    def __contains__(self, name):
        return name in self._config

    def register(self):
        """
        Add the project's taskgraph directory to the python path, and register
        any extensions present.
        """
        modify_path = os.path.dirname(self.root_dir)
        if GraphConfig._PATH_MODIFIED:
            if GraphConfig._PATH_MODIFIED == modify_path:
                # Already modified path with the same root_dir.
                # We currently need to do this to enable actions to call
                # taskgraph_decision, e.g. relpro.
                return
            raise Exception("Can't register multiple directories on python path.")
        GraphConfig._PATH_MODIFIED = modify_path
        sys.path.insert(0, modify_path)
        register_path = self['taskgraph'].get('register')
        if register_path:
            find_object(register_path)(self)

    @property
    def vcs_root(self):
        if path.split(self.root_dir)[-2:] != ['taskcluster', 'ci']:
            raise Exception(
                "Not guessing path to vcs root. "
                "Graph config in non-standard location."
            )
        return os.path.dirname(os.path.dirname(self.root_dir))

    @property
    def taskcluster_yml(self):
        if path.split(self.root_dir)[-2:] != ['taskcluster', 'ci']:
            raise Exception(
                "Not guessing path to `.taskcluster.yml`. "
                "Graph config in non-standard location."
            )
        return os.path.join(
            os.path.dirname(os.path.dirname(self.root_dir)),
            ".taskcluster.yml",
        )


def validate_graph_config(config):
    validate_schema(graph_config_schema, config, "Invalid graph configuration:")


def load_graph_config(root_dir):
    config_yml = os.path.join(root_dir, "config.yml")
    if not os.path.exists(config_yml):
        raise Exception("Couldn't find taskgraph configuration: {}".format(config_yml))

    logger.debug("loading config from `{}`".format(config_yml))
    config = load_yaml(config_yml)

    validate_graph_config(config)
    return GraphConfig(config=config, root_dir=root_dir)
